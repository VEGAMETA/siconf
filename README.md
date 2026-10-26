# siconf — локальный ИИ на домашнем ПК

**si** — superintelligence, **conf** — конфигурация. Пока это скромная домашняя версия: одна видеокарта на 16 GB.

Конфиги, промпты, скрипты и документация к локальной связке «чат с ИИ + генерация картинок и видео» на одной видеокарте RTX 4060 Ti 16 GB. Всё настроено и проверено 24 октября 2026 года.

## Что это умеет

- **Чат с Gemma 4 26B** (Google, сжатая с дообучением QAT q4_0), контекст 256K, через Open WebUI в браузере и с телефона. По умолчанию включены:
  - поиск в интернете через свой SearXNG;
  - память о пользователе и поиск по прошлым беседам;
  - сжатие длинных бесед и поиск по полной истории текущей беседы;
  - интерпретатор Python для точного счёта;
  - озвучка ответов (Piper, русские голоса).
- **Картинки FLUX 3 Image Klein прямо из чата.** Gemma сама пишет полный запрос по официальным правилам BFL, правит нарисованное («сделай вечер», «убери машину») и проверяет результат по уменьшенной копии.
- **Размышления партиями** через собственного посредника `think_proxy`: модель не уходит в бесконечные круги, на трудных задачах делает паузы «оглянуться».
- **Видео** в ComfyUI: LTX-2.5 со звуком и Wan 2.2 I2V.
- **Коннектор MCP для Claude Code:** Claude может поручать объёмную простую работу локальной Gemma, искать через SearXNG и рисовать на локальной видеокарте.

## Схема

```
браузер / телефон ──► Open WebUI :3000 ──► think_proxy :8081 ──► llama.cpp :8080 (Gemma 4 26B)
                         │  ├─► SearXNG :8888 (Docker в WSL Debian)
                         │  ├─► Piper TTS :5005
                         │  └─► инструмент flux_studio ──► ComfyUI :8188 (FLUX 3, LTX-2.5, Wan 2.2)
Claude Code ──► MCP local-ai ──► think_proxy / SearXNG / ComfyUI
```

Видеопамять одна, поэтому LLM и генератор картинок работают по очереди: перед генерацией узел `SimpleGenUnloadLLM` выгружает Gemma, после неё `SimpleGenFreeVRAM` освобождает видеопамять, и llama.cpp при следующем запросе загружает модель обратно из файлового кэша за секунды.

## Железо

Ryzen 7 7700, 64 GB DDR5-6000, RTX 4060 Ti 16 GB, Windows 11. Подробности и история дисков — [docs/01-pc.md](docs/01-pc.md).

## Документация

| Файл | О чём |
|---|---|
| [docs/01-pc.md](docs/01-pc.md) | железо, диски (MAXIO/Phison), SMART, HMB, мёртвый SSD |
| [docs/02-llm.md](docs/02-llm.md) | llama.cpp, выбор модели, `models.ini`, замеры скорости, зрение на CPU |
| [docs/03-open-webui.md](docs/03-open-webui.md) | Open WebUI: модели, поиск, память, сжатие, инструменты, озвучка |
| [docs/04-prompts.md](docs/04-prompts.md) | системный промпт и план размышлений: что и почему |
| [docs/05-think-proxy.md](docs/05-think-proxy.md) | посредник: размышления партиями с паузами |
| [docs/06-images.md](docs/06-images.md) | FLUX 3 Klein: выбор модели, схемы, инструмент для чата |
| [docs/07-video.md](docs/07-video.md) | ComfyUI, LTX-2.5, Wan 2.2, страница `/simple` |
| [docs/08-mcp-claude.md](docs/08-mcp-claude.md) | коннектор MCP для Claude Code |
| [docs/09-benchmarks.md](docs/09-benchmarks.md) | тесты: GSM8K, IFEval, MMLU-Pro, тест-ловушка, сравнения |
| [docs/10-lessons.md](docs/10-lessons.md) | грабли и как их обошли |
| [docs/11-todo.md](docs/11-todo.md) | что ещё не сделано и не проверено |
| [docs/12-health.md](docs/12-health.md) | медицина: клинрекомендации Минздрава в базе знаний, поиск по литературе (Europe PMC) и инструкциям (openFDA), навык health |
| [docs/13-offline-docs.md](docs/13-offline-docs.md) | офлайн-документация DevOps: Kubernetes, Helm, Prometheus из исходников, DevDocs и ArchWiki в SQLite FTS5 |
| [gen/HOW_TO_PROMPT.md](gen/HOW_TO_PROMPT.md) | как писать запросы для видео и картинок |

## Раскладка репозитория

| Папка | На ПК | Что внутри |
|---|---|---|
| `llm/` | `D:\llm` | `models.ini`, батники запуска, `owui_setup.py`, инструменты Open WebUI, посредник, MCP, сервер озвучки, тесты, иконки, схемы ComfyUI для чата |
| `prompts/` | `D:\gen\prompts` | системный промпт, план размышлений, официальные промпты BFL / Lightricks / Wan / Z-Image |
| `gen/` | `D:\gen` | запуск ComfyUI, свой узел `ComfyUI-SimpleGen`, официальные схемы FLUX 3, шпаргалка по запросам |
| `owui-config/` | база Open WebUI | снимок настроек Open WebUI через API (ключи заменены на `<redacted>`) |
| `searxng/` | WSL Debian `/opt/searxng` | конфиг SearXNG (без `secret_key`) и команда запуска контейнера |
| `scripts/` | — | загрузка моделей с проверкой SHA-256, иконки, замер скорости, разбор сбоев NVMe, снимок настроек Open WebUI (`owui_snapshot.py`) |

## Запуск

Ярлык **Local AI** (`D:\shortcuts`) запускает `llm\tray\local_ai_tray.py` (pythonw, без консоли): одна иконка в трее поднимает все службы без окон — SearXNG (Docker в WSL), llama.cpp, think_proxy, Piper, ComfyUI, Open WebUI — и открывает чат. Точка на иконке: зелёная — всё работает, жёлтая — не всё, серая — остановлено; подсказка показывает «работает N из 6». Меню: открыть чат / ComfyUI / `/simple`, состояние каждой службы с перезапуском, остановкой и журналом (`D:\llm\logs\*.log`), «Освободить память» (ComfyUI `/free` + выгрузка Gemma), «Остановить всё и выйти». Повторный запуск ярлыка открывает чат. Батники `llm\start_all.bat` / `stop_all.bat` остались как запасной вариант.

| Служба | Адрес |
|---|---|
| Open WebUI | http://127.0.0.1:3000, с телефона http://192.168.0.109:3000 |
| ComfyUI | http://127.0.0.1:8188, с телефона http://192.168.0.109:8188/simple |
| llama.cpp | http://127.0.0.1:8080 (напрямую), http://127.0.0.1:8081 (через посредника) |

## Чего здесь нет

Модели (их скачивают скрипты из `scripts/`), база Open WebUI, ключи из `D:\gen\.env` (`HF_TOKEN`, `CIVITAI_API_KEY`, `OPENWEBUI_API_KEY`) и `secret_key` SearXNG. Скрипты берут ключи из окружения: `set -a; . /d/gen/.env; set +a`.
