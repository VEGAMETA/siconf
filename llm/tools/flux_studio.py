"""
title: FLUX 3: картинки
description: Генерация и редактирование картинок в ComfyUI (FLUX 3 Image Klein). Два режима: готовая подпись от модели или короткое задание, которое разворачивает официальный улучшатель запросов BFL. Модель видит уменьшенную копию результата для самопроверки.
author: local
version: 0.2.0
"""

import asyncio
import base64
import io
import json
import mimetypes
import pathlib
import random
import uuid

import aiofiles
import aiohttp
from open_webui.models.chats import Chats
from open_webui.models.files import Files
from open_webui.models.users import UserModel
from open_webui.routers.images import upload_image
from open_webui.storage.provider import Storage
from open_webui.utils.chat_id import is_saved_chat_id
from PIL import Image

COMFY = "http://127.0.0.1:8188"
T2I_WORKFLOW = pathlib.Path(r"D:\llm\openwebui_flux3_t2i.json")
EDIT_WORKFLOW = pathlib.Path(r"D:\llm\openwebui_flux3_edit.json")
PROMPTS = pathlib.Path(r"D:\gen\prompts\official")
# официальный улучшатель запросов BFL (Qwen3.5-9B): разворачивает короткое задание в подпись «на языке FLUX»
UPSAMPLER = "qwen3.5_9b_flux3_prompt_upsampler_int8_convrot.safetensors"
# quality (по карточке модели BFL): fast — дистиллированная (16 шагов, без CFG); best — базовая (50 шагов, CFG 3.5), примерно вшестеро дольше
QUALITY = {
    "fast": {"unet": "flux3-image-klein-int8-convrot.safetensors", "steps": 16, "cfg": 1.0},
    "best": {"unet": "flux3-image-klein-base-int8-convrot.safetensors", "steps": 50, "cfg": 3.5},
}
MIN_PIXELS, MAX_PIXELS = 512 * 512, 1536 * 1536
MAX_REFERENCES = 4
PREVIEW_SIDE = 768  # уменьшенная копия результата, которую видит сама модель
TIMEOUT = 900


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


def _ratio(w, h):
    from math import gcd
    g = gcd(w, h)
    return f"{w // g}:{h // g}"


def _build(path, prompt, quality, seed):
    wf = json.loads(path.read_text(encoding="utf-8"))
    q = QUALITY.get(quality, QUALITY["fast"])
    wf["1"]["inputs"]["unet_name"] = q["unet"]
    wf["8"]["inputs"].update(steps=q["steps"], cfg=q["cfg"], seed=seed)
    wf["12"]["inputs"]["text"] = prompt
    return wf


def _add_upsampler(wf, brief, system_file, image_node=None):
    """Задание -> улучшатель BFL (TextGenerate) -> подпись в узел 12; параметры как в официальных схемах BFL."""
    wf.update({
        "30": {"class_type": "CLIPLoader", "inputs": {"clip_name": UPSAMPLER, "type": "flux3", "device": "default"}},
        "31": {"class_type": "PrimitiveStringMultiline",
               "inputs": {"value": (PROMPTS / system_file).read_text(encoding="utf-8")}},
        "32": {"class_type": "TextGenerate", "inputs": {
            "clip": ["30", 0], "prompt": brief, "max_length": 3584,
            "sampling_mode": "on", "sampling_mode.temperature": 1.0, "sampling_mode.top_k": 1, "sampling_mode.top_p": 0.95,
            "sampling_mode.min_p": 0.0, "sampling_mode.repetition_penalty": 1.0, "sampling_mode.seed": 7,
            "thinking": False, "use_default_template": True, "system_prompt": ["31", 0], "mtp": "off"}},
        "33": {"class_type": "PreviewAny", "inputs": {"source": ["32", 0]}},
    })
    if image_node:
        wf["32"]["inputs"]["image"] = [image_node, 0]
    wf["12"]["inputs"]["text"] = ["32", 0]


def _with_layout(prompt, layout):
    """Подпись + таблица рамок в формате улучшателя BFL: «подпись [{"id","bbox","desc"}, ...]»."""
    rows = []
    for item in layout or []:
        if not isinstance(item, dict) or not item.get("id") or not isinstance(item.get("bbox"), list) or len(item["bbox"]) != 4:
            continue
        bbox = [max(0, min(1000, int(v))) for v in item["bbox"]]
        rows.append({"id": str(item["id"]), "bbox": bbox, "desc": str(item.get("desc", ""))})
    return f"{prompt.strip()} {json.dumps(rows, ensure_ascii=False)}" if rows else prompt


def _preview(data):
    """JPEG-копия до PREVIEW_SIDE по большей стороне как data:-URL."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((PREVIEW_SIDE, PREVIEW_SIDE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


async def _comfy(session, wf):
    """Поставить схему в очередь, дождаться; вернуть [(байты, mime)] готовых картинок и подпись улучшателя."""
    async with session.post(f"{COMFY}/prompt", json={"prompt": wf, "client_id": uuid.uuid4().hex}) as r:
        if r.status != 200:
            raise RuntimeError(f"ComfyUI отклонил схему: {(await r.text())[:500]}")
        prompt_id = (await r.json())["prompt_id"]
    loop = asyncio.get_running_loop()
    deadline = loop.time() + TIMEOUT
    while loop.time() < deadline:
        async with session.get(f"{COMFY}/history/{prompt_id}") as r:
            hist = (await r.json()).get(prompt_id)
        status = (hist or {}).get("status", {})
        if status.get("status_str") == "error":
            raise RuntimeError(f"ComfyUI: ошибка генерации {json.dumps(status.get('messages', []), ensure_ascii=False)[:500]}")
        if hist and status.get("completed"):
            images, caption = [], None
            for out in hist.get("outputs", {}).values():
                text = out.get("text")
                if text:
                    caption = text[0] if isinstance(text, list) else text
                for img in out.get("images", []):
                    if img.get("type") != "output":
                        continue
                    params = {"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": "output"}
                    async with session.get(f"{COMFY}/view", params=params) as v:
                        images.append((await v.read(), v.headers.get("Content-Type", "image/png")))
            return images, caption
        await asyncio.sleep(1.0)
    raise RuntimeError("ComfyUI не закончил за 15 минут")


async def _upload_ref(session, data, mime):
    form = aiohttp.FormData()
    ext = mimetypes.guess_extension(mime) or ".png"
    form.add_field("image", data, filename=f"ref_{uuid.uuid4().hex[:8]}{ext}", content_type=mime)
    form.add_field("type", "input")
    async with session.post(f"{COMFY}/upload/image", data=form) as r:
        r.raise_for_status()
        return (await r.json())["name"]


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
    async def _run(self, wf, label, request, user, emit, chat_id, message_id, model, session, brief_used):
        if emit:
            note = " (улучшатель BFL: первый запуск дольше)" if brief_used else ""
            await emit({"type": "status", "data": {"description": f"Рисую: {label}{note}", "done": False}})
        outputs, caption = await _comfy(session, wf)
        if not outputs:
            raise RuntimeError("ComfyUI не вернул картинку")
        images, previews = [], []
        for data, content_type in outputs:
            previews.append(_preview(data))
            _, image_file = await upload_image(request, data, content_type, {"prompt": caption or label}, user)
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
            "The attached preview is what was actually generated: check it as the image-generation skill says "
            "(focal subject, requested elements, text spelling, scale and proportions, hands and faces). Say in one line "
            "which size and mode you used, and if something is clearly wrong, say so plainly and offer a fix.",
            "seed": wf["8"]["inputs"]["seed"],
        }
        if caption:
            result["caption"] = caption  # что именно нарисовано: пригодится для точной правки
        vision = ((model or {}).get("info") or {}).get("meta", {}).get("capabilities", {}).get("vision")
        if vision and previews:
            result["preview"] = previews[0]
        else:
            result["message"] = ("The image is already visible to the user in the chat; do not embed it again. "
                                 "Say in one line which size and mode you used.")
        return result

    async def create_image(
        self,
        prompt: str = "",
        brief: str = "",
        size: str = "1024x1024",
        quality: str = "fast",
        seed: int = 0,
        layout: list = None,
        __request__=None,
        __user__: dict = None,
        __event_emitter__=None,
        __chat_id__: str = None,
        __message_id__: str = None,
        __model__: dict = None,
    ) -> dict:
        """
        Generate a new image with FLUX 3. Use it whenever the user asks to draw, generate or show a picture, or to come up with a visual thing (cover, poster, logo, avatar, banner, illustration). Pass either brief or prompt (see the image-generation skill for which).
        :param brief: Short art-director brief, 60-150 words, any language: purpose and audience, what the image is about, the one focal subject and key moment or symbol, 3-5 elements, composition and where text goes, exact text in quotes, palette and mood, real sizes of important objects. The official BFL prompt writer turns it into the full FLUX caption. Best for covers, posters, banners and complex scenes. First use takes 1-4 minutes longer.
        :param prompt: Full English caption written by you, 100-350 words of prose: medium and style first ("Full-color outdoor photograph, ..."), then scene, lighting and camera, then each subject with colors, materials, state, size and frame-relative position; text in double quotes with typography and placement. With layout, cite each element by id in angle brackets ("a woman <woman_1>"). Fast; good for simple images.
        :param size: WIDTHxHEIGHT: "832x1216" portrait, book cover or full-height figure, "1216x832" landscape or room, "1344x768" wide banner or thumbnail, "1024x1024" square or single object; the size the user asks for if any.
        :param quality: "fast" (default, about 10-15 seconds) or "best" (slower base model, about 6 times longer; only when the user asks for maximum quality).
        :param seed: 0 for a new random image; reuse the previous seed only for a small variation of the same image.
        :param layout: Only with prompt. Composition boxes, 2-6 items {"id": "woman_1", "bbox": [top, left, bottom, right], "desc": "..."} on a 0-1000 grid (0,0 = top-left), one per main subject and per text block (text ids like "Ru_Text_1", desc quoting the exact words).
        :return: Result of the generation
        """
        session = None
        try:
            if not (brief or prompt).strip():
                return {"error": "Pass brief (short brief for the BFL prompt writer) or prompt (full caption)."}
            seed = seed or random.randint(1, 2**50)
            w, h = _size(size)
            wf = _build(T2I_WORKFLOW, _with_layout(prompt, layout) if prompt else "", quality, seed)
            if brief.strip():
                _add_upsampler(wf, f"TARGET CANVAS: {_ratio(w, h)}\n{brief.strip()}", "flux3_upsampler_t2i.txt")
            wf["7"]["inputs"].update(width=w, height=h, batch_size=1)
            wf["4"]["inputs"].update(width=w, height=h)
            q = quality if quality in QUALITY else "fast"
            mode = "задание → BFL" if brief.strip() else "подпись"
            label = f"{w}x{h}, {q}, {mode}, seed {seed}"
            user = UserModel(**__user__) if __user__ else None
            session = aiohttp.ClientSession(trust_env=False)
            return await self._run(wf, label, __request__, user, __event_emitter__, __chat_id__,
                                   __message_id__, __model__, session, bool(brief.strip()))
        except Exception as e:
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": f"Ошибка: {e}", "done": True}})
            return {"error": str(e)}
        finally:
            if session:
                await session.close()

    async def edit_image(
        self,
        prompt: str = "",
        brief: str = "",
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
        Edit the latest image of this conversation (one the user attached or one you generated earlier), or combine several latest images into a new one. Unchanged areas stay as they are. Use it for "fix this", "change the color", "remove", "add", "make it a photo", turning a sketch into a finished picture, fixing misspelled text, or putting a subject from one image into another. Pass either brief or prompt.
        :param brief: Short edit request in any language (e.g. "make the ring a realistic small size, keep everything else"); the official BFL prompt writer looks at the image and expands it into a precise instruction. Best when the change needs to fit the existing picture.
        :param prompt: English editing instruction written by you, 50-150 words. For a change to one image: imperative ("Change the jacket to dark green wool, ..."), describe only the change and its knock-on effects (shadows, reflections, what fills a removed area), and end with one clause naming what stays unchanged. For a new composition from several images: "Create a photograph of ..." and say what to take from the first image, the second image, and so on.
        :param images: How many of the latest images to use, 1 to 4, oldest first ("the first image" is the oldest of them); 1 for a normal edit.
        :param quality: "fast" (default) or "best" (much slower).
        :param seed: 0 for random.
        :return: Result of the edit
        """
        session = None
        try:
            if not (brief or prompt).strip():
                return {"error": "Pass brief (short edit request) or prompt (full English instruction)."}
            user = UserModel(**__user__) if __user__ else None
            count = max(1, min(MAX_REFERENCES, int(images or 1)))
            refs = (await _chat_images(__chat_id__, user, __messages__))[-count:]
            if not refs:
                return {"error": "No image found in this conversation. Ask the user to attach one or generate one first."}
            session = aiohttp.ClientSession(trust_env=False)
            seed = seed or random.randint(1, 2**50)
            wf = _build(EDIT_WORKFLOW, prompt, quality, seed)
            for i, ref in enumerate(refs):
                data, mime = await _image_bytes(ref, user)
                node = "20" if i == 0 else f"2{i}0"
                wf[node] = {"class_type": "LoadImage", "inputs": {"image": await _upload_ref(session, data, mime)}}
                wf["14"]["inputs"][f"images.image{i}"] = [node, 0]
            if brief.strip():
                # улучшатель видит первую картинку и пишет инструкцию по официальному шаблону BFL для правок
                request_text = ("Reference images follow in order (the first image, the second image, ...).\n"
                                f"User request: {brief.strip()}\nOutput the caption.")
                _add_upsampler(wf, request_text, "flux3_upsampler_edit.txt", image_node="20")
            q = quality if quality in QUALITY else "fast"
            mode = "задание → BFL" if brief.strip() else "инструкция"
            label = f"правка по {len(refs)} картинк{'е' if len(refs) == 1 else 'ам'}, {q}, {mode}, seed {seed}"
            return await self._run(wf, label, __request__, user, __event_emitter__, __chat_id__,
                                   __message_id__, __model__, session, bool(brief.strip()))
        except Exception as e:
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": f"Ошибка: {e}", "done": True}})
            return {"error": str(e)}
        finally:
            if session:
                await session.close()
