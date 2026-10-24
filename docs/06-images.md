# Картинки: FLUX 3 Image Klein

## Выбор модели

Рейтинг Artificial Analysis (слепое сравнение, Эло), октябрь 2026:

| Модель | Эло | Открытые веса | Для 16 GB |
|---|---|---|---|
| GPT Image 2.5 Sunburst | 1222 | нет | — |
| Nano Banana Pro | 1118 | нет | — |
| **FLUX 3 Image Klein** (15.10.2026) | **1043** | да, FLUX Kommunity | **int8 5,8 GB + энкодер 4,9 GB** |
| Qwen-Image-2.1 | 1042 | только некоммерческая | влезет в Q4, но тяжелее |
| Fibo 2.0 | 1039 | только некоммерческая | 16 GB, загрузчика в ComfyUI ещё не было |
| GPT Image 1 | 1013 | нет | — |
| Z-Image Turbo (была раньше) | 936 | Apache 2.0 | — |

Z-Image удалена вместе со своими LoRA: на ~107 очков хуже, «стеклянную рыбу» рисовала как вазу.

## Файлы

`black-forest-labs/flux-3-image-klein-comfy` (доступ после согласия с лицензией), скрипт `scripts/flux3_download.py`:

| Файл | Размер | Папка ComfyUI |
|---|---|---|
| `flux3-image-klein-int8-convrot` (дистиллированная) | 5,8 GB | diffusion_models |
| `flux3-image-klein-base-int8-convrot` (базовая) | 5,8 GB | diffusion_models |
| `qwen3vl_4b_int8_convrot` | 4,9 GB | text_encoders |
| `qwen3.5_9b_flux3_prompt_upsampler_int8_convrot` | 9,8 GB | text_encoders (пока не используется: запросы пишет Gemma) |
| `flux2-vae` | 0,3 GB | vae |

nvfp4 работает только на RTX 50-й серии, bf16 избыточна для 16 GB. ComfyUI v0.42.1 уже поддерживает FLUX 3, обновлять не пришлось.

## Параметры (карточка BFL)

| Режим | Модель | Шаги | CFG | Сэмплер |
|---|---|---|---|---|
| fast | дистиллированная | 16 | 1 (без CFG) | euler / simple |
| best | базовая | 50 | 3.5 | euler / simple |

`ModelSamplingFlux`: `max_shift = base_shift = ln(16) = 2.77259` (alpha 16 из официальных схем), латент `EmptyFlux2LatentImage`, CLIP-тип `flux3`.

## Схемы для чата и MCP

`llm/workflows/openwebui_flux3_t2i.json` и `openwebui_flux3_edit.json` (формат API ComfyUI):

```
UNETLoader → ModelSamplingFlux → KSampler → VAEDecode → SimpleGenFreeVRAM → SaveImage
CLIPLoader(qwen3vl, flux3) → CLIPTextEncode(SimpleGenUnloadLLM(prompt)) / CLIPTextEncode("")
правка: LoadImage → ImageScaleToTotalPixels(1 Мп) → GetImageSize → EmptyFlux2LatentImage
        ReferenceMultiLatent(resolution=resize, resolution.megapixels=1.0, images.image0..N)
```

Схемы проверены в ComfyUI без запуска: одно поле нарочно испорчено (`weight_dtype`), и ComfyUI сообщил только об этой ошибке.

## Инструмент для чата `flux_studio` (`llm/tools/flux_studio.py`)

- `create_image(prompt, size, quality, seed)` — новая картинка. Gemma сама выбирает размер под сюжет: 832×1216 портрет, 1216×832 пейзаж, 1344×768 баннер, 1024×1024 квадрат.
- `edit_image(prompt, images, quality, seed)` — правка последней картинки беседы (вашей или нарисованной) или объединение до 4 картинок. Картинки берутся из базы чата, где есть и сгенерированные, а для временного чата — из сообщений.
- Картинка появляется в чате так же, как у встроенного генератора (`chat:message:files`). В статусе видны размер, режим и seed.
- **Самопроверка:** инструмент возвращает словарь с уменьшенной копией (JPEG 768 px, data-URL), Open WebUI показывает её модели. Gemma сверяет результат с запросом и прямо говорит, если что-то не так. С зрением на CPU это +~12 с на картинку.

## Ограничения FLUX 3 (на 24.10.2026)

- **LoRA мало:** ~26 на Hugging Face, в основном экспериментальные (Outpaint, Restore, Consistency, Angles, photo-aesthetics, 4-step для базовой). Старые LoRA Z-Image не подходят.
- **ControlNet нет.** Его заменяют картинки-образцы (до 10), рамки на сетке 0–1000 и правка. По словам BFL, образцы «задают содержание, но не фиксируют структуру», так что набросок — это «по мотивам», не контур в контур.
- Модель обучали на отфильтрованных данных, она строже Z-Image.

## Не проверено

Генерация и правка вживую через чат и MCP, время на 4060 Ti, видит ли Gemma картинку в следующих ходах. См. [11-todo.md](11-todo.md).
