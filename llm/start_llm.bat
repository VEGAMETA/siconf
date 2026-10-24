@echo off
rem llama.cpp router: models from models.ini, one model in VRAM at a time.
rem API (OpenAI-compatible): http://127.0.0.1:8080/v1   built-in chat: http://127.0.0.1:8080
cd /d "%~dp0"
llama.cpp\llama-server.exe --models-preset models.ini --models-max 1 --host 127.0.0.1 --port 8080
pause
