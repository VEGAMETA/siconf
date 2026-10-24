@echo off
rem Open WebUI: chat with local models + web search. Phone: http://192.168.0.109:3000
rem Needs start_llm.bat (llama.cpp on 127.0.0.1:8080) and start_proxy.bat (think proxy on 127.0.0.1:8081) running.
set DATA_DIR=D:\llm\open-webui
rem Python in UTF-8 mode: Open WebUI writes files without an explicit encoding, on Windows
rem that breaks on Cyrillic (e.g. text-to-speech cache) without this
set PYTHONUTF8=1
set OPENAI_API_BASE_URL=http://127.0.0.1:8081/v1
set OPENAI_API_KEY=local
set ENABLE_OLLAMA_API=false
rem Web search: SearXNG in Docker inside WSL Debian, http://127.0.0.1:8888 (config /opt/searxng/settings.yml).
rem Search settings themselves live in Open WebUI's database (Admin Panel -> Settings -> Web Search).
rem Start Debian + container and keep Debian running while this window is open (WSL stops idle distros).
wsl -d Debian -u root -- docker start searxng >nul 2>&1
start "" /b wsl -d Debian -u root --exec sleep infinity
rem Text-to-speech: local Piper server (CPU, Russian voices), http://127.0.0.1:5005/v1, see D:\llm\tts\server.py
start "" /b D:\llm\tts\.venv\Scripts\python.exe D:\llm\tts\server.py
rem Open WebUI goes to the internet directly, not through v2rayN: its SSRF protection
rem rejects connections to the proxy at 127.0.0.1, so web search pages would not load.
rem Search engines, GitHub, Wikipedia, HF, Reddit work directly; X, YouTube, Medium do not.
set NO_PROXY=*
set no_proxy=*
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
open-webui serve --host 0.0.0.0 --port 3000
pause
