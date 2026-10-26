"""Справочник торговых названий лекарств → МНН из Государственного реестра лекарственных средств (ГРЛС).

Зачем: Gemma путает торговые названия по памяти (в калибровке приняла торговое название за другое вещество).
Фильтр task_skills_auto находит торговые названия в сообщении и дописывает справку из этой базы до того, как модель
начнёт думать, — не надеясь, что она сама вызовет инструмент.

Источник: grls.rosminzdrav.ru — «Загрузите ГРЛС одним файлом» (ZIP ≈ 18 МБ, xlsx по статусам регистрации; ссылка
GetGRLS.ashx?FileGUID=… меняется, берётся со страницы). Столбцы: торговое наименование, МНН (или химическое/группировочное
наименование), фармакотерапевтическая группа.

Ложные срабатывания: часть торговых названий — обычные слова. Однословные названия, которые часто встречаются в тексте
кодексов (D:\\llm\\law\\law.db — большой словарь обычного русского), в поиск по сообщению не берутся.

Запуск (раз в месяц-два): D:\\llm\\law\\.venv\\Scripts\\python.exe -X utf8 D:\\llm\\health\\grls_build.py
"""
import io
import re
import sqlite3
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl

HERE = Path(__file__).parent
DB = HERE / "grls.db"
LAW_DB = Path(r"D:\llm\law\law.db")
PAGE = "https://grls.rosminzdrav.ru/GRLS.aspx"
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ACTIVE = ("Действующий", "Изменённый", "ЕАЭС", "подтверждении", "иностранных")


def get(url, timeout=600):
    with OP.open(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=timeout) as r:
        return r.read()


def norm(name):
    """Ключ поиска: нижний регистр, ё→е, без ®/™ и кавычек, дефисы и пробелы схлопнуты."""
    name = name.lower().replace("ё", "е")
    name = re.sub(r"[®™©«»\"']", "", name)
    name = re.sub(r"[\s\-]+", " ", name).strip()
    return re.sub(r"^l ", "л ", name)  # «L-Тироксин» пишут и «л-тироксин»


def common_words():
    """Слова обычного русского: встречаются в кодексах не меньше 3 раз (бренды там почти не встречаются)."""
    if not LAW_DB.exists():
        return set()
    count = Counter()
    con = sqlite3.connect(LAW_DB)
    for (text,) in con.execute("select text from articles"):
        count.update(w.replace("ё", "е") for w in re.findall(r"[а-яё]{3,}", text.lower()))
    con.close()
    return {w for w, n in count.items() if n >= 3}


def main():
    page = get(PAGE, 120).decode("utf-8", "replace")
    link = re.search(r"GetGRLS\.ashx\?FileGUID=[\w-]+&UserReq=\d+", page)
    if not link:
        raise SystemExit("на странице ГРЛС не найдена ссылка на выгрузку")
    archive = zipfile.ZipFile(io.BytesIO(get("https://grls.rosminzdrav.ru/" + link.group(0))))
    names = defaultdict(lambda: {"inn": Counter(), "group": Counter(), "active": False, "trade": ""})
    for info in archive.infolist():
        status = re.sub(r"^grls[\d-]+-", "", Path(info.filename).stem)
        active = any(a in status for a in ACTIVE)
        ws = openpyxl.load_workbook(io.BytesIO(archive.read(info)), read_only=True).worksheets[0]
        for row in ws.iter_rows(min_row=6, values_only=True):
            if len(row) < 14 or not row[8]:
                continue
            trade, inn, group = str(row[8]).strip(), str(row[9] or "").strip(), str(row[13] or "").strip()
            entry = names[norm(trade)]
            entry["trade"] = entry["trade"] or trade
            if inn and inn != "~":
                entry["inn"][inn] += 1
            if group and group != "~":
                entry["group"][group] += 1
            entry["active"] |= active
        print(f"{status}: прочитано", flush=True)
    common = common_words()
    tmp = DB.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.execute("create table names (key text primary key, trade text, inn text, grp text, active integer, searchable integer)")
    skipped = 0
    for key, e in names.items():
        if not e["inn"]:
            continue
        # одно МНН разными написаниями («…+[Магния гидроксид]», «… + Магния гидроксид») — одно
        uniq = {}
        for i, _ in e["inn"].most_common():
            uniq.setdefault(re.sub(r"[\[\]\s]", "", i.lower()), i)
        inn = "; ".join(list(uniq.values())[:3])
        # искать в сообщении только настоящие бренды: не совпадающие с МНН и не обычные слова
        same_as_inn = norm(inn) == key
        searchable = not same_as_inn and len(key) >= 4 and not (" " not in key and key in common)
        skipped += not searchable and not same_as_inn
        con.execute("insert into names values (?, ?, ?, ?, ?, ?)",
                    (key, e["trade"], inn, e["group"].most_common(1)[0][0] if e["group"] else "", int(e["active"]), int(searchable)))
    con.commit()
    total, brands = con.execute("select count(*), sum(searchable) from names").fetchone()
    con.close()
    tmp.replace(DB)
    print(f"готово: {DB}, названий {total}, ищутся в сообщениях {brands}, отсеяно как обычные слова {skipped}")


if __name__ == "__main__":
    main()
