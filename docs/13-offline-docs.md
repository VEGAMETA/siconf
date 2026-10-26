# Офлайн-документация DevOps

Инструмент `llm/tools/devops_docs.py` (`search_docs`, `read_doc`) ищет по локальной базе `D:\llm\docs\docs.db` — SQLite FTS5 с английским стеммингом (porter), ответ за сотые доли секунды, интернет не нужен.

## Что в базе (2026-10-26, ≈ 21 тыс. страниц, 260 МБ)

- **Официальная документация в Markdown прямо из репозиториев** (полноценные руководства, а не только справочник API): Kubernetes (`kubernetes/website`, `content/en/docs`, 1,3 тыс. страниц), Prometheus (`prometheus/prometheus`, `docs`), Helm (`helm/helm-www`, `docs` — Docusaurus, .md и .mdx). Клонирование `--depth 1 --filter=blob:none --sparse`; front matter, шорткоды Hugo и JSX-импорты вырезаются; ссылка — адрес страницы на сайте.
- **ZIM-файлы Kiwix** (читаются библиотекой `libzim`, venv `D:\llm\docs\.venv`): справочники DevDocs — Ansible, Terraform, Docker, nginx, PostgreSQL, Python, Go, Bash, Git, kubectl, Kubernetes API, Vagrant, jq, HTTP, Redis, RabbitMQ, SQLite — и **ArchWiki** (3,3 тыс. статей, только английские и русские; переводы на другие языки засоряли выдачу). Последняя версия каждой книги — по каталогу `library.kiwix.org/catalog/v2/entries?name=<книга>` (параметр `q=` ищет по тексту, а не по имени).
- Готовых ZIM-копий kubernetes.io, Prometheus и Helm в каталоге Kiwix нет — поэтому они из исходников.

## Сборка и обновление

`D:\llm\docs\.venv\Scripts\python.exe -X utf8 D:\llm\docs\build_docs.py` — скачивает новые версии ZIM (старые удаляет), обновляет репозитории, пересобирает базу (минуты). В репозиторий не кладутся: база, ZIM-файлы, клоны, venv.

## Как модель пользуется

Системный промпт: для точного синтаксиса, флагов, ключей конфигов и пошаговых инструкций по этим технологиям сначала `search_docs`/`read_doc`, веб-поиск — для новых версий и того, чего нет в документации. `search_docs` сначала ищет все слова запроса, если пусто — любое; можно ограничить источником (`source="terraform"`); `read_doc` читает страницу кусками по 9000 символов.

Почему не kiwix-serve и не база знаний Open WebUI: kiwix-serve потребовал бы ещё одну службу; эмбеддинги bge-m3 на CPU для 20 тыс. страниц заняли бы сутки, а для английской документации полнотекстовый поиск со стеммингом работает хорошо.
