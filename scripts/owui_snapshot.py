"""Снимок настроек Open WebUI в owui-config/ через API (ключи и пароли заменяются на <redacted>).
Запуск: загрузить ключи из D:\\gen\\.env и python -X utf8 scripts/owui_snapshot.py
"""
import json
import os
import pathlib
import re
import sqlite3
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:3000"
KEY = os.environ["OPENWEBUI_API_KEY"]
DB = r"D:\llm\open-webui\webui.db"
OUT = pathlib.Path(__file__).resolve().parent.parent / "owui-config"
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# файл -> адрес API
ENDPOINTS = {
    "audio_tts.json": "/api/v1/audio/config",
    "chats_compaction.json": "/api/v1/chats/config",
    "code_execution.json": "/api/v1/configs/code_execution",
    "images.json": "/api/v1/images/config",
    "models_defaults.json": "/api/v1/configs/models",
    "openai_connection.json": "/openai/config",
    "retrieval_web_search.json": "/api/v1/retrieval/config",
    "tasks.json": "/api/v1/tasks/config",
}
# «key» без приставки — это ключ поля узла ComfyUI в images.json, не секрет
SECRET = re.compile(r"api_?keys?|_keys?$|token|password|secret", re.I)
HARMLESS = {"", "local", "none"}  # заглушки, а не настоящие ключи


def get(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": f"Bearer {KEY}"})
    with op.open(req) as r:
        return json.load(r)


def redact(obj, key=""):
    if isinstance(obj, dict):
        return {k: redact(v, k) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v, key) for v in obj]
    if isinstance(obj, str) and SECRET.search(key) and obj.strip().lower() not in HARMLESS:
        return "<redacted>"
    return obj


def unpack(data):
    """Рабочие процессы ComfyUI Open WebUI хранит строкой JSON — в снимке они объектами, чтобы diff был читаемым."""
    if isinstance(data, dict):
        return {k: json.loads(v) if k.endswith("COMFYUI_WORKFLOW") and isinstance(v, str) and v.strip().startswith("{")
                else unpack(v) for k, v in data.items()}
    return data


def save(name, data):
    (OUT / name).write_text(json.dumps(redact(unpack(data)), ensure_ascii=False, indent=2), encoding="utf-8")
    print("снимок", name)


for name, path in ENDPOINTS.items():
    save(name, get(path))

# свои модели и переопределения базовых (Workspace → Models). /models/export отдаёт только производные модели,
# поэтому идём по списку /api/models: у моделей с настройками в базе есть поле info
models = []
for item in get("/api/models")["data"]:
    if not item.get("info"):
        continue
    m = get(f"/api/v1/models/model?id={urllib.parse.quote(item['id'])}")
    meta = dict(m.get("meta") or {}, profile_image_url=None, background_image_url=None)
    params = dict(m.get("params") or {})
    if params.get("system"):
        # промпт целиком лежит в prompts/, здесь только отметка о длине
        params["system"] = f"<prompts/system_prompt_en.txt (+ thinking_plan_en.txt у основной): {len(params['system'])} символов>"
    models.append({"id": m["id"], "name": m.get("name"), "base_model_id": m.get("base_model_id"),
                   "meta": meta, "params": params})
save("models.json", sorted(models, key=lambda m: m["id"]))

# память настраивается только в базе (таблица config)
with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as db:
    rows = db.execute("select key, value from config where key like 'memories.%' order by key").fetchall()
save("memories_db.json", {k: json.loads(v) if isinstance(v, str) else v for k, v in rows})
