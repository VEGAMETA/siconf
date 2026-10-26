"""
title: Медицинская литература и инструкции к препаратам
description: Поиск по научной медицинской литературе (Europe PMC: PubMed и не только, с аннотациями; по умолчанию систематические обзоры, метаанализы и клинические руководства за последние 10 лет) и официальные инструкции к препаратам (openFDA, через прокси — из России закрыт; если сайт недоступен — локальная копия). Ответы со ссылками на PubMed для проверки.
author: local
version: 0.3.0
"""

import json
import os
import re
import sqlite3
import urllib.parse
from datetime import date

import aiohttp

EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
OPENFDA = "https://api.fda.gov/drug/label.json"
OPENFDA_PROXY = "http://127.0.0.1:10808"  # v2rayN: api.fda.gov отвечает 403 на запросы из России
OFFLINE_DB = r"D:\llm\health\openfda_labels.db"  # запасная копия на случай недоступности сайта (D:\llm\health\openfda_offline.py)
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


class Tools:
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
