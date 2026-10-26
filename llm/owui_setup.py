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
# image_generation выключен: это встроенный генератор Open WebUI (кнопка «Изображение»); картинки делает свой инструмент
# flux_studio (create_image / edit_image), два генератора у модели только путают
CAPS = {"web_search": True, "builtin_tools": True, "citations": True, "file_upload": True, "usage": True, "image_generation": False}
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
# web_research — свой search_web (SearXNG с фильтром по времени + текст лучших страниц): функция с тем же именем
# занимает место встроенного search_web Open WebUI; встроенный fetch_url остаётся
TOOLS = {"current_chat_search": "Поиск по текущей беседе", "flux_studio": "FLUX 3: картинки",
         "web_research": "Поиск в интернете с чтением страниц",
         # Inline Visualizer 2.2.3 (github.com/Classic298/open-webui-plugins, BSD-3-Clause; файлы inline-visualizer-v2/tool.py и SKILL.md): графики и схемы прямо в чате;
         # навык visualize — его SKILL.md. Нужна пользовательская настройка «iframe Sandbox Allow Same Origin»
         "inline_visualizer": "Inline Visualizer",
         # Europe PMC (обзоры, метаанализы, руководства с аннотациями) и openFDA (инструкции к препаратам, через прокси)
         "medical_research": "Медицинская литература и инструкции"}
for tool_id, name in TOOLS.items():
    content = open(rf"D:\llm\tools\{tool_id}.py", encoding="utf-8").read()
    desc = next((l.split(":", 1)[1].strip() for l in content.splitlines() if l.startswith("description:")), "")
    tool = {"id": tool_id, "name": name, "content": content, "meta": {"description": desc, "manifest": {}}}
    r = api("POST", f"/api/v1/tools/id/{tool_id}/update", tool)
    if isinstance(r, dict) and r.get("error"):
        r = api("POST", "/api/v1/tools/create", tool)
    print("инструмент", tool_id, "->", "OK" if isinstance(r, dict) and not r.get("error") else r)

# навыки (Skills) из D:\gen\prompts\skills: модель видит только их названия и описания и читает инструкцию
# целиком через view_skill, когда нужно (например, правила картинок — перед первой генерацией)
import glob
import pathlib
import re

for path in sorted(glob.glob(r"D:\gen\prompts\skills\*.md")):
    text = open(path, encoding="utf-8").read()
    front = re.match(r"---\n(.*?)\n---\n", text, re.S)
    meta = dict(line.split(":", 1) for line in front.group(1).splitlines() if ":" in line) if front else {}
    skill_id = pathlib.Path(path).stem
    skill = {"id": skill_id, "name": meta.get("name", skill_id).strip(), "description": meta.get("description", "").strip(),
             "content": text[front.end():].strip() if front else text}
    r = api("POST", f"/api/v1/skills/id/{skill_id}/update", skill)
    if isinstance(r, dict) and r.get("error"):
        r = api("POST", "/api/v1/skills/create", skill)
    print("навык", skill_id, "->", "OK" if isinstance(r, dict) and not r.get("error") else r)

# функции-фильтры из D:\llm\functions (id = имя файла): image_skill_auto включает навык image-generation в тех
# сообщениях, где просят картинку. Фильтр должен быть активен и привязан к модели (meta.filterIds)
FILTERS = []
for path in sorted(glob.glob(r"D:\llm\functions\*.py")):
    content = open(path, encoding="utf-8").read()
    fid = pathlib.Path(path).stem
    title = next((l.split(":", 1)[1].strip() for l in content.splitlines() if l.startswith("title:")), fid)
    desc = next((l.split(":", 1)[1].strip() for l in content.splitlines() if l.startswith("description:")), "")
    fn = {"id": fid, "name": title, "content": content, "meta": {"description": desc, "manifest": {}}}
    r = api("POST", f"/api/v1/functions/id/{fid}/update", fn)
    if isinstance(r, dict) and r.get("error"):
        r = api("POST", "/api/v1/functions/create", fn)
    state = api("GET", f"/api/v1/functions/id/{fid}") or {}
    if isinstance(state, dict) and not state.get("is_active"):
        state = api("POST", f"/api/v1/functions/id/{fid}/toggle")
    FILTERS.append(fid)
    print("фильтр", fid, "->", "активен" if isinstance(state, dict) and state.get("is_active") else state)

# старый инструмент Z-Image (модель удалена 2026-10-24)
api("DELETE", "/api/v1/tools/id/zimage_studio/delete")

# у моделей из выбора: поиск по беседе и картинки через flux_studio (FLUX 3: генерация, правка, размер, самопроверка).
# Встроенные generate_image/edit_image (кнопка «Изображение») по умолчанию выключены, чтобы не было двух генераторов
CHAT_TOOLS = {"gemma-4-26b-a4b"}
KNOWLEDGE = {"Клинические рекомендации Минздрава РФ"}
for m in models:
    if m["id"] in CHAT_TOOLS:
        m["meta"]["toolIds"] = list(TOOLS)
        m["meta"]["filterIds"] = list(FILTERS)
        m["meta"].setdefault("defaultFeatureIds", [])
        if "memory" not in m["meta"]["defaultFeatureIds"]:
            m["meta"]["defaultFeatureIds"].append("memory")  # кнопка «Память» включена в новых чатах
        if "code_interpreter" not in m["meta"]["defaultFeatureIds"]:
            # «Интерпретатор кода» (Pyodide в браузере): считать слова, буквы и арифметику кодом, а не в уме
            m["meta"]["defaultFeatureIds"].append("code_interpreter")
        # базы знаний (D:\llm\health): модель видит только их названия и ищет по ним встроенными инструментами
        # (query_knowledge_files и т. п.), в контекст целиком они не вставляются
        kbs = api("GET", "/api/v1/knowledge/") or {}
        kbs = kbs.get("items", []) if isinstance(kbs, dict) else kbs
        m["meta"]["knowledge"] = [{"type": "collection", "id": kb["id"], "name": kb["name"]}
                                  for kb in kbs if kb.get("name") in KNOWLEDGE]
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
