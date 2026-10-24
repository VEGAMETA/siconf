@echo off
rem ComfyUI + Manager; listens on 127.0.0.1 only, browser opens automatically
cd /d "%~dp0ComfyUI_windows_portable"
.\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --enable-manager
pause
