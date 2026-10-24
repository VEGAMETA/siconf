"""Скачивание ComfyUI portable и моделей в D:\\gen с докачкой и проверкой SHA-256."""
import concurrent.futures as cf
import hashlib
import json
import os
import subprocess
import sys
import urllib.request

ROOT = r"D:\gen"
COMFY_ARCHIVE = os.path.join(ROOT, "_downloads", "ComfyUI_windows_portable_nvidia.7z")
MODELS = os.path.join(ROOT, "ComfyUI_windows_portable", "ComfyUI", "models")
LOG = os.path.join(ROOT, "_downloads", "download.log")

# (репозиторий HF, путь в репо, папка в models)
HF_FILES = [
    # базовая Wan 2.2 (QuantStack GGUF Q5_K_M, umt5 fp8, wan_2.1_vae, lightx2v LoRA) убрана по просьбе пользователя
    # Wan 2.2 модификация: Rapid AIO Mega v9 NSFW (всё в одном)
    ("Phr00t/WAN2.2-14B-Rapid-AllInOne", "Mega-v9/wan2.2-rapid-mega-aio-nsfw-v9.safetensors", "checkpoints"),
    # LTX-2.3 uncensored v1.4
    ("ChrisColeTech/LTX-2.3-uncensored-v1.4-FP8", "split/diffusion_models/ltxv23_uncensored_v1.4_Q4_K_M.gguf", "diffusion_models"),
    ("ChrisColeTech/LTX-2.3-uncensored-v1.4-FP8", "split/text_encoders/gemma-3-12b-it-ablit-norms-biproj-Q4_K_M.gguf", "text_encoders"),
    ("ChrisColeTech/LTX-2.3-uncensored-v1.4-FP8", "split/text_encoders/ltxv23_uncensored_v1.4_projections.safetensors", "text_encoders"),
    ("ChrisColeTech/LTX-2.3-uncensored-v1.4-FP8", "split/vae/ltxv23_uncensored_v1.4_video_vae.safetensors", "vae"),
    ("ChrisColeTech/LTX-2.3-uncensored-v1.4-FP8", "split/vae/ltxv23_uncensored_v1.4_audio_vae.safetensors", "vae"),
    ("ChrisColeTech/LTX-2.3-uncensored-v1.4-FP8", "split/latent_upscale_models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors", "latent_upscale_models"),
]


def log(msg):
    print(msg, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def hf_auth():
    """Заголовок авторизации HF из окружения (берётся из D:\\gen\\.env) — нужен для закрытых репозиториев."""
    tok = os.environ.get("HF_TOKEN")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def hf_meta(repo, path):
    folder = os.path.dirname(path)
    url = f"https://huggingface.co/api/models/{repo}/tree/main/{folder}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=hf_auth())) as r:
        for x in json.load(r):
            if x["path"] == path:
                return x["size"], (x.get("lfs") or {}).get("oid")
    raise RuntimeError(f"нет файла {repo}/{path}")


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(16 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url, dest, size, digest, name):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest) and os.path.getsize(dest) == size and digest and sha256(dest) == digest:
        log(f"OK (уже есть)  {name}")
        return True
    for attempt in range(1, 4):
        part = dest + ".part"
        auth = [arg for k, v in hf_auth().items() for arg in ("-H", f"{k}: {v}")] if "huggingface.co" in url else []
        subprocess.run(["curl", "-L", "-sS", "--fail", "-C", "-", "--retry", "10", "--retry-delay", "5",
                        "--retry-all-errors", *auth, "-o", part, url])
        if not os.path.exists(part) or os.path.getsize(part) != size:
            log(f"размер не совпал ({os.path.getsize(part) if os.path.exists(part) else 0} из {size}), попытка {attempt}  {name}")
            continue
        if digest and sha256(part) != digest:
            log(f"SHA-256 НЕ СОВПАЛ, качаю заново, попытка {attempt}  {name}")
            os.remove(part)
            continue
        os.replace(part, dest)
        log(f"OK  {size / 1e9:6.2f} GB  {name}")
        return True
    log(f"ОШИБКА  {name}")
    return False


def main():
    os.makedirs(os.path.dirname(COMFY_ARCHIVE), exist_ok=True)
    rel = json.load(urllib.request.urlopen("https://api.github.com/repos/Comfy-Org/ComfyUI/releases/latest"))
    asset = next(a for a in rel["assets"] if a["name"] == "ComfyUI_windows_portable_nvidia.7z")
    digest = (asset.get("digest") or "").removeprefix("sha256:") or None
    log(f"ComfyUI {rel['tag_name']}, digest: {digest or 'нет'}")
    ok = fetch(asset["browser_download_url"], COMFY_ARCHIVE, asset["size"], digest, asset["name"])

    jobs = []
    for repo, path, sub in HF_FILES:
        size, oid = hf_meta(repo, path)
        url = f"https://huggingface.co/{repo}/resolve/main/{path}"
        jobs.append((url, os.path.join(MODELS, sub, os.path.basename(path)), size, oid, f"{sub}/{os.path.basename(path)}"))
    log(f"моделей: {len(jobs)}, всего {sum(j[2] for j in jobs) / 1e9:.1f} GB")
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        results = list(ex.map(lambda j: fetch(*j), jobs))
    log(f"ГОТОВО: успешно {sum(results) + ok} из {len(results) + 1}")
    sys.exit(0 if ok and all(results) else 1)


if __name__ == "__main__":
    main()
