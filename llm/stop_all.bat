@echo off
rem Stops everything start_all.bat started: llama.cpp, think proxy, ComfyUI, Open WebUI, Piper TTS, the WSL keepalive
rem and their windows. The SearXNG container stays (it is tiny; WSL stops Debian by itself when idle).
rem Unfinished ComfyUI queue items and a chat answer being generated are lost.
powershell -NoProfile -Command "$p = 'llama-server|open-webui|ComfyUI.main\.py|tts.server\.py|think_proxy\.py|start_proxy\.bat|sleep infinity|start_llm\.bat|start_webui\.bat|start_comfyui_lan\.bat'; Get-CimInstance Win32_Process | Where-Object { $_.Name -in 'llama-server.exe','open-webui.exe','python.exe','wsl.exe','cmd.exe' -and $_.CommandLine -match $p } | ForEach-Object { Write-Host ('stop ' + $_.Name + ' ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 3
