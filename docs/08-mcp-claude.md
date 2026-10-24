# MCP-коннектор local-ai для Claude Code

`llm/mcp/local_ai_mcp.py`, окружение uv (`llm/mcp/requirements.txt`, SDK `mcp` 2.3). В этой версии `FastMCP` переименован: `from mcp.server.mcpserver import MCPServer, Image`.

Подключение для всех проектов:

```
claude mcp add --scope user local-ai -- D:\llm\mcp\.venv\Scripts\python.exe D:\llm\mcp\local_ai_mcp.py
```

## Инструменты

| Инструмент | Что делает |
|---|---|
| `local_llm(task, files, think, max_tokens)` | поручает задачу Gemma через `think_proxy`. **Файлы читает сам сервер** (до 700 тыс. символов), в контекст Claude возвращается только результат и строка «сколько токенов на вход и выход». `think=false` — быстрые выжимки и переводы, `true` — с размышлениями |
| `web_search(query, count)` | поиск через локальный SearXNG |
| `generate_image(prompt, size, quality, seed)` | FLUX 3: PNG в `ComfyUI\output\mcp`, плюс уменьшенная копия, чтобы Claude видел результат |
| `edit_image(prompt, images, quality, seed)` | правка или объединение до 4 картинок с диска |

## Когда это выгодно

`local_llm` экономит лимиты Claude, когда много входа превращается в короткий выход: большие журналы, документация, черновики, переводы, сортировка. На сложных рассуждениях и решениях Gemma заметно слабее, результат надо выборочно проверять. Это прописано в инструкциях сервера для Claude.

Проверено: журнал загрузок на 2 018 токенов → ответ в 60 токенов за 7 с.

Встроенный поиск Claude обычно лучше на английских и технических темах. SearXNG полезен для русскоязычных и местных тем: в нём есть Яндекс, и он находит другие источники.

## Запуск Claude Code на локальной модели

Возможен: llama.cpp понимает Anthropic API `/v1/messages`.

```powershell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8080"
$env:ANTHROPIC_AUTH_TOKEN = "local"
$env:ANTHROPIC_MODEL = "gemma-4-26b-a4b"
claude
```

Но для агентной работы с файлами и командами Gemma 26B слишком слаба. Это годится только для экспериментов.
