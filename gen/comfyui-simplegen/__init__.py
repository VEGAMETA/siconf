"""Простая мобильная страница генерации видео: http://<адрес>:8188/simple

Отдаёт simple.html (процесс собирается в браузере и уходит в стандартный /prompt ComfyUI),
умеет удалять видео страницы из истории и с диска, и добавляет узлы для общей с llama.cpp
видеокарты (vram_nodes.py) — их использует генерация картинок из Open WebUI.
"""
import os
import re

import folder_paths
from aiohttp import web
from server import PromptServer

_PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simple.html")
# только файлы, которые создаёт сама страница: simple/wan_00001.mp4, simple/ltx_00002-audio.mp4 и их .png
_OWN = re.compile(r"^(wan|ltx)_\d+(-audio)?\.(mp4|png)$")
routes = PromptServer.instance.routes


def _simple_dir():
    return os.path.join(folder_paths.get_output_directory(), "simple")


def _delete_files(filename):
    """Удаляет видео и его спутники (.png с процессом, вариант без звука)."""
    stem = re.sub(r"(-audio)?\.(mp4|png)$", "", filename)
    removed = []
    for name in (f"{stem}.mp4", f"{stem}-audio.mp4", f"{stem}.png"):
        path = os.path.join(_simple_dir(), name)
        if _OWN.match(name) and os.path.isfile(path):
            os.remove(path)
            removed.append(name)
    return removed


@routes.get("/simple")
async def simple_page(request):
    return web.FileResponse(_PAGE, headers={"Cache-Control": "no-cache"})


@routes.post("/simple/delete")
async def simple_delete(request):
    data = await request.json()
    filename = str(data.get("filename", ""))
    if not _OWN.match(filename):
        return web.json_response({"error": "можно удалять только видео этой страницы"}, status=400)
    removed = _delete_files(filename)
    prompt_id = data.get("prompt_id")
    if prompt_id:
        PromptServer.instance.prompt_queue.delete_history_item(str(prompt_id))
    return web.json_response({"removed": removed})


@routes.post("/simple/clear")
async def simple_clear(request):
    removed = []
    if os.path.isdir(_simple_dir()):
        for name in os.listdir(_simple_dir()):
            if _OWN.match(name):
                os.remove(os.path.join(_simple_dir(), name))
                removed.append(name)
    queue = PromptServer.instance.prompt_queue
    for prompt_id, entry in list(queue.get_history().items()):
        extra = entry.get("prompt", [None] * 4)[3] or {}
        if "simplegen" in extra:
            queue.delete_history_item(prompt_id)
    return web.json_response({"removed": len(removed)})


from .vram_nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS  # noqa: E402,F401  узлы для общей с LLM видеокарты
