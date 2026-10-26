"""Законы РФ в действующей редакции для инструмента law: база law.db (статьи, полнотекстовый поиск с русским стеммингом, граф ссылок).

Источник — официальный портал «Законодательство России» (pravo.gov.ru, ИПС): для каждого акта берётся номер последней редакции
со страницы ?docbody=&nd=<nd>, затем весь текст этой редакции одним файлом ?savertf=&nd=<nd>&page=all&rdk=<редакция>
(веб-архив MHTML с HTML внутри; обычная страница doc_itself отдаёт только начало больших кодексов).
Вставные статьи размечены как «Статья 8<span class="W9">1</span>» — это статья 8.1.
Ссылки между статьями достаются регулярными выражениями («статьёй 450 настоящего Кодекса», «статьи 18 Закона о защите прав
потребителей»), без языковой модели.

Запуск: D:\\llm\\law\\.venv\\Scripts\\python.exe -X utf8 law_build.py   (раз в месяц-два, чтобы обновить редакции);
только отдельные акты, в готовой базе: ... law_build.py nk2 tk
"""
import email
import html as htmllib
import re
import sqlite3
import sys
import time
import urllib.request
from email import policy
from pathlib import Path

import snowballstemmer

HERE = Path(__file__).parent
DB = HERE / "law.db"
IPS = "http://pravo.gov.ru/proxy/ips/"
# ключ, короткое название, номер документа в ИПС, как акт называют в ссылках из других актов (родительный падеж, начало)
ACTS = [
    ("constitution", "Конституция РФ", "102027595", r"Конституци"),
    ("gk1", "ГК РФ, часть 1", "102033239", r"Гражданского кодекса"),
    ("gk2", "ГК РФ, часть 2", "102039276", r"Гражданского кодекса"),
    ("gk3", "ГК РФ, часть 3", "102073578", r"Гражданского кодекса"),
    ("gk4", "ГК РФ, часть 4", "102110716", r"Гражданского кодекса"),
    ("gpk", "ГПК РФ", "102078828", r"Гражданского процессуального кодекса"),
    ("tk", "ТК РФ", "102074279", r"Трудового кодекса"),
    ("sk", "СК РФ", "102038925", r"Семейного кодекса"),
    ("zhk", "ЖК РФ", "102090645", r"Жилищного кодекса"),
    ("koap", "КоАП РФ", "102074277", r"Кодекса Российской Федерации об административных правонарушениях"),
    ("uk", "УК РФ", "102041891", r"Уголовного кодекса"),
    ("nk1", "НК РФ, часть 1", "102054722", r"Налогового кодекса"),
    ("nk2", "НК РФ, часть 2", "102067058", r"Налогового кодекса"),
    ("zozpp", "Закон о защите прав потребителей", "102014512", r"Закона (?:Российской Федерации )?(?:\"|«)?О защите прав потребителей"),
    ("fz323", "323-ФЗ об основах охраны здоровья граждан", "102152259", r"Федерального закона (?:\"|«)?Об основах охраны здоровья"),
    ("fz152", "152-ФЗ о персональных данных", "102108261", r"Федерального закона (?:\"|«)?О персональных данных"),
    ("osago", "40-ФЗ об ОСАГО", "102075866", r"Федерального закона (?:\"|«)?Об обязательном страховании гражданской ответственности"),
]
GK_PARTS = {"gk1": (1, 453), "gk2": (454, 1109), "gk3": (1110, 1224), "gk4": (1225, 1551)}  # части ГК: диапазоны статей
NK_PARTS = {"nk1": (1, 142.9), "nk2": (143, 9999)}
STEM = snowballstemmer.stemmer("russian")
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(url, timeout=600, tries=3):
    for attempt in range(tries):
        try:
            with OP.open(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=timeout) as r:
                return r.read()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(10)


def stem_text(text):
    return " ".join(STEM.stemWords(re.findall(r"[а-яёa-z0-9]+", text.lower())))


def latest_redaction(nd, tries=4):
    for attempt in range(tries):
        page = get(f"{IPS}?docbody=&nd={nd}").decode("cp1251", "replace")
        title = re.search(r"<title>(.*?)</title>", page, re.S)
        # действующая редакция помечена selected (обычно последняя; подпись бывает с датой принятия, а не изменения)
        current = re.findall(r"<option value='(\d+),\d+'[^>]*selected[^>]*>([^<]*)", page)
        options = current or re.findall(r"<option value='(\d+),\d+'[^>]*>([^<]*)", page)
        if title and options:
            rdk, label = options[-1]
            return title.group(1).strip(), rdk, label.strip()
        time.sleep(30)  # под нагрузкой ИПС отдаёт страницу без списка редакций — тогда взялась бы исходная редакция
    raise RuntimeError(f"нет списка редакций для nd={nd}")


def full_html(nd, rdk):
    raw = get(f"{IPS}?savertf=&nd={nd}&page=all&rdk={rdk}")
    part = next(p for p in email.message_from_bytes(raw, policy=policy.default).walk() if p.get_content_type() == "text/html")
    return part.get_payload(decode=True).decode(part.get_content_charset() or "cp1251", "replace")


def paragraphs(page):
    """(класс, текст) по абзацам; вставные номера <span class="W9">1</span> → «.1»."""
    page = re.sub(r'<span class="W9">\s*(\d+)\s*</span>', r".\1", page)
    for m in re.finditer(r'<p(?: class="([^"]*)")?[^>]*>(.*?)</p>', page, re.S):
        text = htmllib.unescape(re.sub(r"<[^>]+>", "", m.group(2))).replace("\xa0", " ")
        text = re.sub(r"[ \t\r\n]+", " ", text).strip()
        if text:
            yield m.group(1) or "", text


def articles(page):
    """Статьи: номер, заголовок, раздел/глава, текст."""
    current, chapter, out = None, "", []
    for cls, text in paragraphs(page):
        head = re.match(r"Статья\s+(\d+(?:\.\d+)*)\.?\s*(.*)", text)
        if head and (cls == "H" or len(text) < 300):
            if current:
                out.append(current)
            current = {"num": head.group(1), "title": head.group(2).strip(), "chapter": chapter, "lines": []}
        elif re.match(r"(?:Раздел|Глава|ГЛАВА|РАЗДЕЛ|Подраздел|Параграф|§)\s", text) and len(text) < 300:
            chapter = text if not text.startswith(("Параграф", "§")) else (chapter.split(" | ")[0] + " | " + text)
        elif current:
            current["lines"].append(text)
    if current:
        out.append(current)
    for a in out:
        a["text"] = "\n".join(a.pop("lines"))
    return out


REF_ARTICLE = re.compile(r"стать(?:я|и|ей|ю|е|ями|ях|ям)\s+((?:\d+(?:\.\d+)*(?:\s*(?:,|и|-|–)\s*)?)+)(\s+(?:настоящего\s+(?:Кодекса|Федерального закона|Закона)|"
                         r"[А-ЯЁ][^.;:()]{0,120}))?", re.I)


def references(key, text, act_patterns):
    """Ссылки статьи: [(акт, номер)] — свой акт («настоящего Кодекса» или без названия) или другой из списка."""
    refs = set()
    for m in REF_ARTICLE.finditer(text):
        nums = re.findall(r"\d+(?:\.\d+)*", m.group(1))
        tail = m.group(2) or ""
        target = key
        if tail and not re.search(r"настоящего", tail):
            target = next((k for k, pat in act_patterns if re.match(r"\s*" + pat, tail)), None)
        if target:
            for n in nums:
                refs.add((target, n))
    return refs


def resolve_part(target, num):
    """«статья 1102 Гражданского кодекса» → нужная часть ГК (и так же для НК)."""
    parts = GK_PARTS if target.startswith("gk") else NK_PARTS if target.startswith("nk") else None
    if not parts:
        return target
    whole = float(num.split(".")[0])
    return next((k for k, (lo, hi) in parts.items() if lo <= whole <= hi), target)


def build_act(con, key, name, nd, act_patterns):
    title, rdk, label = latest_redaction(nd)
    arts = articles(full_html(nd, rdk))
    for table, col in (("acts", "key"), ("articles", "act"), ("refs", "act"), ("search", "act")):
        con.execute(f"delete from {table} where {col} = ?", (key,))
    url = f"http://pravo.gov.ru/proxy/ips/?docbody=&nd={nd}&rdk={rdk}"
    con.execute("insert into acts values (?, ?, ?, ?, ?, ?, date('now'))", (key, name, title, nd, label, url))
    seen = set()
    for a in arts:
        if a["num"] in seen:  # редкие дубли номеров (примечания, приложения) — первый вариант
            continue
        seen.add(a["num"])
        con.execute("insert into articles values (?, ?, ?, ?, ?)", (key, a["num"], a["title"], a["chapter"], a["text"]))
        con.execute("insert into search values (?, ?, ?)", (key, a["num"], stem_text(f"{a['title']} {a['title']} {a['text']}")))
        for to_act, to_num in references(key, a["text"], act_patterns):
            to_act = resolve_part(to_act, to_num)
            if (to_act, to_num) != (key, a["num"]):
                con.execute("insert into refs values (?, ?, ?, ?)", (key, a["num"], to_act, to_num))
    con.commit()
    print(f"{name}: редакция «{label}», статей {len(seen)}", flush=True)


def main(only=()):
    """Без аргументов — вся база заново; с ключами актов (law_build.py nk2 tk) — только они, в готовой базе."""
    act_patterns = [(k, pat) for k, _, _, pat in ACTS]
    if only:
        con = sqlite3.connect(DB)
        for key, name, nd, _ in ACTS:
            if key in only:
                build_act(con, key, name, nd, act_patterns)
        con.close()
        return
    tmp = DB.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript("""
        create table acts (key text primary key, name text, title text, nd text, redaction text, url text, fetched text);
        create table articles (act text, num text, title text, chapter text, text text, primary key (act, num));
        create table refs (act text, num text, to_act text, to_num text);
        create virtual table search using fts5(act unindexed, num unindexed, stems, tokenize='unicode61');
        create index refs_from on refs(act, num);
        create index refs_to on refs(to_act, to_num);
    """)
    for key, name, nd, _ in ACTS:
        try:
            build_act(con, key, name, nd, act_patterns)
        except Exception as e:
            print(f"ОШИБКА {name}: {e}", flush=True)
    con.close()
    tmp.replace(DB)
    print(f"готово: {DB} ({DB.stat().st_size // 2**20} МБ)", flush=True)


if __name__ == "__main__":
    main(set(sys.argv[1:]))
