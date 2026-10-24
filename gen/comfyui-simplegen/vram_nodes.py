"""Узлы для общей видеокарты с llama.cpp (LLM в чате Open WebUI).

SimpleGenUnloadLLM — перед генерацией выгружает модели llama.cpp из видеопамяти
(файлы остаются в кэше Windows, следующая загрузка в чате идёт из RAM).
SimpleGenFreeVRAM — после генерации переносит модели ComfyUI в оперативную память,
чтобы LLM снова получила всю видеопамять.
"""
import json
import logging
import urllib.request

import comfy.model_management as mm

LLAMA_URL = "http://127.0.0.1:8080"
log = logging.getLogger("SimpleGen")
# локальный адрес — мимо системного прокси
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def unload_llama_models() -> list[str]:
    """Выгружает все загруженные модели маршрутизатора llama.cpp; возвращает их имена."""
    try:
        with _opener.open(f"{LLAMA_URL}/models", timeout=5) as r:
            models = json.load(r).get("data", [])
    except Exception as e:  # llama.cpp не запущен — выгружать нечего
        log.info("llama.cpp недоступен (%s), выгрузка не нужна", e)
        return []
    unloaded = []
    for m in models:
        status = (m.get("status") or {}).get("value")
        if status in ("loaded", "loading"):
            req = urllib.request.Request(f"{LLAMA_URL}/models/unload", data=json.dumps({"model": m["id"]}).encode(),
                                         headers={"Content-Type": "application/json"})
            try:
                _opener.open(req, timeout=30).read()
                unloaded.append(m["id"])
            except Exception as e:
                log.warning("не удалось выгрузить %s: %s", m["id"], e)
    if unloaded:
        log.info("выгружены из видеопамяти модели llama.cpp: %s", ", ".join(unloaded))
    return unloaded


class SimpleGenUnloadLLM:
    """Пропускает текст запроса насквозь, а перед этим освобождает видеопамять от LLM."""

    CATEGORY = "SimpleGen"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"text": ("STRING", {"multiline": True, "default": ""})}}

    @classmethod
    def IS_CHANGED(cls, text):
        return float("nan")  # выполнять каждый раз: LLM могла снова загрузиться между генерациями

    def run(self, text):
        unload_llama_models()
        return (text,)


class SimpleGenFreeVRAM:
    """Пропускает картинки насквозь и переносит модели ComfyUI из видеопамяти в RAM."""

    CATEGORY = "SimpleGen"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("images",)
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"images": ("IMAGE",)}}

    @classmethod
    def IS_CHANGED(cls, images):
        return float("nan")

    def run(self, images):
        mm.unload_all_models()
        mm.soft_empty_cache()
        return (images,)


NODE_CLASS_MAPPINGS = {"SimpleGenUnloadLLM": SimpleGenUnloadLLM, "SimpleGenFreeVRAM": SimpleGenFreeVRAM}
NODE_DISPLAY_NAME_MAPPINGS = {"SimpleGenUnloadLLM": "Выгрузить LLM (llama.cpp)", "SimpleGenFreeVRAM": "Освободить видеопамять"}
