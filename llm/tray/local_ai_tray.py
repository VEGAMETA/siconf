"""Local AI в трее: запускает все службы без окон, показывает их состояние и даёт управлять ими с одной иконки.

Службы: SearXNG (Docker в WSL Debian), llama.cpp, think_proxy, Piper TTS, ComfyUI, Open WebUI.
Журналы — D:\\llm\\logs\\<служба>.log (перезаписываются при каждом запуске службы).
Запуск без консоли: pythonw.exe local_ai_tray.py (ярлык «Local AI» в D:\\shortcuts).
"""
import os
import socket
import subprocess
import threading
import time
import urllib.request
import webbrowser

import psutil
import pystray
from PIL import Image, ImageDraw

LLM, GEN = r"D:\llm", r"D:\gen"
LOGS = os.path.join(LLM, "logs")
ICON = os.path.join(LLM, "icons", "local_ai.png")
CHAT_URL, COMFY_URL = "http://127.0.0.1:3000", "http://127.0.0.1:8188"
NO_WINDOW = 0x08000000
LOCK_PORT = 8099  # одна копия приложения: второй запуск просто открывает чат

OWUI_ENV = {
    "DATA_DIR": r"D:\llm\open-webui", "PYTHONUTF8": "1", "OPENAI_API_BASE_URL": "http://127.0.0.1:8081/v1",
    "OPENAI_API_KEY": "local", "ENABLE_OLLAMA_API": "false",
    # SSRF-защита Open WebUI режет соединения через прокси на 127.0.0.1 — в интернет напрямую
    "NO_PROXY": "*", "no_proxy": "*",
}

# имя, порт для проверки, команда, рабочая папка, доп. окружение, шаблон командной строки для поиска «чужих» копий
SERVICES = [
    {"key": "searxng", "name": "Поиск SearXNG", "port": 8888,
     "cmd": ["wsl.exe", "-d", "Debian", "-u", "root", "--exec", "sh", "-c",
             "docker start searxng >/dev/null 2>&1; exec sleep infinity"],  # держит Debian живым, пока работает
     "cwd": LLM, "match": "sleep infinity"},
    {"key": "llama", "name": "Gemma (llama.cpp)", "port": 8080,
     "cmd": [os.path.join(LLM, r"llama.cpp\llama-server.exe"), "--models-preset", "models.ini", "--models-max", "1",
             "--host", "127.0.0.1", "--port", "8080"], "cwd": LLM, "match": "llama-server"},
    {"key": "proxy", "name": "Посредник think_proxy", "port": 8081,
     "cmd": [os.path.join(LLM, r"proxy\.venv\Scripts\python.exe"), "think_proxy.py"],
     "cwd": os.path.join(LLM, "proxy"), "match": "think_proxy.py"},
    {"key": "tts", "name": "Озвучка Piper", "port": 5005,
     "cmd": [os.path.join(LLM, r"tts\.venv\Scripts\python.exe"), os.path.join(LLM, r"tts\server.py")],
     "cwd": os.path.join(LLM, "tts"), "match": r"tts.server\.py"},
    {"key": "comfy", "name": "ComfyUI (картинки, видео)", "port": 8188,
     "cmd": [os.path.join(GEN, r"ComfyUI_windows_portable\python_embeded\python.exe"), "-s", r"ComfyUI\main.py",
             "--windows-standalone-build", "--enable-manager", "--listen", "0.0.0.0", "--port", "8188", "--disable-auto-launch"],
     "cwd": os.path.join(GEN, "ComfyUI_windows_portable"), "match": r"ComfyUI.main\.py"},
    {"key": "owui", "name": "Open WebUI (чат)", "port": 3000,
     "cmd": [os.path.expanduser(r"~\.local\bin\open-webui.exe"), "serve", "--host", "0.0.0.0", "--port", "3000"],
     "cwd": LLM, "env": OWUI_ENV, "match": "open-webui"},
]

procs = {}          # key -> Popen запущенной нами службы
lock = threading.Lock()
state = {"stopping": False}


def port_open(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def running(svc):
    return port_open(svc["port"])


def kill_tree(pid):
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except psutil.Error:
        pass


def find_external(svc):
    """Копии службы, запущенные не нами (например, старыми батниками)."""
    import re
    pat = re.compile(svc["match"])
    names = {"llama-server.exe", "open-webui.exe", "python.exe", "pythonw.exe", "wsl.exe"}
    out = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if p.info["name"] in names and p.info["cmdline"] and pat.search(" ".join(p.info["cmdline"])):
                if p.pid != os.getpid():
                    out.append(p.pid)
        except psutil.Error:
            pass
    return out


def start(svc):
    with lock:
        if svc["key"] in procs and procs[svc["key"]].poll() is None:
            return
        # для SearXNG важен не порт, а «якорь»: без живого wsl.exe WSL через минуту усыпит Debian вместе с поиском
        if (find_external(svc) if svc["key"] == "searxng" else running(svc)):
            return
        env = dict(os.environ, **svc.get("env", {}))
        log = open(os.path.join(LOGS, f"{svc['key']}.log"), "w", encoding="utf-8", errors="replace")
        procs[svc["key"]] = subprocess.Popen(svc["cmd"], cwd=svc["cwd"], env=env, stdout=log, stderr=subprocess.STDOUT,
                                             stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)


def stop(svc):
    with lock:
        p = procs.pop(svc["key"], None)
        if p and p.poll() is None:
            kill_tree(p.pid)
        for pid in find_external(svc):
            kill_tree(pid)


def restart(svc):
    stop(svc)
    time.sleep(1.5)
    start(svc)


def start_all(open_chat=False):
    for svc in SERVICES:
        start(svc)
        time.sleep(0.5)
    if open_chat:
        for _ in range(240):  # до 2 минут ждём Open WebUI
            if port_open(3000):
                break
            time.sleep(0.5)
        webbrowser.open(CHAT_URL)


def free_memory():
    """ComfyUI сбрасывает модели и из видеопамяти, и из RAM; llama.cpp выгружает Gemma (загрузится при следующем запросе)."""
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    msgs = []
    try:
        req = urllib.request.Request(f"{COMFY_URL}/free", data=b'{"unload_models": true, "free_memory": true}',
                                     headers={"Content-Type": "application/json"})
        op.open(req, timeout=10)
        msgs.append("ComfyUI: модели выгружены")
    except Exception:
        msgs.append("ComfyUI: не отвечает")
    try:
        import json
        data = json.load(op.open("http://127.0.0.1:8080/models", timeout=5))
        for m in data.get("data", []):
            if (m.get("status") or {}).get("value") == "loaded":
                req = urllib.request.Request("http://127.0.0.1:8080/models/unload", data=json.dumps({"model": m["id"]}).encode(),
                                             headers={"Content-Type": "application/json"})
                op.open(req, timeout=30)
                msgs.append(f"Gemma выгружена ({m['id']})")
    except Exception:
        msgs.append("llama.cpp: не отвечает")
    return "; ".join(msgs)


def make_icon(color):
    img = Image.open(ICON).convert("RGBA").resize((64, 64), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    d.ellipse((40, 40, 63, 63), fill=(30, 30, 30, 255))
    d.ellipse((43, 43, 60, 60), fill=color)
    return img


ICONS = {"ok": make_icon((60, 200, 90, 255)), "partial": make_icon((240, 190, 40, 255)), "off": make_icon((140, 140, 140, 255))}


def status_text():
    up = [s for s in SERVICES if running(s)]
    return up, f"Local AI: работает {len(up)} из {len(SERVICES)}"


def build_menu(icon):
    def svc_item(svc):
        return pystray.MenuItem(
            lambda item, s=svc: f"{'●' if running(s) else '○'}  {s['name']}",
            pystray.Menu(
                pystray.MenuItem("Перезапустить", lambda: threading.Thread(target=restart, args=(svc,), daemon=True).start()),
                pystray.MenuItem("Остановить", lambda: threading.Thread(target=stop, args=(svc,), daemon=True).start()),
                pystray.MenuItem("Журнал", lambda: os.startfile(os.path.join(LOGS, f"{svc['key']}.log"))),
            ))

    def on_free(icon_, item):
        icon_.notify(free_memory(), "Local AI")

    def on_quit(icon_, item):
        state["stopping"] = True
        for svc in reversed(SERVICES):
            stop(svc)
        icon_.stop()

    return pystray.Menu(
        pystray.MenuItem("Открыть чат", lambda: webbrowser.open(CHAT_URL), default=True),
        pystray.MenuItem("Открыть ComfyUI", lambda: webbrowser.open(COMFY_URL)),
        pystray.MenuItem("Страница для телефона (/simple)", lambda: webbrowser.open(COMFY_URL + "/simple")),
        pystray.Menu.SEPARATOR,
        *[svc_item(s) for s in SERVICES],
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Запустить всё", lambda: threading.Thread(target=start_all, daemon=True).start()),
        pystray.MenuItem("Освободить память (выгрузить модели)", on_free),
        pystray.MenuItem("Папка журналов", lambda: os.startfile(LOGS)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Остановить всё и выйти", on_quit),
    )


def monitor(icon):
    last = None
    while not state["stopping"]:
        up, text = status_text()
        kind = "ok" if len(up) == len(SERVICES) else ("off" if not up else "partial")
        if kind != last:
            icon.icon = ICONS[kind]
            last = kind
        icon.title = text
        icon.update_menu()
        time.sleep(3)


def main():
    os.makedirs(LOGS, exist_ok=True)
    guard = socket.socket()
    try:
        guard.bind(("127.0.0.1", LOCK_PORT))
    except OSError:
        webbrowser.open(CHAT_URL)  # уже запущено — просто открыть чат
        return
    icon = pystray.Icon("local_ai", ICONS["off"], "Local AI: запуск…")
    icon.menu = build_menu(icon)

    def setup(icon_):
        icon_.visible = True
        threading.Thread(target=monitor, args=(icon_,), daemon=True).start()
        threading.Thread(target=start_all, kwargs={"open_chat": True}, daemon=True).start()

    icon.run(setup=setup)


if __name__ == "__main__":
    main()
