@echo off
rem Think proxy between Open WebUI and llama.cpp: Gemma thinks in batches with checkpoints
rem (first stop at 6000 thinking tokens, then every 4000, final answer forced at 18000).
rem Open WebUI -> http://127.0.0.1:8081/v1 -> proxy -> http://127.0.0.1:8080 (llama.cpp). Code: proxy\think_proxy.py
cd /d "%~dp0proxy"
.venv\Scripts\python.exe think_proxy.py
pause
