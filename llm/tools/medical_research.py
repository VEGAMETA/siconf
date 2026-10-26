"""
title: Медицинская литература и инструкции к препаратам
description: Клинические рекомендации Минздрава РФ (точный поиск по фрагментам с русским стеммингом и чтение разделов), научная медицинская литература (Europe PMC: PubMed и не только, с аннотациями; по умолчанию систематические обзоры, метаанализы и клинические руководства за последние 10 лет) и официальные инструкции к препаратам (openFDA, через прокси — из России закрыт; если сайт недоступен — локальная копия). Ответы со ссылками для проверки.
author: local
version: 0.4.0
"""

import json
import os
import re
import sqlite3
import sys
import urllib.parse
from datetime import date

import aiohttp

try:
    import snowballstemmer
except ImportError:
    # ставится uv pip в окружение Open WebUI; если его снесло обновлением — из venv сборщика базы законов (чистый Python)
    sys.path.append(r"D:\llm\law\.venv\Lib\site-packages")
    import snowballstemmer

EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
OPENFDA = "https://api.fda.gov/drug/label.json"
OPENFDA_PROXY = "http://127.0.0.1:10808"  # v2rayN: api.fda.gov отвечает 403 на запросы из России
OFFLINE_DB = r"D:\llm\health\openfda_labels.db"  # запасная копия на случай недоступности сайта (D:\llm\health\openfda_offline.py)
CLINREC_DB = r"D:\llm\health\clinrec.db"  # фрагменты клинических рекомендаций (D:\llm\health\clinrec_index.py)
STEM = snowballstemmer.stemmer("russian")
SECTION_CHARS = 12000
# общие слова названий КР — по ним нужную КР не выбрать
GENERIC = set(STEM.stemWords("острый острая хронический хроническая взрослые взрослых дети детей болезнь заболевание "
                             "инфекция синдром тип типа у при".split()))
# слова запроса, которые в КР пишут иначе: каждое ищется вместе со своими вариантами
SYNONYMS = {STEM.stemWord(k): [STEM.stemWord(v) for v in vs] for k, vs in {
    "длительность": ["продолжительность"], "продолжительность": ["длительность"], "дозировка": ["доза"], "дозы": ["доза"],
    "антибиотик": ["антибактериальный"], "антибиотики": ["антибактериальный"], "жаропонижающие": ["антипиретик", "лихорадка"],
    "температура": ["лихорадка"], "давление": ["АД"], "сахар": ["глюкоза", "гликемия"],
}.items()}
# пролонгированные и прочие модифицированные формы (так же определяет openfda_offline.py)
RELEASE = re.compile(r"extended[- ]release|delayed[- ]release|sustained[- ]release|controlled[- ]release|modified[- ]release|"
                     r"prolonged[- ]release|\b(?:ER|XR|XL|SR|CR|DR)\b", re.I)
RESULTS = 6
ABSTRACT_CHARS = 1500
LABEL_SECTION_CHARS = 1800
# доказательные типы публикаций: на них в первую очередь стоит опираться
EVIDENCE = '(PUB_TYPE:"systematic-review" OR PUB_TYPE:"Systematic Review" OR PUB_TYPE:"Meta-Analysis" OR PUB_TYPE:"Practice Guideline" OR PUB_TYPE:"Guideline" OR PUB_TYPE:"review")'
LABEL_SECTIONS = [
    ("boxed_warning", "Boxed warning"), ("indications_and_usage", "Indications"), ("dosage_and_administration", "Dosage"),
    ("contraindications", "Contraindications"), ("do_not_use", "Do not use"), ("warnings_and_cautions", "Warnings and precautions"),
    ("warnings", "Warnings"), ("drug_interactions", "Drug interactions"), ("adverse_reactions", "Adverse reactions"),
    ("pregnancy", "Pregnancy"), ("pregnancy_or_breast_feeding", "Pregnancy or breast-feeding"), ("pediatric_use", "Pediatric use"),
    ("geriatric_use", "Geriatric use"), ("ask_doctor", "Ask a doctor before use if"),
]


def _clean(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def _form(label):
    """Форма выпуска: пролонгированные и прочие модифицированные формы отдельно от обычных — у них свои дозы."""
    if label.get("_form"):
        return label["_form"]
    names = " ".join((label.get("spl_product_data_elements") or [])[:1] + ((label.get("openfda") or {}).get("brand_name") or [])[:2])
    return "modified-release" if RELEASE.search(names) else "immediate"


def _route(label):
    return ", ".join((label.get("openfda") or {}).get("route") or []).lower() or "unknown"


def _pick(labels, name, route, form):
    """Лучшая инструкция под запрошенный способ применения и форму + список других имеющихся вариантов."""
    def score(lab):
        fda = lab.get("openfda") or {}
        generic = " ".join(fda.get("generic_name") or []).lower()
        single = " and " not in generic and "," not in generic  # одно вещество, не комбинация
        # без уточнения — обычная форма внутрь (самый частый случай), потом остальные
        return (single, generic.startswith(name), "PRESCRIPTION" in " ".join(fda.get("product_type") or []),
                _form(lab) == "immediate", _route(lab) == "oral",
                "contraindications" in lab or "adverse_reactions" in lab, lab.get("effective_time") or "")
    labels = [lab for lab in labels if score(lab)[0]] or labels
    variants = sorted({(_route(lab), _form(lab)) for lab in labels})
    chosen = [lab for lab in labels if (not route or route in _route(lab)) and (not form or form in _form(lab))]
    if not chosen:
        return None, variants
    return max(chosen, key=score), variants


def _offline_labels(name):
    """Инструкции из локальной копии openFDA (D:\\llm\\health\\openfda_labels.db): (список, дата выгрузки) или ([], None)."""
    if not os.path.exists(OFFLINE_DB):
        return [], None
    con = sqlite3.connect(f"file:{OFFLINE_DB}?mode=ro", uri=True)
    try:
        exported = (con.execute("select value from meta where key = 'export_date'").fetchone() or [""])[0]
        rows = con.execute("select generic, ptype, route, form, effective, brands, set_id, sections from labels "
                           "where generic = ? or generic like ? or substances like ? limit 300",
                           (name, f"{name}%", f"%{name}%")).fetchall()
    finally:
        con.close()
    return [{"openfda": {"generic_name": [g], "product_type": [p], "route": [r for r in route.split(", ") if r],
                         "brand_name": [b for b in brands.split(", ") if b], "spl_set_id": [sid]},
             "_form": form, "effective_time": eff, **json.loads(sections)}
            for g, p, route, form, eff, brands, sid, sections in rows], exported


def _clinrec():
    if not os.path.exists(CLINREC_DB):
        raise FileNotFoundError(f"no guidelines index {CLINREC_DB}; run D:\\llm\\health\\clinrec_index.py")
    return sqlite3.connect(f"file:{CLINREC_DB}?mode=ro", uri=True)


def _guideline_line(row):
    code, title, age, published, url = row
    return f"КР {code} «{title}» ({age.lower()}, {published[:4]}) {url}"


class Tools:
    def search_guidelines(self, query: str, age: str = "", code: str = "") -> str:
        """
        Search the Russian clinical guidelines (клинические рекомендации Минздрава РФ, 92 common conditions, separate ones for adults and children) for exact passages: doses, regimens, targets, durations, criteria, recommendation grades. Returns the matching passages with guideline code and section. Use it first for any clinical question.
        :param query: Russian medical keywords as the guideline would phrase them, e.g. "целевой уровень мочевой кислоты", "внебольничная пневмония амбулаторно амоксициллин длительность", "гипертензия у беременных метилдопа".
        :param age: "adults" or "children" to search only guidelines for that age; empty for both.
        :param code: Optional guideline code to search only in, e.g. "936_1" (from an earlier result).
        :return: Up to 6 passages: guideline, section, text; read a whole section with read_guideline.
        """
        try:
            con = _clinrec()
        except FileNotFoundError as e:
            return str(e)
        words = list(dict.fromkeys(w for w in STEM.stemWords(re.findall(r"[а-яёa-z0-9]+", (query or "").lower())) if len(w) > 1))[:10]
        if not words:
            return "Pass Russian medical keywords."
        where, args = "", []
        if code:
            where, args = " and p.code = ?", [code.strip()]
        elif (age or "").lower().startswith(("adult", "взросл")):
            where, args = " and g.age = 'Взрослые'", []
        elif (age or "").lower().startswith(("child", "дет", "ребен", "ребён")):
            where, args = " and g.age = 'Дети'", []
        sql = ("select p.id, p.code, p.section, p.text, bm25(search) from search s join passages p on p.id = s.rowid "
               "join guidelines g on g.code = p.code where search match ?{} order by bm25(search) limit 6")
        term = lambda w: "(" + " OR ".join(f'"{x}"*' for x in [w] + SYNONYMS.get(w, [])) + ")"
        match = lambda ws, op=" AND ": op.join(term(w) for w in ws)

        def run(cond, cargs, need=6):
            """Сначала все слова; не хватает — варианты без одного слова (лучшие по bm25); потом любое слово."""
            q = sql.format(cond)
            rows = con.execute(q, [match(words)] + cargs).fetchall()
            if len(rows) < need and len(words) > 2:
                found = {}
                for i in range(len(words)):
                    for r in con.execute(q, [match(words[:i] + words[i + 1:])] + cargs):
                        found.setdefault(r[0], r)
                seen = {r[0] for r in rows}
                rows += sorted((r for r in found.values() if r[0] not in seen), key=lambda r: r[4])[:need - len(rows)]
            if len(rows) < need:
                seen = {r[0] for r in rows}
                rows += [r for r in con.execute(q, [match(words, " OR ")] + cargs) if r[0] not in seen][:need - len(rows)]
            return rows

        try:
            heads = {r[0]: r for r in con.execute("select code, title, age, published, url from guidelines")}
            rows = []
            if not code:
                # КР, в названии которой больше всего слов запроса («пневмония», «подагра»): сначала фрагменты из неё —
                # иначе длинные таблицы и приложения других КР перебивают её по bm25
                score = {c: len(set(words) & (set(STEM.stemWords(re.findall(r"[а-яё0-9]+", h[1].lower())) ) - GENERIC))
                         for c, h in heads.items()}
                best = max(score.values(), default=0)
                top = [c for c, s in score.items() if best and s == best]
                if top:
                    rows = run(where + f" and p.code in ({','.join('?' * len(top))})", args + top, need=4)[:4]
            seen = {r[0] for r in rows}
            rows += [r for r in run(where, args) if r[0] not in seen][:6 - len(rows)]
            rows = [r[1:4] for r in rows]
            # лучший результат — весь его подраздел: модель редко дочитывает сама, а выбор схемы зависит от соседнего
            # текста (амбулаторно или в стационаре, с сопутствующими или без)
            full = ""
            if rows:
                full = "\n".join(t for (t,) in con.execute("select text from passages where code = ? and section = ? order by pos",
                                                          rows[0][:2]))
        finally:
            con.close()
        if not rows:
            return f'Nothing found in the guidelines for "{query}". Try other words or search_medical_literature.'
        lines = [f'Клинические рекомендации Минздрава РФ: "{query}"', ""]
        for n, (c, section, text) in enumerate(rows, 1):
            lines.append(f"[{n}] {_guideline_line(heads[c])}\n    Раздел: {section}  → read_guideline(\"{c}\", \"{section.split(' › ')[-1][:40]}\")")
            if n == 1 and len(full) <= SECTION_CHARS:
                lines.append("    (весь подраздел)\n    " + full.replace("\n", "\n    "))
            else:
                lines.append("    " + text[:1500].replace("\n", "\n    "))
        lines.append("\nCite as «КР <code>, раздел <section>». The first result is the whole subsection: base the regimen on it. "
                     "Read other subsections with read_guideline when needed.")
        return "\n".join(lines)

    def read_guideline(self, code: str, section: str = "", offset: int = 0) -> str:
        """
        Read a section of a Russian clinical guideline in full, or list its sections.
        :param code: Guideline code, e.g. "936_1".
        :param section: Start of the section title, e.g. "3. Лечение", "2.3", "Приложение А3"; empty to list the sections.
        :param offset: Character offset for long sections.
        :return: The section text or the table of contents.
        """
        try:
            con = _clinrec()
        except FileNotFoundError as e:
            return str(e)
        try:
            head = con.execute("select code, title, age, published, url from guidelines where code = ?", ((code or "").strip(),)).fetchone()
            if not head:
                return f'No guideline "{code}". Find codes with search_guidelines.'
            parts = con.execute("select section, text from passages where code = ? order by pos", (head[0],)).fetchall()
        finally:
            con.close()
        sections = {}
        for s, t in parts:
            sections.setdefault(s, []).append(t)
        if not section:
            toc = "\n".join(f"- {s} ({sum(map(len, t)) // 1000 + 1} тыс. символов)" for s, t in sections.items())
            return f"{_guideline_line(head)}\nРазделы:\n{toc}"
        want = section.strip().lower()
        name = next((s for s in sections if s.lower().startswith(want)), None) or next((s for s in sections if want in s.lower()), None)
        if not name:
            return f'No section "{section}" in КР {code}. Sections: ' + "; ".join(sections)
        text = "\n".join(sections[name])
        offset = max(0, int(offset or 0))
        more = (f"\n[… ещё {len(text) - offset - SECTION_CHARS} символов: read_guideline(\"{code}\", \"{name[:40]}\", offset={offset + SECTION_CHARS})]"
                if len(text) > offset + SECTION_CHARS else "")
        return f"{_guideline_line(head)}\nРаздел: {name}\n\n{text[offset:offset + SECTION_CHARS]}{more}"

    async def search_medical_literature(self, query: str, evidence: str = "reviews", years: int = 10) -> str:
        """
        Search medical research (PubMed and more via Europe PMC) and return titles, years, publication types, abstracts and PubMed links.
        Use it for questions about diseases, symptoms, treatments, tests and medicines. Write the query in English with medical terms (e.g. "statin myalgia", "vitamin D supplementation fracture prevention").
        :param query: Short English query with medical terms; 2-6 words work best.
        :param evidence: "reviews" (default) for systematic reviews, meta-analyses and clinical guidelines; "all" to include single studies.
        :param years: How many recent years to search (default 10).
        :return: Numbered results with title, journal, year, publication type, PMID link and abstract.
        """
        years = max(1, min(int(years or 10), 50))
        parts = [f"({query})", f"PUB_YEAR:[{date.today().year - years} TO {date.today().year}]"]
        if (evidence or "reviews").lower() != "all":
            parts.append(EVIDENCE)
        params = {"query": " AND ".join(parts), "format": "json", "resultType": "core", "pageSize": RESULTS}
        try:
            async with aiohttp.ClientSession(trust_env=False) as s:
                async with s.get(EUROPE_PMC, params=params, timeout=aiohttp.ClientTimeout(total=40)) as r:
                    data = await r.json(content_type=None)
        except Exception as e:
            return f"Europe PMC error: {e}"
        results = (data.get("resultList") or {}).get("result") or []
        if not results:
            hint = ' Try evidence="all" or other words.' if (evidence or "reviews").lower() != "all" else " Try other or fewer words."
            return f'No results for "{query}".{hint}'
        lines = [f'Europe PMC: "{query}" | {data.get("hitCount")} found | showing {len(results)} | evidence: {evidence} | years: last {years}', ""]
        for n, r in enumerate(results, 1):
            types = ", ".join(((r.get("pubTypeList") or {}).get("pubType")) or [])
            journal = ((r.get("journalInfo") or {}).get("journal") or {}).get("title") or r.get("journalTitle") or ""
            pmid = r.get("pmid")
            link = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else (f"https://doi.org/{r['doi']}" if r.get("doi") else "")
            lines.append(f"[{n}] {_clean(r.get('title'))}")
            lines.append(f"    {journal}, {r.get('pubYear')} | {types} | cited by {r.get('citedByCount', 0)} | {link}")
            abstract = _clean(r.get("abstractText"))
            if abstract:
                lines.append("    Abstract: " + abstract[:ABSTRACT_CHARS] + (" […]" if len(abstract) > ABSTRACT_CHARS else ""))
            lines.append("")
        lines.append("Cite results by number with their links. Prefer systematic reviews, meta-analyses and guidelines; say when evidence is weak or mixed.")
        return "\n".join(lines)

    async def drug_label(self, drug: str, route: str = "", form: str = "") -> str:
        """
        Official drug label (FDA, USA) of a medicine by its international non-proprietary name: indications, dosage, contraindications, warnings, interactions, adverse reactions, pregnancy.
        Use the English generic name (INN), e.g. "ibuprofen", "metformin", "amoxicillin", not a Russian brand name.
        Tablets and a gel, or a normal and an extended-release form, have different labels and doses: pass route and form when you know them; the result lists the other forms available.
        :param drug: English generic (INN) name of the active substance.
        :param route: Optional route: "oral", "topical", "intravenous", "intramuscular", "ophthalmic", "nasal", "rectal", "transdermal"...
        :param form: Optional: "immediate" (normal) or "modified-release" (extended, delayed or sustained release).
        :return: Main sections of the label, trimmed, with the source and the other available forms.
        """
        name = (drug or "").strip().lower()
        route, form = (route or "").strip().lower(), (form or "").strip().lower()
        if form and form not in ("immediate", "modified-release"):
            form = "modified-release" if RELEASE.search(form) or "extend" in form or "prolong" in form else "immediate"
        if not name:
            return "Pass the English generic name of the drug."
        quoted = urllib.parse.quote(f'"{name}"')
        queries = [f"openfda.generic_name:{quoted}", f"openfda.substance_name:{quoted}"]
        labels, offline, online_error = [], None, None
        try:
            async with aiohttp.ClientSession(trust_env=False) as s:
                for q in queries:
                    async with s.get(f"{OPENFDA}?search={q}&limit=100", proxy=OPENFDA_PROXY, timeout=aiohttp.ClientTimeout(total=40)) as r:
                        if r.status == 200:
                            labels = (await r.json(content_type=None)).get("results") or []
                            if labels:
                                break
                        elif r.status != 404:  # 404 — просто не найдено; остальное (403, 5xx) — сайт недоступен
                            online_error = f"HTTP {r.status}"
                            break
        except Exception as e:
            online_error = str(e) or type(e).__name__
        if online_error:
            # сайт недоступен (прокси выключен или заблокирован) — локальная копия, собранная openfda_offline.py
            labels, offline = _offline_labels(name)
            if not labels:
                return (f"openFDA is unreachable ({online_error}; proxy {OPENFDA_PROXY}) and the offline copy has no label for \"{drug}\"."
                        if offline else f"openFDA is unreachable ({online_error}) and there is no offline copy ({OFFLINE_DB}).")
        if not labels:
            return f'No FDA label for "{drug}". Check the English generic name (INN); some drugs are not sold in the USA.'
        label, variants = _pick(labels, name, route, form)
        listed = "; ".join(f"{r} {f}" for r, f in variants)
        if not label:
            return f'No FDA label for "{drug}" with route "{route}" and form "{form}". Available: {listed}. Call again with one of them.'
        fda = label.get("openfda") or {}
        lines = [f"FDA drug label: {', '.join(fda.get('generic_name', [name])[:2])} | brands: {', '.join(fda.get('brand_name', [])[:4])} | "
                 f"{', '.join(fda.get('product_type', []))} | route: {_route(label)} | form: {_form(label)} | effective {label.get('effective_time', '')}",
                 "Note: US label; doses and registered indications in Russia may differ (check the Russian instruction in ГРЛС)."]
        if len(variants) > 1:
            lines.append(f"Other forms with their own labels and doses: {listed}. If the user's form differs, call drug_label again with route/form.")
        if offline:
            lines.append(f"Offline copy of openFDA from {offline} (the site is unreachable now); newer label changes may be missing.")
        lines.append("")
        for key, title in LABEL_SECTIONS:
            text = _clean(" ".join(label.get(key) or []))
            if text:
                lines.append(f"## {title}\n{text[:LABEL_SECTION_CHARS]}" + (" […]" if len(text) > LABEL_SECTION_CHARS else ""))
        if fda.get("spl_set_id"):
            lines.append(f"\nSource: https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={fda['spl_set_id'][0]}")
        return "\n".join(lines)
