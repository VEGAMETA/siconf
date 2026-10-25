"""Правки фронтенда Open WebUI, которых нет в релизе. Запускать после каждого обновления open-webui:
    python -X utf8 D:\\llm\\patches\\apply_owui_patches.py
Повторный запуск безопасен: уже исправленные файлы пропускаются.

1. Кнопка «Скачать» в просмотре картинки не нажимается на телефоне (0.12.3): panzoom вешает touchstart на всё окно
   просмотра и вызывает preventDefault, поэтому click по кнопке не рождается. onTouch, возвращающий false для касаний
   по кнопкам, пропускает их (опция panzoom, https://github.com/anvaka/panzoom/issues/12).
"""
import glob
import os
import sys

CHUNKS = os.path.expanduser(r"~\AppData\Roaming\uv\tools\open-webui\Lib\site-packages\open_webui\frontend\_app\immutable\chunks")

PATCHES = [
    ("кнопки в просмотре картинки на телефоне",
     "const n={bounds:!0,boundsPadding:.1,pinchSpeed:3.5,beforeWheel:()=>!0};",
     'const n={bounds:!0,boundsPadding:.1,pinchSpeed:3.5,beforeWheel:()=>!0,onTouch:t=>!(t.target&&t.target.closest&&t.target.closest("button"))};'),
]

ok = True
for name, old, new in PATCHES:
    done = False
    for path in glob.glob(os.path.join(CHUNKS, "*.js")):
        s = open(path, encoding="utf-8").read()
        if new in s:
            print(f"уже исправлено: {name} ({os.path.basename(path)})")
            done = True
        elif old in s:
            open(path, "w", encoding="utf-8", newline="").write(s.replace(old, new))
            print(f"исправлено: {name} ({os.path.basename(path)})")
            done = True
    if not done:
        print(f"НЕ НАЙДЕНО: {name} — код Open WebUI изменился, правку нужно пересобрать (или ошибку уже починили)")
        ok = False
sys.exit(0 if ok else 1)
