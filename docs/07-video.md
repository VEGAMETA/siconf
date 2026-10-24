# Видео: ComfyUI

ComfyUI portable **v0.42.1** (torch 2.14 + cu130, встроенный Python 3.13) в `D:\gen\ComfyUI_windows_portable`. Запуск в локальной сети — `gen/start_comfyui_lan.bat` (`--listen 0.0.0.0 --port 8188 --enable-manager`), правило брандмауэра «ComfyUI 8188 (LAN)» разрешает только локальную подсеть. ZeroTier пользователь не хочет.

## Модели (только нейтральные)

| Режим | Модель | Энкодер / прочее |
|---|---|---|
| Видео со звуком по тексту или кадру | **LTX-2.5 distilled** (unsloth UD-Q4_K_XL, 14 GB) | **официальный** `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot` (Lightricks, доступ после лицензии), VAE видео и аудио, апскейлер x2 |
| Оживить картинку | **Wan 2.2 I2V A14B** high + low noise (Q6_K, по 12 GB) | umt5_xxl_fp16, wan_2.1_vae, LoRA lightx2v 4 шага; LoRA Lenovo (фотореализм) и detailz |

NSFW-сборки (Wan Mega v12.2, LTX 2.3 uncensored, LoRA DR34ML4Y и подобные) удалены по решению пользователя: они уводили любые сцены в эротику («столб жидкости» превращался понятно во что).

**Почему энкодер официальный.** С «расцензуренным» энкодером Gemma 4 Q4 от ChrisColeTech LTX-2.5 игнорировала запрос и рисовала говорящую женщину. С официальным int8 запрос выполняется точно.

VAE `ltx25_uncensored_*` называются так по сборке, но по SHA-256 совпадают с официальными Lightricks.

## Настройки

- **LTX-2.5:** две ступени. Узел `LTXV25ImgToVideo` считает в половинном разрешении, поэтому нужны `LatentUpscale` и «refine» на 3 шага. 768×448, 49 кадров — около 96 с.
- **Wan 2.2 I2V:** 4 шага с lightx2v, CFG 1.
- Узлы: ComfyUI-GGUF (city96), ComfyUI-GGUF-Loader (ChrisColeTech, закреплён на проверенном коммите `109a281`, ставить только gguf, sentencepiece, protobuf и requests), VideoHelperSuite, KJNodes, WanVideoWrapper, Manager.

## Свой узел ComfyUI-SimpleGen (`gen/comfyui-simplegen`)

- `__init__.py` — маршруты `/simple` (страница для телефона), `/simple/delete`, `/simple/clear`.
- `vram_nodes.py` — `SimpleGenUnloadLLM` (перед генерацией выгружает модели llama.cpp через `/models/unload`) и `SimpleGenFreeVRAM` (после декодирования освобождает видеопамять). Так LLM и генераторы делят одну видеокарту.
- `simple.html` — страница «ввёл запрос и нажал»: история, удаление, подхват заданий после перезагрузки страницы (по `extra_data.simplegen`). **Устарела:** ссылается на удалённые NSFW-модели, будет переделана под LTX-2.5 и Wan I2V.

## Как писать запросы

[gen/HOW_TO_PROMPT.md](../gen/HOW_TO_PROMPT.md). Официальные правила Lightricks и Wan — в `prompts/official/`.
