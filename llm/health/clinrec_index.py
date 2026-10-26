"""Поисковый индекс клинических рекомендаций для инструмента medical_research (search_guidelines, read_guideline).

База знаний Open WebUI (эмбеддинги bge-m3) находит нужную КР, но конкретный факт внутри текста в 200-300 тыс. символов
часто пропускает (целевой уровень мочевой кислоты при подагре, длительность антибиотикотерапии при пневмонии).
Здесь каждая КР из D:\\llm\\health\\clinrec\\*.md режется на фрагменты по 0,7-1,8 тыс. символов внутри разделов «## …»,
и по ним идёт полнотекстовый поиск SQLite FTS5 по основам слов (русский стеммер Snowball) — как в базе законов.

Запуск после clinrec_fetch.py: D:\\llm\\law\\.venv\\Scripts\\python.exe -X utf8 D:\\llm\\health\\clinrec_index.py
"""
import re
import sqlite3
from pathlib import Path

import snowballstemmer

HERE = Path(__file__).parent
SRC = HERE / "clinrec"
DB = HERE / "clinrec.db"
SKIP = {"Список сокращений"}  # сокращения засоряют выдачу
MIN, MAX = 700, 1800
SUBSECTION = re.compile(r"\d+(?:\.\d+){1,3}\.?\s+[А-ЯЁA-Z]")
STEM = snowballstemmer.stemmer("russian")


def stem_text(text):
    return " ".join(STEM.stemWords(re.findall(r"[а-яёa-z0-9]+", text.lower())))


def parse(path):
    """Шапка КР и фрагменты: [(раздел, текст)]."""
    lines = path.read_text(encoding="utf-8").splitlines()
    title = lines[0].lstrip("# ").strip()
    meta = " ".join(lines[1:5])
    code = re.search(r"код (\S+?),", meta)
    age = re.search(r"возраст: ([^,]+),", meta)
    published = re.search(r"опубликованы (\d{4}-\d{2}-\d{2})", meta)
    url = re.search(r"Источник: (\S+)", meta)
    mkb = re.search(r"МКБ-10: (.+?)(?:$|  )", meta)
    head = {"code": code.group(1) if code else path.stem.split()[0], "title": title, "age": age.group(1) if age else "",
            "published": published.group(1) if published else "", "url": url.group(1) if url else "",
            "mkb": mkb.group(1).strip() if mkb else ""}
    # «Список сокращений» КР: «АБТ — антибактериальная терапия» — для раскрытия сокращений в индексе
    abbr, in_list = {}, False
    for line in lines:
        if line.startswith("## "):
            in_list = line[3:].strip() == "Список сокращений"
        elif in_list:
            m = re.match(r"\s*([A-ZА-ЯЁ][\wА-Яа-яЁё\-]{0,11})\s*[—–-]\s*(.{3,200})", line)
            if m and any(ch.isupper() for ch in m.group(1)[1:] + m.group(1)[:1]):
                abbr[m.group(1)] = m.group(2).strip()
    head["abbr"] = abbr
    section, buf, out = "", [], []

    def flush():
        if buf and section not in SKIP:
            out.append((section, "\n".join(buf)))
        buf.clear()

    chapter = ""
    for line in lines[5:]:
        if line.startswith("## "):
            flush()
            section = chapter = line[3:].strip()
            continue
        line = line.strip()
        if not line:
            continue
        # подразделы внутри «## 3. Лечение» записаны обычным текстом («3.1.1 Лечение амбулаторных пациентов»):
        # фрагменты помечаются ими, чтобы read_guideline читал подраздел, а не главу на 60 тыс. символов
        if SUBSECTION.match(line) and len(line) < 140 and chapter not in SKIP:
            flush()
            section = f"{chapter} › {line.rstrip('.')}"
            continue
        if buf and sum(map(len, buf)) + len(line) > MAX and sum(map(len, buf)) >= MIN:
            flush()
        buf.append(line)
        if sum(map(len, buf)) >= MAX:
            flush()
    flush()
    return head, out


SCHEMA = """
    create table if not exists guidelines (code text primary key, title text, age text, published text, url text, mkb text);
    create table if not exists passages (id integer primary key, code text, pos integer, section text, text text);
    create index if not exists passages_code on passages(code, pos);
    create virtual table if not exists search using fts5(stems, tokenize='unicode61');
"""


def index_file(con, path):
    """Одна КР в индекс (старые фрагменты этой КР удаляются). Возвращает (шапка, число фрагментов)."""
    head, parts = parse(path)
    old = [r[0] for r in con.execute("select id from passages where code = ?", (head["code"],))]
    con.executemany("delete from search where rowid = ?", [(i,) for i in old])
    con.execute("delete from passages where code = ?", (head["code"],))
    con.execute("insert or replace into guidelines values (:code, :title, :age, :published, :url, :mkb)", head)
    abbr = head["abbr"]
    for pos, (section, text) in enumerate(parts):
        cur = con.execute("insert into passages (code, pos, section, text) values (?, ?, ?, ?)", (head["code"], pos, section, text))
        # название КР и раздела тоже в индексе: «подагра лечение аллопуринол» находит раздел «3. Лечение» нужной КР
        # и возраст («взрослые»/«дети»): запрос «пневмония у взрослых» не уходит в детскую КР;
        # сокращения раскрываются: «продолжительность АБТ» находится по «антибактериальной терапии»
        found = {w for w in re.findall(r"[A-ZА-ЯЁ][\wА-Яа-яЁё\-]*", text) if w in abbr}
        expanded = " ".join(abbr[w] for w in sorted(found))
        con.execute("insert into search (rowid, stems) values (?, ?)",
                    (cur.lastrowid, stem_text(f"{head['title']} {head['age']} {section} {text} {expanded}")))
    return head, len(parts)


def add(path):
    """Дописать одну КР в готовый индекс (её скачивает инструмент medical_research, когда КР нет локально)."""
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    head, n = index_file(con, Path(path))
    con.commit()
    con.close()
    return head, n


def main():
    tmp = DB.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    total = 0
    for path in sorted(SRC.glob("*.md")):
        total += index_file(con, path)[1]
    con.commit()
    con.close()
    tmp.replace(DB)
    print(f"готово: {DB}, КР {len(list(SRC.glob('*.md')))}, фрагментов {total}, {DB.stat().st_size // 2**20} МБ")


if __name__ == "__main__":
    main()
