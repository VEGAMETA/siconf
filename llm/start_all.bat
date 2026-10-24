@echo off
rem Starts the whole local AI stack and opens the chat. Each service gets its own minimized
rem window (close it or run stop_all.bat to stop); a service that is already running is skipped.
rem   llama.cpp   127.0.0.1:8080  start_llm.bat
rem   think proxy 127.0.0.1:8081  start_proxy.bat (Gemma thinks in batches with checkpoints; Open WebUI talks to it)
rem   ComfyUI     0.0.0.0:8188    D:\gen\start_comfyui_lan.bat   (phone: http://192.168.0.109:8188/simple)
rem   Open WebUI  0.0.0.0:3000    start_webui.bat (+ SearXNG, WSL keepalive, Piper TTS)  (phone: http://192.168.0.109:3000)
call :up 8080 "LLM llama.cpp" "D:\llm\start_llm.bat"
call :up 8081 "Think proxy" "D:\llm\start_proxy.bat"
call :up 8188 "ComfyUI" "D:\gen\start_comfyui_lan.bat"
call :up 3000 "Open WebUI" "D:\llm\start_webui.bat"
echo Waiting for Open WebUI...
set /a tries=0
:wait
curl -s -o nul --noproxy * http://127.0.0.1:3000/health && goto ready
set /a tries+=1
if %tries% geq 150 (echo Open WebUI did not start in 5 minutes, see its window. & pause & exit /b 1)
timeout /t 2 /nobreak >nul
goto wait
:ready
start "" http://127.0.0.1:3000
exit /b 0

:up
rem %1 port, %2 window title, %3 script
netstat -ano | findstr /r /c:":%1 .*LISTENING" >nul && (echo %~2: already running& exit /b 0)
echo Starting %~2
start "%~2" /min cmd /c "%~3"
exit /b 0
