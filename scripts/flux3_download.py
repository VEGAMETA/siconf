"""FLUX 3 Image Klein для ComfyUI (int8 под RTX 4060 Ti; nvfp4 — только для RTX 50, bf16 не нужен).

Репозиторий закрытый: ждёт, пока пользователь примет лицензию на HF, затем качает с проверкой SHA-256.
"""
import concurrent.futures as cf
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_download as g  # noqa: E402

REPO = "black-forest-labs/flux-3-image-klein-comfy"
FILES = [  # (путь в репо, папка назначения)
    ("diffusion_models/flux3-image-klein-int8-convrot.safetensors", g.MODELS + r"\diffusion_models"),        # дистиллированная, 16 шагов
    ("diffusion_models/flux3-image-klein-base-int8-convrot.safetensors", g.MODELS + r"\diffusion_models"),   # базовая, 50 шагов
    ("text_encoders/qwen3vl_4b_int8_convrot.safetensors", g.MODELS + r"\text_encoders"),
    ("text_encoders/qwen3.5_9b_flux3_prompt_upsampler_int8_convrot.safetensors", g.MODELS + r"\text_encoders"),
    ("vae/flux2-vae.safetensors", g.MODELS + r"\vae"),
    ("LICENSE.md", r"D:\gen\workflows\flux3"),
]
for name in ("t2i", "i2i", "mi2i"):
    for kind in ("int8", "base_int8"):
        FILES.append((f"workflows/flux3_klein_{kind}_{name}.json", r"D:\gen\workflows\flux3"))
for ref in ("autumn_forest", "great_wave", "green_doors", "toast", "woman_hat"):
    FILES.append((f"workflows/klein_ref_{ref}.jpg", r"D:\gen\workflows\flux3"))

probe = f"https://huggingface.co/{REPO}/resolve/main/vae/flux2-vae.safetensors"
auth = [a for k, v in g.hf_auth().items() for a in ("-H", f"{k}: {v}")]
for i in range(240):  # до 2 часов
    code = subprocess.run(["curl", "-s", "-o", os.devnull, "-w", "%{http_code}", "-r", "0-10", "-L", *auth, probe],
                          capture_output=True, text=True).stdout
    if code in ("200", "206"):
        break
    if i == 0:
        g.log(f"FLUX 3: нет доступа ({code}) — жду, пока примут лицензию на https://huggingface.co/{REPO}")
    time.sleep(30)
else:
    g.log("FLUX 3: доступа так и нет, выхожу")
    sys.exit(2)

jobs = []
for path, folder in FILES:
    size, oid = g.hf_meta(REPO, path)
    jobs.append((f"https://huggingface.co/{REPO}/resolve/main/{path}", os.path.join(folder, os.path.basename(path)),
                 size, oid, os.path.basename(path)))
g.log(f"FLUX 3: файлов {len(jobs)}, всего {sum(j[2] for j in jobs) / 1e9:.1f} GB")
with cf.ThreadPoolExecutor(max_workers=3) as ex:
    results = list(ex.map(lambda j: g.fetch(*j), jobs))
g.log(f"FLUX 3 ГОТОВО: успешно {sum(results)} из {len(results)}")
sys.exit(0 if all(results) else 1)
