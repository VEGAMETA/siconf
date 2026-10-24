"""
title: FLUX 3: картинки
description: Генерация и редактирование картинок в ComfyUI (FLUX 3 Image Klein). Модель сама выбирает размер и режим, правит уже нарисованные или приложенные картинки и видит уменьшенную копию результата для самопроверки.
author: local
version: 0.1.0
"""

import base64
import io
import json
import mimetypes
import pathlib
import random
import uuid

import aiofiles
from open_webui.models.chats import Chats
from open_webui.models.files import Files
from open_webui.models.users import UserModel
from open_webui.routers.images import get_image_config, get_image_data, upload_image
from open_webui.storage.provider import Storage
from open_webui.utils.chat_id import is_saved_chat_id
from open_webui.utils.images.comfyui import (
    ComfyUICreateImageForm,
    ComfyUIWorkflow,
    comfyui_create_image,
    comfyui_upload_image,
)
from PIL import Image

T2I_WORKFLOW = pathlib.Path(r"D:\llm\openwebui_flux3_t2i.json")
EDIT_WORKFLOW = pathlib.Path(r"D:\llm\openwebui_flux3_edit.json")
# quality (по карточке модели BFL): fast — дистиллированная (16 шагов, без CFG); best — базовая (50 шагов, CFG 3.5), примерно вшестеро дольше
QUALITY = {
    "fast": {"unet": "flux3-image-klein-int8-convrot.safetensors", "steps": 16, "cfg": 1.0},
    "best": {"unet": "flux3-image-klein-base-int8-convrot.safetensors", "steps": 50, "cfg": 3.5},
}
MIN_PIXELS, MAX_PIXELS = 512 * 512, 1536 * 1536
MAX_REFERENCES = 4
PREVIEW_SIDE = 768  # уменьшенная копия результата, которую видит сама модель


def _size(size):
    """'832x1216' -> (832, 1216): стороны кратны 16, площадь в разумных пределах."""
    try:
        w, h = (int(v) for v in str(size).lower().replace("×", "x").split("x"))
    except ValueError:
        w, h = 1024, 1024
    w, h = max(w, 64), max(h, 64)
    scale = 1.0
    if w * h > MAX_PIXELS:
        scale = (MAX_PIXELS / (w * h)) ** 0.5
    elif w * h < MIN_PIXELS:
        scale = (MIN_PIXELS / (w * h)) ** 0.5
    return max(16, round(w * scale / 16) * 16), max(16, round(h * scale / 16) * 16)


def _build(path, prompt, quality, seed):
    wf = json.loads(path.read_text(encoding="utf-8"))
    q = QUALITY.get(quality, QUALITY["fast"])
    wf["1"]["inputs"]["unet_name"] = q["unet"]
    wf["8"]["inputs"].update(steps=q["steps"], cfg=q["cfg"], seed=seed)
    wf["12"]["inputs"]["text"] = prompt
    return wf


def _preview(data):
    """JPEG-копия до PREVIEW_SIDE по большей стороне как data:-URL."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((PREVIEW_SIDE, PREVIEW_SIDE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


async def _image_bytes(ref, user):
    """Картинка по data:-URL, ссылке /api/v1/files/<id>/content или id файла."""
    if ref.startswith("data:"):
        header, encoded = ref.split(",", 1)
        return base64.b64decode(encoded), header[5:].split(";")[0] or "image/png"
    file_id = ref.split("/api/v1/files/")[1].split("/")[0] if "/api/v1/files/" in ref else ref
    file = await Files.get_file_by_id(file_id)
    if not file or (file.user_id != user.id and user.role != "admin"):
        raise ValueError("файл картинки не найден")
    path = Storage.get_file(file.path)
    async with aiofiles.open(path, "rb") as f:
        data = await f.read()
    return data, (file.meta or {}).get("content_type") or mimetypes.guess_type(path)[0] or "image/png"


def _file_refs(files):
    return [f.get("url") or f.get("id") for f in files or [] if f.get("type") == "image" and (f.get("url") or f.get("id"))]


async def _chat_images(chat_id, user, messages):
    """Все картинки беседы по порядку: приложенные пользователем и нарисованные раньше.

    Берёт ветку из базы (там есть и сгенерированные картинки), для временного чата — из __messages__.
    """
    refs = []
    if is_saved_chat_id(chat_id):
        chat = await Chats.get_chat_by_id_and_user_id(chat_id, user.id)
        history = ((chat.chat if chat else None) or {}).get("history", {})
        by_id, chain, cur, seen = history.get("messages", {}), [], history.get("currentId"), set()
        while cur and cur not in seen:
            seen.add(cur)
            msg = by_id.get(cur)
            if not msg:
                break
            chain.append(msg)
            cur = msg.get("parentId")
        for msg in reversed(chain):
            refs += _file_refs(msg.get("files"))
    for msg in messages or []:  # картинки текущего запроса могут ещё не быть в базе
        content = msg.get("content")
        if msg.get("role") == "user" and isinstance(content, list):
            for part in content:
                url = (part.get("image_url") or {}).get("url") if part.get("type") == "image_url" else None
                if url and url not in refs:
                    refs.append(url)
    return refs


class Tools:
    async def _run(self, wf, prompt, label, request, user, emit, chat_id, message_id, model):
        cfg = await get_image_config()
        base_url, api_key = cfg.COMFYUI_BASE_URL, cfg.COMFYUI_API_KEY
        if emit:
            await emit({"type": "status", "data": {"description": f"Рисую: {label}", "done": False}})
        width = wf["7"]["inputs"]["width"]
        height = wf["7"]["inputs"]["height"]
        form = ComfyUICreateImageForm(
            workflow=ComfyUIWorkflow(workflow=json.dumps(wf), nodes=[]),
            prompt=prompt,
            width=width if isinstance(width, int) else 1024,
            height=height if isinstance(height, int) else 1024,
        )
        res = await comfyui_create_image(None, form, str(uuid.uuid4()), base_url, api_key)
        if not res or not res.get("data"):
            raise RuntimeError("ComfyUI не вернул картинку (запущен ли ComfyUI на 8188?)")
        urls = list(dict.fromkeys(img["url"] for img in res["data"]))
        urls = [u for u in urls if "type=output" in u] or urls
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        images, previews = [], []
        for url in urls:
            data, content_type = await get_image_data(url, headers, trusted_base_url=base_url)
            previews.append(_preview(data))
            _, image_file = await upload_image(request, data, content_type, {"prompt": prompt}, user)
            images.append(image_file)
        image_files = [{"type": "image", **img} for img in images]
        if is_saved_chat_id(chat_id) and message_id and images:
            db_files = await Chats.add_message_files_by_id_and_message_id(chat_id, message_id, image_files)
            if db_files is not None:
                image_files = db_files
        if emit:
            await emit({"type": "chat:message:files", "data": {"files": image_files}})
            await emit({"type": "status", "data": {"description": f"Готово: {label}", "done": True}})
        # словарь, а не строка: Open WebUI вынимает data:-картинки из результата и показывает их модели
        result = {
            "status": "success",
            "message": "The image is already visible to the user in the chat; do not embed it again. "
            "The attached preview is what was actually generated: compare it with the request. Say in one line "
            "which size and quality you used, and if something requested is clearly missing or wrong "
            "(wrong object, missing element, broken anatomy or hands, misspelled text), say so plainly and offer a fix.",
            "seed": wf["8"]["inputs"]["seed"],
        }
        # превью — только моделям со зрением
        vision = ((model or {}).get("info") or {}).get("meta", {}).get("capabilities", {}).get("vision")
        if vision and previews:
            result["preview"] = previews[0]
        else:
            result["message"] = ("The image is already visible to the user in the chat; do not embed it again. "
                                 "Say in one line which size and quality you used.")
        return result

    async def create_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "fast",
        seed: int = 0,
        __request__=None,
        __user__: dict = None,
        __event_emitter__=None,
        __chat_id__: str = None,
        __message_id__: str = None,
        __model__: dict = None,
    ) -> dict:
        """
        Generate a new image with FLUX 3. Use it whenever the user asks to draw, generate or show a picture, or to come up with a visual thing (cover, poster, logo, avatar, banner, illustration).
        :param prompt: One continuous English prose caption, 100-350 words, not tags: medium and style first ("Full-color outdoor photograph, ..."), then scene, lighting and camera, then each subject with concrete colors, materials, state and frame-relative position (frame-left, foreground, background). Text that must appear goes in double quotes with its typography and placement.
        :param size: WIDTHxHEIGHT: "832x1216" portrait or full-height figure, "1216x832" landscape or room, "1344x768" wide banner or thumbnail, "1024x1024" square or single object; the size the user asks for if any.
        :param quality: "fast" (default, about 15 seconds) or "best" (slower base model, about 6 times longer; only when the user asks for maximum quality).
        :param seed: 0 for a new random image; reuse the previous seed only when the user wants the same image with a small change in the prompt.
        :return: Result of the generation
        """
        try:
            seed = seed or random.randint(1, 2**50)
            w, h = _size(size)
            wf = _build(T2I_WORKFLOW, prompt, quality, seed)
            wf["7"]["inputs"].update(width=w, height=h, batch_size=1)
            wf["4"]["inputs"].update(width=w, height=h)
            q = quality if quality in QUALITY else "fast"
            label = f"{w}x{h}, {q}, seed {seed}"
            user = UserModel(**__user__) if __user__ else None
            return await self._run(wf, prompt, label, __request__, user, __event_emitter__, __chat_id__,
                                   __message_id__, __model__)
        except Exception as e:
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": f"Ошибка: {e}", "done": True}})
            return {"error": str(e)}

    async def edit_image(
        self,
        prompt: str,
        images: int = 1,
        quality: str = "fast",
        seed: int = 0,
        __request__=None,
        __user__: dict = None,
        __event_emitter__=None,
        __chat_id__: str = None,
        __message_id__: str = None,
        __messages__: list = None,
        __model__: dict = None,
    ) -> dict:
        """
        Edit the latest image of this conversation (one the user attached or one you generated earlier), or combine several latest images into a new one. Unchanged areas stay as they are. Use it for "fix this", "change the color", "remove", "add", "make it a photo", turning a sketch into a finished picture, or putting a subject from one image into another.
        :param prompt: English editing instruction, 50-150 words. For a change to one image: imperative ("Change the jacket to dark green wool, ..."), describe only the change and its knock-on effects (shadows, reflections, what fills a removed area), and end with one clause naming what stays unchanged. For a new composition from several images: "Create a photograph of ..." and say what to take from the first image, the second image, and so on.
        :param images: How many of the latest images to use, 1 to 4, oldest first ("the first image" is the oldest of them); 1 for a normal edit.
        :param quality: "fast" (default) or "best" (much slower).
        :param seed: 0 for random.
        :return: Result of the edit
        """
        try:
            user = UserModel(**__user__) if __user__ else None
            count = max(1, min(MAX_REFERENCES, int(images or 1)))
            refs = (await _chat_images(__chat_id__, user, __messages__))[-count:]
            if not refs:
                return {"error": "No image found in this conversation. Ask the user to attach one or generate one first."}
            cfg = await get_image_config()
            seed = seed or random.randint(1, 2**50)
            wf = _build(EDIT_WORKFLOW, prompt, quality, seed)
            for i, ref in enumerate(refs):
                data, mime = await _image_bytes(ref, user)
                ext = mimetypes.guess_extension(mime) or ".png"
                up = await comfyui_upload_image(
                    ("image", (f"ref_{uuid.uuid4().hex[:8]}{ext}", data, mime)), cfg.COMFYUI_BASE_URL, cfg.COMFYUI_API_KEY
                )
                node = "20" if i == 0 else f"2{i}0"
                wf[node] = {"class_type": "LoadImage", "inputs": {"image": up.get("name")}}
                wf["14"]["inputs"][f"images.image{i}"] = [node, 0]
            q = quality if quality in QUALITY else "fast"
            label = f"правка по {len(refs)} картинк{'е' if len(refs) == 1 else 'ам'}, {q}, seed {seed}"
            return await self._run(wf, prompt, label, __request__, user, __event_emitter__, __chat_id__,
                                   __message_id__, __model__)
        except Exception as e:
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": f"Ошибка: {e}", "done": True}})
            return {"error": str(e)}
