@echo off
rem ComfyUI + Manager, reachable from the home network: http://192.168.0.109:8188
rem Simple phone page (prompt + Generate): http://192.168.0.109:8188/simple
rem No password! Firewall rule "ComfyUI 8188 (LAN)" allows only the local subnet.
cd /d "%~dp0ComfyUI_windows_portable"
.\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --enable-manager --listen 0.0.0.0 --port 8188 --disable-auto-launch
pause
