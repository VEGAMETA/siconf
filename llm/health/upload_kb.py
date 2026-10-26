"""Загрузка Markdown-файлов клинических рекомендаций в базу знаний Open WebUI.

Запуск (ключ — из D:\\gen\\.env): python -X utf8 upload_kb.py [файл.md ...]
Без аргументов загружает все файлы из clinrec/, которых ещё нет в базе (сравнение по имени файла).
Эмбеддинги считает сам Open WebUI (bge-m3 на процессоре), поэтому файлы идут по одному и синхронно.
"""
import os
import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:3000"
NAME = "Клинические рекомендации Минздрава РФ"
DESCRIPTION = ("Действующие клинические рекомендации Минздрава России по распространённым заболеваниям взрослых и детей "
               "(cr.minzdrav.gov.ru): определение, диагностика, лечение, профилактика, информация для пациента.")
HEADERS = {"Authorization": f"Bearer {os.environ['OPENWEBUI_API_KEY']}"}
SESSION = requests.Session()
SESSION.trust_env = False  # Open WebUI локальный: без системного прокси


def knowledge_id():
    data = SESSION.get(f"{BASE}/api/v1/knowledge/", headers=HEADERS, timeout=60).json()
    items = data.get("items", data) if isinstance(data, dict) else data
    for kb in items:
        if kb.get("name") == NAME:
            return kb["id"]
    kb = SESSION.post(f"{BASE}/api/v1/knowledge/create", headers=HEADERS, timeout=60,
                      json={"name": NAME, "description": DESCRIPTION, "access_grants": []}).json()
    return kb["id"]


def existing_names(kb_id):
    names, page = set(), 1
    while True:
        data = SESSION.get(f"{BASE}/api/v1/knowledge/{kb_id}/files", headers=HEADERS, params={"page": page}, timeout=60).json()
        items = data.get("items", []) if isinstance(data, dict) else data
        names |= {(f.get("meta") or {}).get("name") or f.get("filename") for f in items}
        if not items or len(names) >= (data.get("total") or 0):
            return names
        page += 1


def upload(kb_id, path):
    with open(path, "rb") as fh:
        f = SESSION.post(f"{BASE}/api/v1/files/", headers=HEADERS, params={"process": "true", "process_in_background": "false"},
                         files={"file": (path.name, fh, "text/markdown")}, timeout=3600).json()
    if not f.get("id"):
        raise RuntimeError(f"загрузка: {f}")
    r = SESSION.post(f"{BASE}/api/v1/knowledge/{kb_id}/file/add", headers=HEADERS, json={"file_id": f["id"]}, timeout=3600)
    if r.status_code != 200:
        raise RuntimeError(f"добавление в базу: {r.status_code} {r.text[:200]}")


def main():
    kb_id = knowledge_id()
    files = [Path(a) for a in sys.argv[1:]] or sorted((Path(__file__).parent / "clinrec").glob("*.md"))
    have = existing_names(kb_id)
    todo = [p for p in files if p.name not in have]
    print(f"база {kb_id}: уже {len(have)} файлов, загрузить {len(todo)}", flush=True)
    for n, path in enumerate(todo, 1):
        t = time.time()
        try:
            upload(kb_id, path)
            print(f"[{n}/{len(todo)}] {path.name} — {time.time() - t:.0f} с", flush=True)
        except Exception as e:
            print(f"[{n}/{len(todo)}] ОШИБКА {path.name}: {e}", flush=True)


if __name__ == "__main__":
    main()
