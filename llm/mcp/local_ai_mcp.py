"""MCP-сервер «local-ai»: локальные возможности ПК для Claude (Claude Code, приложение Claude).

Инструменты:
  local_llm      — поручить задачу локальной Gemma 4 26B (llama.cpp через посредника think_proxy, 8081);
                   сервер сам читает файлы, в контекст Claude возвращается только результат
  web_search     — поиск через локальный SearXNG (127.0.0.1:8888)
  generate_image — картинка FLUX 3 через ComfyUI (127.0.0.1:8188), файл + уменьшенная копия для просмотра
  edit_image     — правка/объединение картинок с диска через FLUX 3

Запуск — stdio, его делает сам клиент MCP:
  claude mcp add --scope user local-ai -- D:\\llm\\mcp\\.venv\\Scripts\\python.exe D:\\llm\\mcp\\local_ai_mcp.py
"""
import asyncio
import io
import json
import logging
import pathlib
import random
import time
import uuid

import httpx
from mcp.server.mcpserver import Image, MCPServer
from PIL import Image as PILImage

LLM_URL = "http://127.0.0.1:8081/v1/chat/completions"   # think_proxy -> llama.cpp
LLM_MODEL = "gemma-4-26b-a4b"
SEARX_URL = "http://127.0.0.1:8888/search"
COMFY_URL = "http://127.0.0.1:8188"
COMFY_OUTPUT = pathlib.Path(r"D:\gen\ComfyUI_windows_portable\ComfyUI\output")
T2I_WORKFLOW = pathlib.Path(r"D:\llm\openwebui_flux3_t2i.json")
EDIT_WORKFLOW = pathlib.Path(r"D:\llm\openwebui_flux3_edit.json")
QUALITY = {  # по карточке модели BFL
    "fast": {"unet": "flux3-image-klein-int8-convrot.safetensors", "steps": 16, "cfg": 1.0},
    "best": {"unet": "flux3-image-klein-base-int8-convrot.safetensors", "steps": 50, "cfg": 3.5},
}
MAX_FILE_CHARS = 700_000   # ~175K токенов: контекст Gemma 256K, остаётся место на задачу и ответ
PREVIEW_SIDE = 768

HELPER_SYSTEM = (
    "You are a helper model working for another AI assistant, not for a human. Do exactly the task given. "
    "Be concise and factual; prefer lists of concrete findings with file names and line references when they help. "
    "If the input does not contain what is asked, say so plainly. Never invent facts. Answer in the language of the task."
)

mcp = MCPServer(
    "local-ai",
    instructions=(
        "Local resources of the user's PC (RTX 4060 Ti 16 GB). local_llm runs Gemma 4 26B locally: free, private, "
        "256K context, but much weaker than you. Use it to save your context on bulk work where a lot of input becomes "
        "a short output: summarizing or searching large files and logs (pass paths in files, do not paste content), "
        "drafts, translations, classification. Do not delegate hard reasoning or decisions; spot-check what it returns. "
        "generate_image/edit_image draw with FLUX 3 on the local GPU (the local LLM is unloaded meanwhile and reloads "
        "on its next call). web_search queries a local SearXNG instance."
    ),
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # без строки на каждый запрос
http = httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(1800, connect=10))


@mcp.tool()
async def local_llm(task: str, files: list[str] | None = None, think: bool = False, max_tokens: int = 4096) -> str:
    """Delegate a task to the local Gemma 4 26B model and get only its result back.

    Args:
        task: What to do, written as an instruction (e.g. "List every ERROR in these logs with its timestamp and likely cause").
        files: Absolute paths of text files the local model should read; the server reads them, so their content never enters your context.
        think: True lets the model reason before answering (slower, better for analysis); False for plain extraction, summaries, translation.
        max_tokens: Upper limit for the answer.
    """
    parts, total = [], 0
    for name in files or []:
        path = pathlib.Path(name)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return f"Cannot read {name}: {e}"
        total += len(text)
        if total > MAX_FILE_CHARS:
            return f"Files are too large for the local model (over {MAX_FILE_CHARS} characters); split the task."
        parts.append(f"=== file: {path} ===\n{text}")
    content = task + ("\n\n" + "\n\n".join(parts) if parts else "")
    body = {
        "model": LLM_MODEL, "max_tokens": max_tokens, "temperature": 1.0, "top_p": 0.95, "top_k": 64,
        "messages": [{"role": "system", "content": ("<|think|>" if think else "") + HELPER_SYSTEM},
                     {"role": "user", "content": content}],
    }
    if not think:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    t0 = time.time()
    try:
        r = await http.post(LLM_URL, json=body)
        r.raise_for_status()
    except httpx.HTTPError as e:
        return f"Local LLM is not reachable ({e}). Is the 'Local AI' stack running?"
    data = r.json()
    answer = (data["choices"][0]["message"].get("content") or "").strip()
    usage = data.get("usage") or {}
    return (f"{answer}\n\n[local Gemma: {usage.get('prompt_tokens', '?')} tokens in, "
            f"{usage.get('completion_tokens', '?')} out, {time.time() - t0:.0f} s]")


@mcp.tool()
async def web_search(query: str, count: int = 8) -> str:
    """Search the web through the user's local SearXNG instance and return titles, URLs and snippets.

    Args:
        query: Search query.
        count: Number of results (1-20).
    """
    try:
        r = await http.get(SEARX_URL, params={"q": query, "format": "json"})
        r.raise_for_status()
    except httpx.HTTPError as e:
        return f"SearXNG is not reachable ({e})."
    results = r.json().get("results", [])[:max(1, min(20, count))]
    if not results:
        return "No results."
    return "\n\n".join(f"{i}. {x.get('title', '')}\n{x.get('url', '')}\n{(x.get('content') or '').strip()}"
                       for i, x in enumerate(results, 1))


def _size(size):
    try:
        w, h = (int(v) for v in str(size).lower().replace("×", "x").split("x"))
    except ValueError:
        w, h = 1024, 1024
    scale = min(1.0, (1536 * 1536 / (w * h)) ** 0.5) if w * h > 0 else 1.0
    return max(256, round(w * scale / 16) * 16), max(256, round(h * scale / 16) * 16)


def _workflow(path, prompt, quality, seed):
    wf = json.loads(path.read_text(encoding="utf-8"))
    q = QUALITY.get(quality, QUALITY["fast"])
    wf["1"]["inputs"]["unet_name"] = q["unet"]
    wf["8"]["inputs"].update(steps=q["steps"], cfg=q["cfg"], seed=seed)
    wf["12"]["inputs"]["text"] = prompt
    wf["11"]["inputs"]["filename_prefix"] = "mcp/flux3"
    return wf


async def _render(wf, seed, label):
    """Поставить схему в очередь ComfyUI, дождаться, вернуть путь к файлу и уменьшенную копию."""
    try:
        r = await http.post(f"{COMFY_URL}/prompt", json={"prompt": wf, "client_id": uuid.uuid4().hex})
    except httpx.HTTPError as e:
        return [f"ComfyUI is not reachable ({e}). Is the 'Local AI' stack running?"]
    if r.status_code != 200:
        return [f"ComfyUI rejected the workflow: {r.text[:500]}"]
    prompt_id = r.json()["prompt_id"]
    t0 = time.time()
    while time.time() - t0 < 900:
        hist = (await http.get(f"{COMFY_URL}/history/{prompt_id}")).json().get(prompt_id)
        if hist:
            status = hist.get("status", {})
            if status.get("status_str") == "error":
                return [f"Generation failed: {json.dumps(status.get('messages', []))[:800]}"]
            for out in hist.get("outputs", {}).values():
                for img in out.get("images", []):
                    if img.get("type") == "output":
                        path = COMFY_OUTPUT / img.get("subfolder", "") / img["filename"]
                        preview = PILImage.open(path).convert("RGB")
                        w, h = preview.size
                        preview.thumbnail((PREVIEW_SIDE, PREVIEW_SIDE))
                        buf = io.BytesIO()
                        preview.save(buf, "JPEG", quality=85)
                        return [f"Saved {path} ({w}x{h}, {label}, seed {seed}, {time.time() - t0:.0f} s). "
                                "The preview below is downscaled.", Image(data=buf.getvalue(), format="jpeg")]
            if status.get("completed"):
                return ["Generation finished without an output image."]
        await asyncio.sleep(1.0)
    return ["Timed out after 15 minutes; the job may still be running in ComfyUI."]


@mcp.tool()
async def generate_image(prompt: str, size: str = "1024x1024", quality: str = "fast", seed: int = 0,
                         layout: list[dict] | None = None) -> list:
    """Generate an image with FLUX 3 Image Klein on the local GPU; saves a PNG and returns its path and a preview.

    The model needs a full scene caption, not a short request: one English prose paragraph of 100-350 words. Start with
    medium and style ("Full-color outdoor photograph, ...", "Studio photograph, ...", "Flat vector illustration, ..."),
    then scene, lighting and camera, then every subject with concrete colors, materials, state and frame-relative position
    (on the left, in the foreground). State absences as what is present ("a bare white wall"); put text that must appear
    in double quotes with its font, color and placement; describe unusual objects part by part. Compose first: one focal
    subject, 3-5 elements, reserved empty space for any text; keep rendered text short (small text gets misspelled).

    Args:
        prompt: The full English caption described above; with layout, cite each element by id at first mention ("a woman <woman_1>").
        size: WIDTHxHEIGHT, about 1 megapixel: "1024x1024", "832x1216" (portrait), "1216x832" (landscape), "1344x768" (wide).
        quality: "fast" (distilled, about 15-30 s) or "best" (base model, 50 steps, several times slower).
        seed: 0 for random; reuse a seed for a small variation of the same image.
        layout: Optional composition boxes, 2-6 items {"id": "woman_1", "bbox": [top, left, bottom, right], "desc": "..."} on a
            0-1000 grid (0,0 = top-left); one per main subject and per text block (ids like "Ru_Text_1", desc quoting the words).
    """
    seed = seed or random.randint(1, 2**50)
    w, h = _size(size)
    rows = [{"id": str(x["id"]), "bbox": [max(0, min(1000, int(v))) for v in x["bbox"]], "desc": str(x.get("desc", ""))}
            for x in layout or [] if isinstance(x, dict) and x.get("id") and isinstance(x.get("bbox"), list) and len(x["bbox"]) == 4]
    if rows:  # таблица рамок в формате улучшателя BFL
        prompt = f"{prompt.strip()} {json.dumps(rows, ensure_ascii=False)}"
    wf = _workflow(T2I_WORKFLOW, prompt, quality, seed)
    wf["7"]["inputs"].update(width=w, height=h, batch_size=1)
    wf["4"]["inputs"].update(width=w, height=h)
    return await _render(wf, seed, quality if quality in QUALITY else "fast")


@mcp.tool()
async def edit_image(prompt: str, images: list[str], quality: str = "fast", seed: int = 0) -> list:
    """Edit an image file, or combine up to 4 image files into a new image, with FLUX 3 on the local GPU.

    Args:
        prompt: English instruction, 50-150 words. For one image: an imperative that describes only the change, its knock-on
            effects (shadows, reflections, what fills a removed area) and ends with a clause naming what stays unchanged.
            For several images: "Create a photograph of ..." saying what to take from the first image, the second image, etc.
        images: Absolute paths of 1-4 image files; the output takes the size of the first one (about 1 megapixel).
        quality: "fast" or "best".
        seed: 0 for random.
    """
    if not images:
        return ["No images given."]
    seed = seed or random.randint(1, 2**50)
    wf = _workflow(EDIT_WORKFLOW, prompt, quality, seed)
    wf["11"]["inputs"]["filename_prefix"] = "mcp/flux3_edit"
    for i, name in enumerate(images[:4]):
        path = pathlib.Path(name)
        try:
            payload = path.read_bytes()
        except OSError as e:
            return [f"Cannot read {name}: {e}"]
        r = await http.post(f"{COMFY_URL}/upload/image", files={"image": (f"mcp_{uuid.uuid4().hex[:8]}{path.suffix}", payload)},
                            data={"type": "input"})
        if r.status_code != 200:
            return [f"Upload to ComfyUI failed: {r.text[:300]}"]
        node = "20" if i == 0 else f"2{i}0"
        wf[node] = {"class_type": "LoadImage", "inputs": {"image": r.json()["name"]}}
        wf["14"]["inputs"][f"images.image{i}"] = [node, 0]
    return await _render(wf, seed, f"edit of {len(images[:4])} image(s), {quality}")


if __name__ == "__main__":
    mcp.run("stdio")
