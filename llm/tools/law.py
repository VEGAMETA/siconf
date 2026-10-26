"""
title: Законы и указы РФ
description: Действующие редакции основных кодексов и законов РФ локально (база D:\\llm\\law\\law.db с официального портала pravo.gov.ru): поиск с русским стеммингом, статья по номеру со ссылками на другие статьи и обратными ссылками. Любые другие акты (указы Президента, постановления Правительства, федеральные законы, приказы) — поиск и текст в действующей редакции в ИПС «Законодательство России» (pravo.gov.ru), самые свежие — на портале опубликования.
author: local
version: 0.1.0
"""

import email
import html as htmllib
import json
import os
import re
import sqlite3
import sys
import urllib.parse
from email import policy

import aiohttp

try:
    import snowballstemmer
except ImportError:
    # без requirements: в окружении uv tool у Open WebUI нет pip, установка из шапки падает.
    # Пакет ставится uv pip; если его снесло обновлением — берём из venv сборщика базы (чистый Python)
    sys.path.append(r"D:\llm\law\.venv\Lib\site-packages")
    import snowballstemmer

DB = r"D:\llm\law\law.db"
IPS = "http://pravo.gov.ru/proxy/ips/"
PUBLICATION = "http://publication.pravo.gov.ru"
# виды актов: код классификатора ИПС (?autocomplete&nclassif=3) и id вида на портале опубликования (/api/DocumentTypes)
DOC_TYPES = {"указ": ("102000503", "0790e34b-784b-4372-884e-3282622a24bd"),
             "постановление": ("102000496", "fd5a8766-f6fd-4ac2-8fd9-66f414d314ac"),
             "распоряжение": ("102000499", "7ff5b3b5-3757-44f1-bb76-3766cabe3593"),
             "федеральный закон": ("102000505", "82a8bf1c-3bc7-47ed-827f-7affd43a7f27")}
HEADERS = {"User-Agent": "Mozilla/5.0"}
STEM = snowballstemmer.stemmer("russian")
TEXT_CHARS = 8000
ARTICLE_CHARS = 20000  # статья целиком: 99 % статей короче (ч. 6 ст. 81 ТК — на 8,6 тыс. символов)
# пометки об изменениях «(В редакции Федерального закона от …)» — шум для ответа, а места занимают до трети статьи
NOTE = re.compile(r"\s*\((?:В редакции|Дополнение|Дополнен[аоы]?|Наименование в редакции|Абзац дополнен|Часть дополнена)"
                  r"[^()]*(?:\([^()]*\)[^()]*)*\)")
ITEM = re.compile(r"^(?:\d+(?:\.\d+)*\)|[а-я]\)|[а-я]\.\d*\))")  # пункты «1)», «7.1)» и подпункты «а)» внутри части


def _connect():
    if not os.path.exists(DB):
        raise FileNotFoundError(f"no law database {DB}; run D:\\llm\\law\\law_build.py")
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def _acts(con):
    return {k: (name, red, url) for k, name, red, url in con.execute("select key, name, redaction, url from acts")}


def _act_key(con, act):
    """Ключ акта по ключу или названию: «tk», «ТК», «трудовой», «гк 2», «защите прав потребителей»…"""
    act = (act or "").strip().lower()
    if not act:
        return ""
    acts = _acts(con)
    if act in acts:
        return act
    aliases = {"трудов": "tk", "семейн": "sk", "жилищн": "zhk", "коап": "koap", "административн": "koap", "уголовн": "uk",
               "гпк": "gpk", "процессуальн": "gpk", "конституц": "constitution", "потребител": "zozpp", "зозпп": "zozpp",
               "охран": "fz323", "323": "fz323", "персональн": "fz152", "152": "fz152", "осаго": "osago"}
    for stem, key in aliases.items():
        if stem in act:
            return key
    part = re.search(r"\d", act)
    if act.startswith(("гк", "граждан")):
        return f"gk{part.group(0) if part else 1}"
    if act.startswith(("нк", "налог")):
        return f"nk{part.group(0) if part else 1}"
    if act in ("тк", "ск", "жк", "ук"):
        return {"тк": "tk", "ск": "sk", "жк": "zhk", "ук": "uk"}[act]
    return next((k for k, (name, _, _) in acts.items() if act in name.lower()), "")


def _mark_parts(text):
    """Без пометок об изменениях и с номерами частей «[ч. N]»: в кодексах части статьи не пронумерованы, а ссылаются
    на них по номеру («ч. 6 ст. 81 ТК»). Где пункты уже пронумерованы «1.», «2.» (ГК, НК, законы), текст как есть."""
    lines = [line for line in (NOTE.sub("", l).strip() for l in text.split("\n")) if line]
    if any(re.match(r"\d+(?:\.\d+)*\.\s", line) for line in lines):
        return "\n".join(lines)
    out, part = [], 0
    for line in lines:
        if line.startswith("Примечани"):
            part = None  # примечания — не части
        elif part is not None and not ITEM.match(line):
            part += 1
            line = f"[ч. {part}] {line}"
        out.append(line)
    return "\n".join(out)


async def _get(session, url, timeout=180):
    async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
        return await r.read()


def _cp1251(text):
    return urllib.parse.quote(text.encode("cp1251", "replace"))


def _ips_list(page):
    """Выдача ИПС (?list_itself=): номер документа nd, статус, заголовок, название."""
    out = []
    for el in re.split(r'<table class="list_elem', page)[1:]:
        nd = re.search(r"nd=(\d+)", el)
        status = re.search(r'tiny_italic_bold">\s*(.*?)\s*</span>', el, re.S)
        head = re.search(r'<a id="link_\d+"[^>]*>\s*(.*?)\s*</a>', el, re.S)
        name = re.search(r'</div>\s*<span class="bold">(.*?)</span>', el, re.S)
        if nd and head:
            clean = lambda s: re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", "", s))).strip()
            out.append((nd.group(1), clean(status.group(1)) if status else "", clean(head.group(1)), clean(name.group(1)) if name else ""))
    return out


def _ips_text(raw):
    """Текст из веб-архива ИПС (?savertf=): абзацы, вставные номера <span class="W9">1</span> → «.1»."""
    part = next(p for p in email.message_from_bytes(raw, policy=policy.default).walk() if p.get_content_type() == "text/html")
    page = part.get_payload(decode=True).decode(part.get_content_charset() or "cp1251", "replace")
    page = re.sub(r'<span class="W9">\s*(\d+)\s*</span>', r".\1", page)
    paras = []
    for m in re.finditer(r"<p[^>]*>(.*?)</p>", page, re.S):
        text = re.sub(r"[ \t\r\n]+", " ", htmllib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).replace("\xa0", " ")).strip()
        if text:
            paras.append(text)
    return "\n".join(paras)


class Tools:
    def search_law(self, query: str, act: str = "") -> str:
        """
        Search the current Russian codes and laws (Russian stemming): ГК (части 1-4), ГПК, ТК, СК, ЖК, КоАП, УК, НК (части 1-2), Конституция, Закон о защите прав потребителей, 323-ФЗ (охрана здоровья), 152-ФЗ (персональные данные), ОСАГО.
        :param query: Russian keywords, e.g. "возврат товара надлежащего качества", "отпуск при увольнении компенсация", "алименты на ребенка размер".
        :param act: Optional act to search only in: "тк", "гк", "гк 2", "жк", "коап", "защите прав потребителей"...
        :return: Matching articles: act, article number, title and the start of the text; open one with law_article.
        """
        try:
            con = _connect()
        except FileNotFoundError as e:
            return str(e)
        try:
            key = _act_key(con, act)
            words = [w for w in STEM.stemWords(re.findall(r"[а-яёa-z0-9]+", (query or "").lower())) if len(w) > 1]
            if not words:
                return "Pass Russian keywords."
            acts = _acts(con)
            rows = []
            for joiner in (" AND ", " OR "):  # сначала все слова, если пусто — любое
                q = joiner.join(f'"{w}"*' for w in words[:12])
                sql = ("select s.act, s.num, a.title, a.text from search s join articles a on a.act = s.act and a.num = s.num "
                       "where search match ?" + (" and s.act = ?" if key else "") + " order by bm25(search) limit 10")
                rows = con.execute(sql, (q, key) if key else (q,)).fetchall()
                if rows:
                    break
        finally:
            con.close()
        if not rows:
            return f'Nothing found for "{query}". Try other words or another act, or search_acts for other acts.'
        lines = [f'Законы РФ (действующие редакции): "{query}"' + (f" в {acts[key][0]}" if key else ""), ""]
        for n, (a, num, title, text) in enumerate(rows, 1):
            lines.append(f"[{n}] {acts[a][0]}, ст. {num}. {title}  → law_article(\"{a}\", \"{num}\")")
            lines.append("    " + re.sub(r"\s+", " ", NOTE.sub("", text))[:300])
        lines.append("\nRead the most relevant articles with law_article before answering; cite act and article.")
        return "\n".join(lines)

    def law_article(self, act: str, number: str, offset: int = 0) -> str:
        """
        Full current text of an article of a code or law from the local base, with the articles it refers to and the articles that refer to it.
        :param act: Act key or name: "tk", "gk1".."gk4", "gpk", "sk", "zhk", "koap", "uk", "nk1", "nk2", "constitution", "zozpp", "fz323", "fz152", "osago", or "ТК", "ГК", "жилищный"... For ГК and НК the part is chosen by the article number.
        :param number: Article number, e.g. "81", "1102", "18", "8.1".
        :param offset: Character offset for very long articles.
        :return: Article text, its chapter, references both ways and the official source.
        """
        try:
            con = _connect()
        except FileNotFoundError as e:
            return str(e)
        try:
            key, num = _act_key(con, act), str(number).strip().replace(",", ".")
            if key.startswith(("gk", "nk")):  # часть ГК/НК — по номеру статьи
                row = con.execute("select act from articles where act like ? and num = ?", (key[:2] + "%", num)).fetchone()
                key = row[0] if row else key
            art = con.execute("select title, chapter, text from articles where act = ? and num = ?", (key, num)).fetchone()
            acts = _acts(con)
            if not art:
                return f'No article {num} in "{act}". Acts: ' + ", ".join(f"{k} ({v[0]})" for k, v in acts.items())
            out_refs = con.execute("select distinct r.to_act, r.to_num, a.title from refs r left join articles a on a.act = r.to_act and "
                                   "a.num = r.to_num where r.act = ? and r.num = ? limit 40", (key, num)).fetchall()
            in_refs = con.execute("select distinct r.act, r.num, a.title from refs r left join articles a on a.act = r.act and "
                                  "a.num = r.num where r.to_act = ? and r.to_num = ? limit 40", (key, num)).fetchall()
        finally:
            con.close()
        title, chapter, text = art
        text = _mark_parts(text)
        name, redaction, url = acts[key]
        offset = max(0, int(offset or 0))
        more = (f"\n[… ещё {len(text) - offset - ARTICLE_CHARS} символов: law_article(\"{key}\", \"{num}\", offset={offset + ARTICLE_CHARS})]"
                if len(text) > offset + ARTICLE_CHARS else "")
        lines = [f"{name}, статья {num}. {title}", chapter, f"Редакция: {redaction}. Источник: {url}", "",
                 text[offset:offset + ARTICLE_CHARS] + more]
        ref = lambda a, n, t: f"{acts.get(a, (a,))[0]} ст. {n}" + (f" ({t[:60]})" if t else "")
        if out_refs:
            lines.append("\nСсылается на: " + "; ".join(ref(*r) for r in out_refs))
        if in_refs:
            lines.append("\nНа неё ссылаются: " + "; ".join(ref(*r) for r in in_refs))
        return "\n".join(line for line in lines if line)

    async def search_acts(self, query: str, doc_type: str = "", in_text: bool = False) -> str:
        """
        Search any Russian federal legal act in the official database pravo.gov.ru: decrees of the President (указы), government resolutions (постановления), orders (распоряжения), federal laws, ministry orders. Shows whether each act is in force. Acts published in the last days may be missing there; then the official publication portal is searched.
        :param query: Russian words from the act's title ("частичной мобилизации", "материнского капитала") or its number and year ("647 2022").
        :param doc_type: Optional: "указ", "постановление", "распоряжение", "федеральный закон".
        :param in_text: True to search the full text instead of the title (when the title words are unknown).
        :return: Acts with status (действует / утратил силу), title and nd; read one with read_act(nd).
        """
        kind = DOC_TYPES.get((doc_type or "").strip().lower())
        number = re.fullmatch(r"\s*№?\s*(\d+[\w-]*)\s+(\d{4})\s*", query or "")
        if number:
            params = f"a8={_cp1251(number.group(1))}&a8type=1&a7type=4&a7from=01.01.{number.group(2)}&a7to=31.12.{number.group(2)}"
        else:
            params = (f"a0={_cp1251(query)}" if in_text else f"a1={_cp1251(query)}&a1type=1")
        if kind:
            params += f"&a3={kind[0]}&a3type=1"
        rows = []
        try:
            async with aiohttp.ClientSession(trust_env=False) as s:
                page = (await _get(s, f"{IPS}?list_itself=&bpas=cd00000&{params}&sort=7&page=firstlast")).decode("cp1251", "replace")
                rows = _ips_list(page)
                if not rows and not number:
                    # свежие акты — на портале опубликования (там тексты — сканы PDF)
                    url = f"{PUBLICATION}/api/Documents?" + urllib.parse.urlencode(
                        {"PageSize": 10, "Index": 1, "Name": query, **({"DocumentTypes": kind[1]} if kind else {})})
                    items = json.loads(await _get(s, url, 60)).get("items") or []
                    if items:
                        lines = [f'В ИПС не найдено; портал официального опубликования: "{query}"', ""]
                        for n, x in enumerate(items, 1):
                            lines.append(f"[{n}] " + re.sub(r"\s+", " ", x.get("complexName") or "")[:220])
                            lines.append(f"    опубликован {str(x.get('publishDateShort'))[:10]} | {PUBLICATION}/document/{x.get('eoNumber')}")
                        lines.append("\nThe portal has only scanned PDFs: give the link; the text is not available to read.")
                        return "\n".join(lines)
        except Exception as e:
            return f"pravo.gov.ru error: {e}"
        if not rows:
            return f'No acts found for "{query}". Try other title words, in_text=True, or web search.'
        lines = [f'Законодательство России (pravo.gov.ru): "{query}" | найдено {len(rows)}', ""]
        for n, (nd, status, head, name) in enumerate(rows[:12], 1):
            name = f' "{name[:200]}"' if name else ""
            lines.append(f"[{n}] {head}{name} — {status or 'статус не указан'}  → read_act(\"{nd}\")")
        lines.append("\nRead the acts you rely on with read_act; prefer acts in force.")
        return "\n".join(lines)

    async def read_act(self, nd: str, offset: int = 0) -> str:
        """
        Current consolidated text (latest redaction) of any act from pravo.gov.ru by its nd number (from search_acts).
        :param nd: The act's nd number, e.g. "603354026".
        :param offset: Character offset for long acts (the answer says where to continue).
        :return: The act's text with its redaction and link.
        """
        nd = re.sub(r"\D", "", str(nd or ""))
        try:
            async with aiohttp.ClientSession(trust_env=False) as s:
                body = (await _get(s, f"{IPS}?docbody=&nd={nd}")).decode("cp1251", "replace")
                title = re.search(r"<title>(.*?)</title>", body, re.S)
                current = re.findall(r"<option value='(\d+),\d+'[^>]*selected[^>]*>([^<]*)", body)
                options = current or re.findall(r"<option value='(\d+),\d+'[^>]*>([^<]*)", body)
                rdk, label = options[-1] if options else ("0", "единственная редакция")
                text = _ips_text(await _get(s, f"{IPS}?savertf=&nd={nd}&page=all&rdk={rdk}", 600))
        except StopIteration:
            return f"No text for nd {nd}: {IPS}?docbody=&nd={nd}"
        except Exception as e:
            return f"pravo.gov.ru error: {e}"
        offset = max(0, int(offset or 0))
        more = (f"\n[… ещё {len(text) - offset - TEXT_CHARS} символов: read_act(\"{nd}\", offset={offset + TEXT_CHARS})]"
                if len(text) > offset + TEXT_CHARS else "")
        head = htmllib.unescape(title.group(1)).strip() if title else ""
        return (f"{head}\nРедакция: {label.strip()}. Источник: {IPS}?docbody=&nd={nd}&rdk={rdk}\n\n"
                + text[offset:offset + TEXT_CHARS] + more)
