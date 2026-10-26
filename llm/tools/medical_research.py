"""
title: Медицинская литература и инструкции к препаратам
description: Поиск по научной медицинской литературе (Europe PMC: PubMed и не только, с аннотациями; по умолчанию систематические обзоры, метаанализы и клинические руководства за последние 10 лет) и официальные инструкции к препаратам (openFDA, через прокси — из России закрыт). Ответы со ссылками на PubMed для проверки.
author: local
version: 0.1.0
"""

import re
import urllib.parse
from datetime import date

import aiohttp

EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
OPENFDA = "https://api.fda.gov/drug/label.json"
OPENFDA_PROXY = "http://127.0.0.1:10808"  # v2rayN: api.fda.gov отвечает 403 на запросы из России
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

    async def drug_label(self, drug: str) -> str:
        """
        Official drug label (FDA, USA) of a medicine by its international non-proprietary name: indications, dosage, contraindications, warnings, interactions, adverse reactions, pregnancy.
        Use the English generic name (INN), e.g. "ibuprofen", "metformin", "amoxicillin", not a Russian brand name.
        :param drug: English generic (INN) name of the active substance.
        :return: Main sections of the label, trimmed, with the source.
        """
        name = (drug or "").strip().lower()
        if not name:
            return "Pass the English generic name of the drug."
        quoted = urllib.parse.quote(f'"{name}"')
        # сначала рецептурная инструкция (в ней противопоказания, взаимодействия, побочные эффекты), потом безрецептурная
        queries = [f'openfda.generic_name:{quoted}+AND+openfda.product_type:"HUMAN+PRESCRIPTION+DRUG"', f"openfda.generic_name:{quoted}",
                   f"openfda.substance_name:{quoted}"]
        def score(lab):
            """Предпочесть препарат с одним веществом (не комбинацию), рецептурный, с названием, начинающимся с запроса."""
            generic = " ".join((lab.get("openfda") or {}).get("generic_name") or []).lower()
            single = " and " not in generic and "," not in generic
            return (single, generic.startswith(name), "contraindications" in lab or "adverse_reactions" in lab)

        label = None
        try:
            async with aiohttp.ClientSession(trust_env=False) as s:
                for q in queries:
                    async with s.get(f"{OPENFDA}?search={q}&limit=20", proxy=OPENFDA_PROXY, timeout=aiohttp.ClientTimeout(total=40)) as r:
                        if r.status == 200:
                            found = (await r.json(content_type=None)).get("results") or []
                            if found:
                                label = max(found, key=score)
                                break
        except Exception as e:
            return f"openFDA error: {e}. The proxy {OPENFDA_PROXY} (v2rayN) may be off."
        if not label:
            return f'No FDA label for "{drug}". Check the English generic name (INN); some drugs are not sold in the USA.'
        fda = label.get("openfda") or {}
        lines = [f"FDA drug label: {', '.join(fda.get('generic_name', [name])[:2])} | brands: {', '.join(fda.get('brand_name', [])[:4])} | "
                 f"{', '.join(fda.get('product_type', []))} | effective {label.get('effective_time', '')}",
                 "Note: US label; doses and registered indications in Russia may differ (check the Russian instruction in ГРЛС).", ""]
        for key, title in LABEL_SECTIONS:
            text = _clean(" ".join(label.get(key) or []))
            if text:
                lines.append(f"## {title}\n{text[:LABEL_SECTION_CHARS]}" + (" […]" if len(text) > LABEL_SECTION_CHARS else ""))
        if fda.get("spl_set_id"):
            lines.append(f"\nSource: https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={fda['spl_set_id'][0]}")
        return "\n".join(lines)
