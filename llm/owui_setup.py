"""Настройка моделей Open WebUI через API. Запуск: загрузить ключи из D:\gen\.env и python owui_setup.py"""
import json
import os
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:3000"
KEY = os.environ["OPENWEBUI_API_KEY"]
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(method, path, data=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        with op.open(req) as r:
            body = r.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": e.read().decode()[:300]}


SYS_THINK = open(r"D:\gen\prompts\system_prompt_en.txt", encoding="utf-8").read().strip()
SYS_PLAIN = SYS_THINK.replace("<|think|>", "").strip()
# основной Gemma — ещё и порядок размышлений: план, разбор по пунктам, самопроверка
SYS_DEEP = SYS_THINK + "\n\n" + open(r"D:\gen\prompts\thinking_plan_en.txt", encoding="utf-8").read().strip()
CAPS = {"web_search": True, "builtin_tools": True, "citations": True, "file_upload": True, "usage": True}
# Gemma 4 пишет вызовы инструментов в своём формате, который llama.cpp не разбирает, —
# поэтому поиск для неё делает сам Open WebUI (режим default)
GEMMA = {"temperature": 1.0, "top_p": 0.95, "top_k": 64, "function_calling": "default"}

models = [
    # id совпадает с моделью llama.cpp — это настройки самой базовой модели
    {"id": "gemma-4-26b-a4b", "base_model_id": None, "name": "Gemma 4 26B",
     "meta": {"description": "Gemma 4 26B-A4B (Google, QAT), контекст 256K. С размышлениями и поиском в интернете по умолчанию, понимает картинки, хороший русский.",
              "capabilities": {**CAPS, "vision": True},
              # кнопка «Веб-поиск» включена в каждом новом чате с этой моделью
              "defaultFeatureIds": ["web_search", "memory"]},
     # контекст 256K (пресет llama.cpp): сжатие беседы начинается с 200K, а не с глобальных 80K
     "params": {**GEMMA, "system": SYS_DEEP, "compact_token_threshold": 200000}},
    {"id": "gemma-4-26b-a4b-fast", "base_model_id": "gemma-4-26b-a4b", "name": "Gemma 4 26B (быстро)",
     "meta": {"description": "Gemma 4 без размышлений. Скрыта из выбора: служебная модель для поисковых запросов и заголовков.",
              "capabilities": {**CAPS, "vision": True}, "hidden": True},
     "params": {**GEMMA, "system": SYS_PLAIN}},
]

# свои инструменты из D:\llm\tools: id = имя файла, описание — из шапки файла
TOOLS = {"current_chat_search": "Поиск по текущей беседе", "flux_studio": "FLUX 3: картинки"}
for tool_id, name in TOOLS.items():
    content = open(rf"D:\llm\tools\{tool_id}.py", encoding="utf-8").read()
    desc = next((l.split(":", 1)[1].strip() for l in content.splitlines() if l.startswith("description:")), "")
    tool = {"id": tool_id, "name": name, "content": content, "meta": {"description": desc, "manifest": {}}}
    r = api("POST", f"/api/v1/tools/id/{tool_id}/update", tool)
    if isinstance(r, dict) and r.get("error"):
        r = api("POST", "/api/v1/tools/create", tool)
    print("инструмент", tool_id, "->", "OK" if isinstance(r, dict) and not r.get("error") else r)

# старый инструмент Z-Image (модель удалена 2026-10-24)
api("DELETE", "/api/v1/tools/id/zimage_studio/delete")

# у моделей из выбора: поиск по беседе и картинки через flux_studio (FLUX 3: генерация, правка, размер, самопроверка).
# Встроенные generate_image/edit_image (кнопка «Изображение») по умолчанию выключены, чтобы не было двух генераторов
CHAT_TOOLS = {"gemma-4-26b-a4b"}
for m in models:
    if m["id"] in CHAT_TOOLS:
        m["meta"]["toolIds"] = list(TOOLS)
        m["meta"].setdefault("defaultFeatureIds", [])
        if "memory" not in m["meta"]["defaultFeatureIds"]:
            m["meta"]["defaultFeatureIds"].append("memory")  # кнопка «Память» включена в новых чатах
        if "code_interpreter" not in m["meta"]["defaultFeatureIds"]:
            # «Интерпретатор кода» (Pyodide в браузере): считать слова, буквы и арифметику кодом, а не в уме
            m["meta"]["defaultFeatureIds"].append("code_interpreter")
    m["access_grants"] = []
    r = api("POST", "/api/v1/models/create", m)
    if isinstance(r, dict) and r.get("error"):
        r = api("POST", f"/api/v1/models/model/update?id={m['id']}", m)
    print(m["name"], "->", "OK" if isinstance(r, dict) and not r.get("error") else r)

# удалённые модели: gpt-oss (2026-10-24, файлы и пресеты тоже) и отдельная «длинная» Gemma — основная теперь сама 256K
for gone in ("gpt-oss-20b", "gpt-oss-20b-high", "gemma-4-26b-a4b-long"):
    api("POST", "/api/v1/models/model/delete", {"id": gone})

cfg = api("GET", "/api/v1/configs/models") or {}
cfg.update({"DEFAULT_MODELS": "gemma-4-26b-a4b",
            "MODEL_ORDER_LIST": ["gemma-4-26b-a4b"]})
r = api("POST", "/api/v1/configs/models", cfg)
print("модель по умолчанию ->", r.get("DEFAULT_MODELS") if isinstance(r, dict) else r)
print("в чате:", [m["name"] for m in (api("GET", "/api/models") or {}).get("data", [])])
