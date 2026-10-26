"""Выгрузка клинических рекомендаций Минздрава РФ (cr.minzdrav.gov.ru) в Markdown для базы знаний Open WebUI.

Запуск:
    python -X utf8 clinrec_fetch.py              — стартовый набор распространённых состояний (KEYS минус EXCLUDE)
    python -X utf8 clinrec_fetch.py 62_3 290_2   — конкретные рекомендации по коду (CodeVersion из clinrec_catalog.json)

Открытое API сайта: список — POST api.ashx?op=GetJsonClinrecsFilterV2, текст по разделам — GET api.ashx?op=GetClinrec2&id=<CodeVersion>.
В Markdown не попадают список литературы, состав рабочей группы и методология (около четверти объёма, для ответов бесполезны).
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

API = "https://apicr.minzdrav.gov.ru/api.ashx"
HEADERS = {"User-Agent": "Mozilla/5.0", "Origin": "https://cr.minzdrav.gov.ru", "Referer": "https://cr.minzdrav.gov.ru/",
           "Content-Type": "application/json"}
HERE = Path(__file__).parent
OUT = HERE / "clinrec"
CATALOG = HERE / "clinrec_catalog.json"
SKIP_SECTIONS = {"doc_whole", "doc_title", "doc_bible", "doc_a1", "doc_a2"}

# распространённые состояния взрослых и детей — стартовый набор для семьи
KEYS = ["артериальн.{0,3} гипертенз", "ишемическая болезнь сердца", "сердечная недостаточность", "фибрилляция", "липидн", "сахарный диабет",
        "ожирени", "гипотиреоз", "тиреоидит", "гастроэзофаг", "гастрит", "язвенная болезнь", "синдром раздраженного", "желчнокаменн", "холецистит",
        "неалкогольн", "панкреатит", "хроническая обструктивная", "бронхиальная астма", "пневмони", "острая респираторная", "острые респираторные",
        "грипп", "тонзилл", "синусит", "отит", "бронхит", "цистит", "пиелонефрит", "мочекаменн", "гиперплазия предстательной", "гонартроз",
        "коксартроз", "остеоартр", "полиартроз", "остеопороз", "подагр", "радикулопат", "мигрен", "головная боль", "ишемический инсульт",
        "депресс", "тревожн", "железодефицитн", "в12-дефицит", "фолиеводефицит", "варикозн", "тромбоз глубоких", "атопический дерматит",
        "псориаз", "аллергический ринит", "крапивниц", "COVID", "кишечн.{0,5} инфекц", "гастроэнтерит", "запор", "хроническая болезнь почек",
        "корь", "клещевой"]
EXCLUDE = re.compile(r"злокачествен|апластическ|гемолитическ|врожденн|новорожденн|недоношенн|геморрагическая лихорадка|западного нила|"
                     r"средиземноморск|грибков|паратонзилляр|гиперчувствительн|при хронической болезни почек|патологические переломы", re.I)

op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(params, body=None):
    url = API + "?" + params
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers=HEADERS, method="POST" if body else "GET")
    with op.open(req, timeout=180) as r:
        return json.load(r)


def catalog():
    items, page = [], 1
    while True:
        body = {"filters": [{"fieldName": "status", "filterType": 1, "filterValueType": 2, "value1": 0, "value2": "", "values": []}],
                "sortOption": {"fieldName": "publishdate", "sortType": 2}, "currentPage": page, "pageSize": 200}
        d = api("op=GetJsonClinrecsFilterV2", body)
        items += d["Data"]
        if not d["Data"] or len(items) >= d["TotalRecords"]:
            break
        page += 1
    CATALOG.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return items


def html_to_md(html):
    html = re.sub(r"<img[^>]*>", "", html or "")
    html = re.sub(r"</(p|div|li|tr|h\d)>|<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"<li[^>]*>", "- ", html, flags=re.I)
    html = re.sub(r"</t[dh]>", " | ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&").replace("&quot;", '"')
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def fetch(item):
    code = item["CodeVersion"]
    data = api(f"op=GetClinrec2&id={code}&ssid=undefined")
    sections = (data.get("obj") or data)["sections"]
    mkb = ", ".join(f"{m.get('MkbCode', '')} {m.get('MkbName', '')}".strip() for m in item.get("Mkbs") or [])
    parts = [f"# {item['Name'].strip()}",
             f"Клинические рекомендации Минздрава РФ, код {code}, возраст: {item['AgeCategoryStr']}, опубликованы {item['PublishDateStr'][:10]}.",
             f"Источник: https://cr.minzdrav.gov.ru/preview-cr/{code}", f"МКБ-10: {mkb}" if mkb else ""]
    for s in sections:
        if s.get("id") in SKIP_SECTIONS:
            continue
        body = html_to_md(s.get("content"))
        if body:
            parts.append(f"\n## {s.get('title', '').strip()}\n{body}")
    safe = re.sub(r'[\\/:*?"<>|]+', " ", item["Name"]).strip()[:90]
    path = OUT / f"{code} {safe}.md"
    path.write_text("\n".join(p for p in parts if p) + "\n", encoding="utf-8")
    return path


def main():
    OUT.mkdir(exist_ok=True)
    items = catalog()
    if len(sys.argv) > 1:
        chosen = [i for i in items if i["CodeVersion"] in sys.argv[1:]]
    else:
        keys = re.compile("|".join(KEYS), re.I)
        chosen = [i for i in items if keys.search(i["Name"]) and not EXCLUDE.search(i["Name"])]
    print(f"каталог: {len(items)}, выбрано: {len(chosen)}")
    for n, item in enumerate(chosen, 1):
        try:
            path = fetch(item)
            print(f"[{n}/{len(chosen)}] {path.name} ({path.stat().st_size // 1024} КБ)")
        except Exception as e:
            print(f"[{n}/{len(chosen)}] ОШИБКА {item['CodeVersion']} {item['Name']}: {e}")


if __name__ == "__main__":
    main()
