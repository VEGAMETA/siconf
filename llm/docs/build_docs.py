"""Офлайн-документация для DevOps: собирает поисковую базу docs.db (SQLite FTS5, английский стемминг) для инструмента devops_docs.

Источники:
  - ZIM-файлы Kiwix: справочники DevDocs и ArchWiki (download.kiwix.org, последние версии по каталогу);
  - официальная документация в Markdown прямо из репозиториев: Kubernetes (kubernetes/website), Prometheus, Helm.
Запуск (раз в несколько месяцев, чтобы обновить): D:\\llm\\docs\\.venv\\Scripts\\python.exe -X utf8 build_docs.py
Нужны libzim и beautifulsoup4 (venv .venv), git.
"""
import re
import sqlite3
import subprocess
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup
from libzim.reader import Archive

HERE = Path(__file__).parent
ZIMS = HERE / "zim"
REPOS = HERE / "repos"
DB = HERE / "docs.db"
CATALOG = "https://library.kiwix.org/catalog/v2/entries?name={q}"  # поиск по имени книги (q= ищет по тексту)
# справочники DevDocs и ArchWiki: имя в каталоге Kiwix -> короткое имя источника
ZIM_BOOKS = {f"devdocs_en_{n}": n for n in ["docker", "terraform", "ansible", "nginx", "postgresql", "python", "bash", "git", "go",
                                              "kubectl", "kubernetes", "vagrant", "jq", "http", "redis", "rabbitmq", "sqlite"]}
ZIM_BOOKS["archlinux_en_all"] = "archwiki"
# официальная документация в Markdown: (источник, репозиторий, папки, базовый URL сайта)
GIT_DOCS = [("kubernetes", "https://github.com/kubernetes/website.git", ["content/en/docs"], "https://kubernetes.io/docs/"),
            ("prometheus", "https://github.com/prometheus/prometheus.git", ["docs"], "https://prometheus.io/docs/"),
            ("helm", "https://github.com/helm/helm-www.git", ["docs"], "https://helm.sh/docs/")]  # helm: Docusaurus, .md и .mdx


TRANSLATION = re.compile(r"\((?:Italiano|Magyar|Português|Français|Español|Deutsch|Русский|日本語|简体中文|正體中文|한국어|Polski|Čeština|"
                         r"Suomi|Ελληνικά|Українська|Dansk|Nederlands|العربية|Türkçe|Svenska|Bahasa Indonesia|Lietuvių|Slovenský|"
                         r"Български|Српски|Hrvatski|Română|Norsk|עברית|ไทย|Tiếng Việt|Eesti|Latviešu|Esperanto|Català)\)")


def latest_zim(name):
    """URL последней версии книги из каталога Kiwix."""
    with urllib.request.urlopen(CATALOG.format(q=name), timeout=120) as r:
        xml = r.read().decode("utf-8")
    urls = []
    for entry in re.findall(r"<entry>(.*?)</entry>", xml, re.S):
        if f"<name>{name}</name>" in entry:
            m = re.search(r'href="([^"]+\.zim)', entry)
            if m:
                urls.append(m.group(1))
    return sorted(urls)[-1] if urls else None


def download_zims():
    ZIMS.mkdir(exist_ok=True)
    paths = {}
    for book, source in ZIM_BOOKS.items():
        url = latest_zim(book)
        if not url:
            print(f"нет в каталоге: {book}", flush=True)
            continue
        path = ZIMS / Path(url).name
        if not path.exists():
            for old in ZIMS.glob(f"{book}_*.zim"):
                old.unlink()  # прошлая версия этой книги
            urllib.request.urlretrieve(url, path)
        paths[source] = path
        print(f"ZIM {source}: {path.name} ({path.stat().st_size // 2**20} МБ)", flush=True)
    return paths


def clone_docs():
    REPOS.mkdir(exist_ok=True)
    for source, url, folders, _ in GIT_DOCS:
        dest = REPOS / source
        if dest.exists():
            subprocess.run(["git", "-C", str(dest), "pull", "-q", "--depth", "1"], check=False)
        else:
            subprocess.run(["git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse", url, str(dest)], check=True)
        subprocess.run(["git", "-C", str(dest), "sparse-checkout", "set", *folders], check=True)  # и при смене папок
        print(f"git {source}: {sum(1 for _ in dest.rglob('*.md*'))} md-файлов", flush=True)


def html_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))
    return title, re.sub(r"[ \t]+", " ", text).strip()


def zim_pages(source, path):
    archive = Archive(str(path))
    for i in range(archive.all_entry_count):
        entry = archive._get_entry_by_id(i)
        if entry.is_redirect:
            continue
        item = entry.get_item()
        if not item.mimetype.startswith("text/html"):
            continue
        # ArchWiki: переводы на десяток языков засоряют выдачу — оставляем английский и русский
        if TRANSLATION.search(entry.title or "") and "(Русский)" not in (entry.title or ""):
            continue
        title, text = html_text(bytes(item.content).decode("utf-8", "replace"))
        if len(text) > 200:
            yield source, entry.title or title, entry.path, text


def md_pages():
    for source, _, folders, site in GIT_DOCS:
        root = REPOS / source
        for folder in folders:
            for path in [*(root / folder).rglob("*.md"), *(root / folder).rglob("*.mdx")]:
                raw = path.read_text(encoding="utf-8", errors="replace")
                title = (re.search(r"^title:\s*[\"']?(.+?)[\"']?\s*$", raw, re.M) or [None, path.stem])[1]
                body = re.sub(r"\A---.*?---\s*", "", raw, flags=re.S)  # front matter
                body = re.sub(r"\{\{[<%].*?[%>]\}\}", "", body, flags=re.S)  # шорткоды Hugo
                body = re.sub(r"^(?:import|export) .*$", "", body, flags=re.M)  # строки JSX-модулей в .mdx
                rel = path.relative_to(root / folder).with_suffix("").as_posix().replace("/_index", "/").replace("_index", "")
                if len(body) > 200:
                    yield source, title, site + rel, body.strip()


def main():
    zims = download_zims()
    clone_docs()
    tmp = DB.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.execute("create virtual table docs using fts5(source, title, path, body, tokenize='porter unicode61')")
    counts = {}
    for source, path in zims.items():
        for row in zim_pages(source, path):
            con.execute("insert into docs values (?, ?, ?, ?)", row)
            counts[source] = counts.get(source, 0) + 1
    for row in md_pages():
        con.execute("insert into docs values (?, ?, ?, ?)", row)
        counts[row[0]] = counts.get(row[0], 0) + 1
    con.commit()
    con.execute("insert into docs(docs) values ('optimize')")
    con.commit()
    con.close()
    tmp.replace(DB)
    print("страниц:", ", ".join(f"{k} {v}" for k, v in sorted(counts.items())), f"| {DB.stat().st_size // 2**20} МБ", flush=True)


if __name__ == "__main__":
    main()
