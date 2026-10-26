"""Офлайн-копия инструкций к препаратам openFDA (drug/label) — запас на случай, если api.fda.gov станет недоступен.

Запуск: python -X utf8 openfda_offline.py   (раз в несколько месяцев, чтобы обновить)
Скачивает все части выгрузки (≈1,8 ГБ zip), собирает SQLite openfda_labels.db: на каждое вещество и тип препарата —
самая свежая инструкция и только разделы, которые показывает инструмент medical_research. Архивы после сборки удаляются.
download.open.fda.gov открывается напрямую; если нет — через прокси v2rayN.
"""
import io
import json
import sqlite3
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
DB = HERE / "openfda_labels.db"
TMP = HERE / "openfda_tmp"
PROXY = "http://127.0.0.1:10808"
SECTIONS = ["boxed_warning", "indications_and_usage", "dosage_and_administration", "contraindications", "do_not_use",
            "warnings_and_cautions", "warnings", "drug_interactions", "adverse_reactions", "pregnancy", "pregnancy_or_breast_feeding",
            "pediatric_use", "geriatric_use", "ask_doctor"]


def opener(proxy):
    return urllib.request.build_opener(urllib.request.ProxyHandler({"https": proxy, "http": proxy} if proxy else {}))


def fetch(url):
    last = None
    for proxy in (None, PROXY):
        try:
            with opener(proxy).open(url, timeout=600) as r:
                return r.read()
        except Exception as e:
            last = e
    raise last


def main():
    index = json.loads(fetch("https://api.fda.gov/download.json"))["results"]["drug"]["label"]
    parts = index["partitions"]
    print(f"экспорт {index['export_date']}: {len(parts)} частей, {sum(float(p['size_mb']) for p in parts):.0f} МБ", flush=True)
    TMP.mkdir(exist_ok=True)
    best = {}  # (вещество, тип) -> запись: самая свежая, однокомпонентные отдельно от комбинаций
    for n, part in enumerate(parts, 1):
        path = TMP / Path(part["file"]).name
        if not path.exists():
            path.write_bytes(fetch(part["file"]))
        with zipfile.ZipFile(path) as z:
            data = json.load(io.TextIOWrapper(z.open(z.namelist()[0]), encoding="utf-8"))
        for lab in data["results"]:
            fda = lab.get("openfda") or {}
            generic = " ".join(fda.get("generic_name") or []).strip().lower()
            if not generic:
                continue
            ptype = " ".join(fda.get("product_type") or [])
            key = (generic, ptype)
            effective = lab.get("effective_time") or ""
            if key not in best or effective > best[key]["effective"]:
                best[key] = {"generic": generic, "ptype": ptype, "effective": effective,
                             "brands": ", ".join((fda.get("brand_name") or [])[:6]),
                             "substances": " ".join(fda.get("substance_name") or []).lower(),
                             "set_id": (fda.get("spl_set_id") or [lab.get("set_id", "")])[0],
                             "sections": json.dumps({k: lab[k] for k in SECTIONS if lab.get(k)}, ensure_ascii=False)}
        print(f"[{n}/{len(parts)}] {path.name}: инструкций {len(data['results'])}, уникальных пока {len(best)}", flush=True)
    tmp_db = DB.with_suffix(".tmp")
    tmp_db.unlink(missing_ok=True)
    con = sqlite3.connect(tmp_db)
    con.execute("create table labels (generic text, ptype text, effective text, brands text, substances text, set_id text, sections text)")
    con.execute("create table meta (key text primary key, value text)")
    con.executemany("insert into labels values (:generic, :ptype, :effective, :brands, :substances, :set_id, :sections)", best.values())
    con.execute("create index labels_generic on labels(generic)")
    con.execute("insert into meta values ('export_date', ?)", (index["export_date"],))
    con.commit()
    con.execute("vacuum")
    con.close()
    tmp_db.replace(DB)
    for p in TMP.glob("*.zip"):
        p.unlink()
    TMP.rmdir()
    print(f"готово: {DB} — {len(best)} инструкций, {DB.stat().st_size // 2**20} МБ, экспорт от {index['export_date']}", flush=True)


if __name__ == "__main__":
    main()
