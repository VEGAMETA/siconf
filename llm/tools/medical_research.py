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


EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
ICITE = "https://icite.od.nih.gov/api/pubs"
STUDY_FILTERS = {"rct": "randomized controlled trial[pt]", "meta": "(meta-analysis[pt] OR systematic review[pt])",
                 "guideline": "(guideline[pt] OR practice guideline[pt])", "review": "review[pt]"}
# вес дизайна исследования при ранжировании
DESIGN = [("Retracted Publication", None), ("Meta-Analysis", 2.2), ("Systematic Review", 2.0), ("Practice Guideline", 2.0),
          ("Guideline", 1.8), ("Randomized Controlled Trial", 1.8), ("Clinical Trial", 0.8), ("Comparative Study", 0.8),
          ("Multicenter Study", 0.6), ("Observational Study", 0.5), ("Review", 0.5),
          ("Case Reports", -1.0), ("Comment", -2.0), ("Letter", -2.0), ("Editorial", -2.0)]
WEAK_JOURNALS = {"cureus", "medicine (baltimore)", "j pak med assoc", "pak j med sci"}  # много слабых работ — понижаются
STOP = {"the", "of", "in", "and", "or", "with", "for", "vs", "versus", "a", "an", "on", "to", "by", "patients", "disease"}
# как пишут в заголовках статей о приёме лекарств (модель пишет «once daily vs twice daily» — статьи «single daily dose»)
EN_PHRASES = [(r"\bonce[- ]daily\b|\bonce a day\b", "single daily dose"), (r"\btwice[- ]daily\b|\btwice a day\b", "divided dose"),
              (r"\bstarting dose\b", "initial dose")]
# слова, которые сужают поиск PubMed, не добавляя смысла: при пустой выдаче выбрасываются первыми
GENERIC_EN = {"disease", "diseases", "rate", "rates", "standard", "dosing", "dosage", "comparison", "compared", "comparing",
              "study", "studies", "trial", "trials", "randomized", "patients", "patient", "efficacy", "effectiveness", "safety",
              "outcome", "outcomes", "treatment", "therapy", "management", "regimen", "regimens", "versus", "vs", "meta-analysis",
              "systematic", "review", "adults", "adult", "clinical", "effect", "effects"}


def _abstract(article):
    """Аннотация: сначала результаты и выводы (в них цифры), потом остальное."""
    parts = [(el.get("Label") or "", "".join(el.itertext()).strip()) for el in article.iter("AbstractText")]
    key = [f"{lab}: {t}" if lab else t for lab, t in parts if re.match(r"(RESULT|CONCLUSION|FINDING|INTERPRETATION)", lab or "", re.I)]
    rest = [f"{lab}: {t}" if lab else t for lab, t in parts if not re.match(r"(RESULT|CONCLUSION|FINDING|INTERPRETATION)", lab or "", re.I)]
    if key:
        return " ".join(key)
    text = " ".join(rest)
    # без разметки разделов выводы — в конце аннотации: начало (что изучали) и конец (цифры и вывод)
    return text if len(text) <= ABSTRACT_CHARS else text[:300] + " […] " + text[-(ABSTRACT_CHARS - 320):]


async def _pubmed(query, study_type, years):
    import math
    import xml.etree.ElementTree as ET
    import asyncio
    # PubMed требует все слова запроса, а модель пишет длинно («metformin once daily vs twice daily dosing efficacy safety»
    # — 0 статей). Ослабление по шагам: формулировки статей («once daily» в заголовках — «single daily dose»); без чисел,
    # связок и общих слов; варианты без одного слова, кроме первого (это препарат или болезнь) — найденное объединяется.
    # Обрезка до первых слов и «любое из слов» давали мусор (блокады нервов в ортопедии, онкология)
    phrased = query
    for a, b in EN_PHRASES:
        phrased = re.sub(a, b, phrased, flags=re.I)
    content = [w for w in re.findall(r"[\w'-]+", phrased)
               if not re.fullmatch(r"\d+([.,]\d+)?|mg|mcg|g|kg|vs|versus|or|and|of|the|in|with|for|on|to", w, re.I)]
    core = [w for w in content if w.lower().strip("'") not in GENERIC_EN]
    variants = list(dict.fromkeys([query, phrased, " ".join(core)]))
    drop_one = [" ".join(core[:i] + core[i + 1:]) for i in range(1, len(core))] if len(core) > 2 else []
    design = f" AND {STUDY_FILTERS[study_type]}" if study_type in STUDY_FILTERS else ""
    humans = " NOT (animals[mh] NOT humans[mh])"

    async def ncbi(s, endpoint, params, parse):
        """NCBI без ключа — 3 запроса в секунду; сверх лимита вместо данных приходит ошибка: пауза и повтор."""
        for attempt in range(4):
            await asyncio.sleep(0.4 + attempt * 1.2)
            async with s.get(EUTILS + endpoint, params={**params, "tool": "local-owui"}) as r:
                body = await r.read()
            try:
                return parse(body)
            except Exception:
                if attempt == 3:
                    raise RuntimeError(f"NCBI {endpoint}: {body[:150]!r}")

    async with aiohttp.ClientSession(trust_env=False, timeout=aiohttp.ClientTimeout(total=60)) as s:
        async def search(q, n=40, filtered=True):
            params = {"db": "pubmed", "retmode": "json", "retmax": n, "sort": "relevance",
                      "term": f"({q})" + (design if filtered else "") + humans}
            if years > 0:
                params.update({"datetype": "pdat", "mindate": date.today().year - years, "maxdate": date.today().year})
            return (await ncbi(s, "esearch.fcgi", params, lambda b: json.loads(b)["esearchresult"])).get("idlist") or []

        ids, used = [], []
        for q in variants:
            ids = await search(q)
            if ids:
                used = [q]
                break
        if not ids:
            for q in drop_one:
                found = await search(q, 15)
                ids += [i for i in found if i not in ids]
                used += [q] if found else []
        if ids and design:
            # плюс без фильтра по дизайну: крупные сравнительные когорты (в вопросах доз и безопасности их много) тоже
            # попадают в список — ниже РКИ и мета-анализов по весу дизайна
            for q in used[:2]:
                ids += [i for i in await search(q, 15, filtered=False) if i not in ids]
        ids = ids[:50]
        found = {"count": len(ids)}
        query = " | ".join(used) or query
        if not ids:
            return f'No PubMed results for "{query}" (study_type={study_type}). Use fewer or broader words, or study_type="any".'
        root = await ncbi(s, "efetch.fcgi", {"db": "pubmed", "retmode": "xml", "id": ",".join(ids)}, ET.fromstring)
        try:
            async with s.get(ICITE, params={"pmids": ",".join(ids), "fl": "pmid,citation_count,relative_citation_ratio"}) as r:
                icite = {str(x["pmid"]): x for x in (await r.json(content_type=None)).get("data", [])}
        except Exception:
            icite = {}
    words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if w not in STOP and len(w) > 2}
    items = []
    for rank, art in enumerate(root.iter("PubmedArticle")):
        pmid = art.findtext(".//PMID")
        title = "".join(art.find(".//ArticleTitle").itertext()) if art.find(".//ArticleTitle") is not None else ""
        journal = art.findtext(".//Journal/ISOAbbreviation") or art.findtext(".//Journal/Title") or ""
        year = art.findtext(".//JournalIssue/PubDate/Year") or (art.findtext(".//JournalIssue/PubDate/MedlineDate") or "")[:4]
        types = [t.text for t in art.iter("PublicationType")]
        weights = [w for t, w in DESIGN if t in types]
        if None in weights:
            continue  # отозванные статьи
        info = icite.get(pmid, {})
        rcr = info.get("relative_citation_ratio") or 0
        overlap = len(words & set(re.findall(r"[a-z0-9]+", title.lower()))) / max(1, len(words))
        score = (3 * (1 - rank / 40) + max(weights, default=0) + min(math.log2(1 + rcr), 2.5) + 2 * overlap
                 - (1.5 if journal.lower().rstrip(".") in WEAK_JOURNALS else 0))
        items.append((score, pmid, title, journal, year, [t for t in types if t not in ("Journal Article",)], info, _abstract(art)))
    items.sort(key=lambda x: -x[0])
    lines = [f'PubMed: "{query}" | study_type={study_type} | {found.get("count")} found, best 8 of {len(items)} by relevance, design and citations', ""]
    for n, (_, pmid, title, journal, year, types, info, abstract) in enumerate(items[:8], 1):
        cites = f"cited {info.get('citation_count', '?')}, RCR {info.get('relative_citation_ratio') or 0:.1f}" if info else ""
        lines.append(f"[{n}] {_clean(title)}")
        lines.append(f"    {journal} {year} | {', '.join(types[:3]) or 'article'} | {cites} | https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
        if abstract:
            lines.append("    " + _clean(abstract)[:ABSTRACT_CHARS] + (" […]" if len(abstract) > ABSTRACT_CHARS else ""))
        lines.append("")
    lines.append("Use only studies whose comparison matches the question (check what the title compares: A vs B); ignore the rest. "
                 "Cite by number with the PubMed link; state design, number of patients and the result numbers from the abstract. "
                 "Claims about safety or efficacy must come from these abstracts, not from memory. If nothing matches, search again "
                 "with other words. RCR = citations relative to the field (1.0 = average).")
    return "\n".join(lines)


# ---- search_evidence: запрос строит инструмент (PICO + рубрики MeSH), выдача по уровням доказательности ----

# что выясняем → условие PubMed. {m} — рубрика MeSH препарата: подрубрики «/administration and dosage», «/adverse effects»
# размечают статьи по смыслу, независимо от слов в заголовке
ASPECTS = {
    # подрубрика — только как главная тема статьи ([majr]): с [mh] «дозирование» стоит и там, где препарат лишь фон
    "dose": '("{m}/administration and dosage"[majr] OR dose[ti] OR doses[ti] OR dosage[ti] OR dosages[ti] OR "high-dose"[tiab] '
            'OR "low-dose"[tiab] OR "initial dose"[tiab] OR "dose-response"[tiab])',
    "frequency": '("single daily"[tiab] OR "once daily"[tiab] OR "once-daily"[tiab] OR "divided dose"[tiab] OR "divided doses"[tiab] '
                 'OR "twice daily"[tiab] OR "dosing frequency"[tiab] OR "dosing interval"[tiab])',
    "duration": '(duration[ti] OR "long-term"[ti] OR "short-term"[ti] OR withdrawal[ti] OR discontinuation[ti] '
                'OR "treatment duration"[tiab] OR "duration of treatment"[tiab] OR "duration of therapy"[tiab])',
    "regimen": '(regimen[tiab] OR regimens[tiab] OR titration[tiab] OR combination[ti] OR strategy[ti] OR protocol[ti])',
    "safety": '("{m}/adverse effects"[majr] OR adverse[ti] OR safety[ti] OR toxicity[ti] OR "side effects"[ti] OR "adverse events"[tiab])',
    "efficacy": '("{m}/therapeutic use"[majr] OR efficacy[ti] OR effectiveness[ti])',
}
# как модель называет аспект → ключ ASPECTS («dosage» вместо «dose» давало поиск без аспекта)
ASPECT_ALIASES = {"dose": r"dos(e|es|age|ing)$|^how much|amount|mg", "frequency": r"frequen|how often|times a day|once|twice|divided|schedul|interval",
                  "duration": r"duration|how long|length|stop|withdraw|discontinu", "regimen": r"regimen|scheme|strateg|protocol|titrat|combination|block",
                  "safety": r"safe|adverse|side|toxic|risk", "efficacy": r"effic|effective|remission|outcome|benefit"}
# слова, которые не несут понятия в названии лечения («block and replace therapy» → block replace)
CONCEPT_STOP = {"and", "or", "of", "the", "with", "for", "in", "therapy", "treatment", "regimen", "drug", "drugs", "use"}
# слова аспекта в заголовке — бонус при сортировке внутри уровня
ASPECT_TITLE = {"dose": r"\bdos(e|es|age|ing)\b|\bmg\b|high.dose|low.dose", "frequency": r"single daily|once|divided|twice|frequency|interval",
                "duration": r"long.term|short.term|duration|withdraw|discontinu|\byears?\b|\bmonths?\b",
                "regimen": r"regimen|titrat|block|combination|strategy|protocol", "safety": r"adverse|safety|toxic|side effect|agranulocyt|hepat|risk",
                "efficacy": r"efficacy|effective|remission|outcome"}
TIERS = [("Руководства", "(guideline[pt] OR practice guideline[pt])", 2),
         ("Мета-анализы и систематические обзоры", "(meta-analysis[pt] OR systematic review[pt])", 3),
         ("РКИ", "randomized controlled trial[pt]", 4),
         ("Крупные сравнительные и наблюдательные исследования",
          "((comparative study[pt] OR observational study[pt] OR multicenter study[pt] OR clinical trial[pt]) NOT randomized controlled trial[pt])", 3)]
HUMANS = " NOT (animals[mh] NOT humans[mh])"


async def _ncbi(s, endpoint, params, parse):
    """NCBI без ключа — 3 запроса в секунду; сверх лимита вместо данных приходит ошибка: пауза и повтор."""
    import asyncio
    for attempt in range(4):
        await asyncio.sleep(0.4 + attempt * 1.2)
        async with s.get(EUTILS + endpoint, params={**params, "tool": "local-owui"}) as r:
            body = await r.read()
        try:
            return parse(body)
        except Exception:
            if attempt == 3:
                raise RuntimeError(f"NCBI {endpoint}: {body[:150]!r}")


async def _mesh(s, text):
    """Рубрика MeSH по автоматическому сопоставлению терминов PubMed («acetylsalicylic acid» → aspirin); нет — None."""
    if not text:
        return None
    r = await _ncbi(s, "esearch.fcgi", {"db": "pubmed", "retmode": "json", "retmax": 0, "term": text},
                    lambda b: json.loads(b)["esearchresult"])
    translations = r.get("translationset") or []
    # всё написанное целиком сопоставлено рубрике — это синоним («paracetamol» → acetaminophen), берём
    for x in translations:
        if x.get("from", "").lower().strip() == text.lower().strip():
            whole = re.findall(r'"([^"]+)"\[MeSH Terms\]', x.get("to", ""))
            if whole:
                return whole[0]
    found = re.findall(r'"([^"]+)"\[MeSH Terms\]', " ".join(x.get("to", "") for x in translations))
    # сопоставлена только часть фразы — рубрика должна совпадать с написанным хоть одним значимым словом: в «block and
    # replace therapy» PubMed сводит «therapy» к «therapeutics», и такая рубрика уводит поиск в сторону
    words = {w.lower()[:6] for w in re.findall(r"[\w'-]+", text) if w.lower() not in CONCEPT_STOP}
    for term in found:
        if words & {w.lower()[:6] for w in re.findall(r"[\w'-]+", term)}:
            return term
    return None


async def _drug_class(s, mesh):
    """Фармакологические группы вещества по MeSH («Allopurinol» → «Gout Suppressants»): в PubMed — поле [pa]."""
    if not mesh:
        return []
    try:
        uids = await _ncbi(s, "esearch.fcgi", {"db": "mesh", "retmode": "json", "retmax": 1, "term": f'"{mesh}"[mh]'},
                           lambda b: json.loads(b)["esearchresult"]["idlist"])
        if not uids or not uids[0].startswith("68"):
            return []
        async with s.get(f"https://id.nlm.nih.gov/mesh/D{uids[0][2:]}.json") as r:
            pa = (await r.json(content_type=None)).get("pharmacologicalAction") or []
        labels = []
        for uri in ([pa] if isinstance(pa, str) else pa)[:3]:
            async with s.get(uri.replace("http://", "https://") + ".json") as r:
                label = (await r.json(content_type=None)).get("label")
            labels.append(label.get("@value") if isinstance(label, dict) else label)
        return [x for x in labels if x]
    except Exception:
        return []


def _concept(text, mesh):
    """Рубрика MeSH или те же слова в заголовке/аннотации (свежие статьи ещё без рубрик). Слова сверх рубрики
    («metformin extended release» → рубрика metformin) обязательны фразой: иначе пропадает различие форм."""
    words = [w for w in re.findall(r"[\w'-]+", text) if w.lower() not in CONCEPT_STOP] or re.findall(r"[\w'-]+", text)
    term = " AND ".join(f"{w}[tiab]" for w in words)
    if not mesh:
        return f"({term})"
    extra = [w for w in words if w.lower() not in mesh.lower()]
    core = f'("{mesh}"[mh] OR ({term}))'
    if not extra or len(extra) >= len(words):
        return core
    phrase = " ".join(extra).lower()
    if re.search(r"release|acting", phrase):
        # формы с замедленным высвобождением называют по-разному: модель пишет «prolonged-release», статьи — «extended-release»
        forms = ["extended release", "prolonged release", "modified release", "sustained release", "slow release",
                 "controlled release", "delayed release", "long acting"]  # без ER/SR: «Exenatide ER», эстрогеновые рецепторы
        if re.search(r"immediate|ordinary|regular", phrase):
            forms = ["immediate release"]
        # форма — в заголовке: в аннотациях «extended-release» встречается у чего угодно (эксенатид, фоновая терапия)
        return f'({core} AND (' + " OR ".join(f'"{f}"[ti]' for f in forms) + "))"
    return f'({core} AND "{phrase}"[tiab])'


def _card(art):
    """Карточка статьи: дизайн из разметки PubMed, число пациентов, предложения результатов с цифрами."""
    title = "".join(art.find(".//ArticleTitle").itertext()) if art.find(".//ArticleTitle") is not None else ""
    abstract = " ".join("".join(el.itertext()) for el in art.iter("AbstractText"))
    labelled = [(el.get("Label") or "", "".join(el.itertext())) for el in art.iter("AbstractText")]
    results = " ".join(t for lab, t in labelled if re.match(r"RESULT|CONCLUSION|FINDING|INTERPRETATION", lab, re.I)) or abstract
    sentences = re.split(r"(?<=[.;])\s+(?=[A-Z(])", results)
    # предложения с числами (%, p, ОР, мг) и вывод — в них ответ
    numeric = [x for x in sentences if re.search(r"\d+(\.\d+)?\s*%|[pP]\s*[<=>]|\b(OR|RR|HR)\b|\d+\s*mg|95%", x)]
    conclusion = next((t for lab, t in labelled if lab.upper().startswith("CONCLUSION")), sentences[-1] if sentences else "")
    key = " ".join(dict.fromkeys(numeric[:4] + [conclusion]))
    n = re.search(r"(\d[\d,]{1,7})\s+(?:\w+\s+){0,3}(?:patients|subjects|participants|individuals|children|adults|women|men|cases)", abstract)
    types = [t.text for t in art.iter("PublicationType")]
    return {"pmid": art.findtext(".//PMID"), "title": _clean(title),
            "journal": art.findtext(".//Journal/ISOAbbreviation") or art.findtext(".//Journal/Title") or "",
            "year": art.findtext(".//JournalIssue/PubDate/Year") or (art.findtext(".//JournalIssue/PubDate/MedlineDate") or "")[:4],
            "types": types, "n": n.group(1) if n else "", "key": _clean(key)[:900]}


def _design(types):
    for t, name in (("Meta-Analysis", "мета-анализ"), ("Systematic Review", "систематический обзор"), ("Practice Guideline", "руководство"),
                    ("Guideline", "руководство"), ("Randomized Controlled Trial", "РКИ"), ("Observational Study", "наблюдательное"),
                    ("Comparative Study", "сравнительное"), ("Clinical Trial", "клиническое испытание (не РКИ)"),
                    ("Multicenter Study", "многоцентровое"), ("Review", "обзор")):
        if t in types:
            return name
    return "статья"


async def _evidence(intervention, condition, aspect, comparator, years):
    import math
    import xml.etree.ElementTree as ET
    async with aiohttp.ClientSession(trust_env=False, timeout=aiohttp.ClientTimeout(total=90)) as s:
        m_i, m_c, m_cmp = await _mesh(s, intervention), await _mesh(s, condition), await _mesh(s, comparator)
        base = _concept(intervention, m_i) + (" AND " + _concept(condition, m_c) if condition else "")
        if comparator and comparator.lower() not in intervention.lower():
            base += " AND " + _concept(comparator, m_cmp)
        # обзоры и руководства часто пишут о группе препаратов («antithyroid drugs»), а не о веществе — для этих уровней
        # добавочный поиск: болезнь + фармакологическая группа ([pa]) + аспект. Без группы болезнь + аспект тянули
        # всё подряд (при «схеме лечения» Грейвса — препараты от офтальмопатии)
        # вопрос о конкретной форме («metformin extended release») — обзоры о классе препаратов не нужны
        # (то же правило, что в _concept: часть слов — рубрика, часть — сверх неё; синоним целиком, как paracetamol →
        # acetaminophen, формой не считается)
        words_i = [w for w in re.findall(r"[\w'-]+", intervention) if w.lower() not in CONCEPT_STOP]
        extra_i = [w for w in words_i if m_i and w.lower() not in m_i.lower()]
        specific = 0 < len(extra_i) < len(words_i)
        classes = [] if specific else await _drug_class(s, m_i)
        class_base = (f"{_concept(condition, m_c)} AND (" + " OR ".join(f'"{c}"[pa]' for c in classes) + ")") if condition and classes else ""
        cond = ASPECTS.get(aspect, "").replace("{m}", m_i or intervention)
        if years > 0:
            base += f" AND {date.today().year - years}:{date.today().year}[dp]"

        async def tier_ids(filt, n, with_aspect=True):
            term = base + (f" AND {cond}" if cond and with_aspect else "") + f" AND {filt}" + HUMANS
            return await _ncbi(s, "esearch.fcgi", {"db": "pubmed", "retmode": "json", "retmax": n, "sort": "relevance", "term": term},
                               lambda b: json.loads(b)["esearchresult"].get("idlist") or [])

        found, relaxed = {}, []
        for name, filt, keep in TIERS:
            ids = await tier_ids(filt, 12)
            if class_base and cond and filt in (TIERS[0][1], TIERS[1][1]):
                term = f"{class_base} AND {cond} AND {filt}{HUMANS}"
                ids += [i for i in await _ncbi(s, "esearch.fcgi", {"db": "pubmed", "retmode": "json", "retmax": 6, "sort": "relevance", "term": term},
                                               lambda b: json.loads(b)["esearchresult"].get("idlist") or []) if i not in ids]
            if not ids and cond:
                ids = await tier_ids(filt, 6, with_aspect=False)  # по аспекту на этом уровне пусто — без него
                if ids:
                    relaxed.append(name)
            found[name] = ids
        all_ids = list(dict.fromkeys(i for ids in found.values() for i in ids))
        if not all_ids:
            return None, (m_i, m_c, m_cmp)
        root = await _ncbi(s, "efetch.fcgi", {"db": "pubmed", "retmode": "xml", "id": ",".join(all_ids)}, ET.fromstring)
        try:
            async with s.get(ICITE, params={"pmids": ",".join(all_ids), "fl": "pmid,citation_count,relative_citation_ratio"}) as r:
                icite = {str(x["pmid"]): x for x in (await r.json(content_type=None)).get("data", [])}
        except Exception:
            icite = {}
    cards = {}
    for art in root.iter("PubmedArticle"):
        c = _card(art)
        if "Retracted Publication" not in c["types"]:
            cards[c["pmid"]] = c
    out, seen_titles = [], set()
    for name, _, keep in TIERS:
        ranked = []
        for rank, pmid in enumerate(found[name]):
            c = cards.get(pmid)
            if not c:
                continue
            norm = re.sub(r"\W+", " ", c["title"].lower()).strip()
            if norm in seen_titles:
                continue  # дубли: версии одного обзора Cochrane, повторные публикации
            rcr = (icite.get(pmid) or {}).get("relative_citation_ratio") or 0
            weak = 1.5 if c["journal"].lower().rstrip(".") in WEAK_JOURNALS else 0
            title = c["title"].lower()
            on_aspect = 2.0 if aspect in ASPECT_TITLE and re.search(ASPECT_TITLE[aspect], title) else 0
            # заголовок называет сам препарат (или его группу) — статья о нём, а не о другом лечении на его фоне
            on_drug = 1.0 if any(w and w.lower() in title for w in (intervention, m_i)) else 0
            ranked.append((2 * (1 - rank / 12) + min(math.log2(1 + rcr), 2.5) + (0.3 if c["key"] else -1) - weak + on_aspect + on_drug, norm, c))
        ranked.sort(key=lambda x: -x[0])
        picked = []
        for _, norm, c in ranked:
            if norm not in seen_titles and len(picked) < keep:
                seen_titles.add(norm)
                picked.append(c)
        if picked:
            out.append((name, picked))
    return (out, relaxed, icite), (m_i, m_c, m_cmp)


HEALTH_DIR = r"D:\llm\health"
CATALOG_MAX_AGE = 30 * 86400  # список действующих КР обновляется раз в месяц


def _stems(text):
    return set(STEM.stemWords(re.findall(r"[а-яё0-9]+", (text or "").lower()))) - GENERIC


def _fetch_missing(words, age, local_best):
    """Среди всех действующих КР на cr.minzdrav.gov.ru есть совпадающая с запросом лучше локальных (local_best — число
    слов запроса в названии и диагнозах лучшей локальной) — скачать и проиндексировать."""
    import json as _json
    import time
    if HEALTH_DIR not in sys.path:
        sys.path.insert(0, HEALTH_DIR)
    import clinrec_fetch
    import clinrec_index
    path = os.path.join(HEALTH_DIR, "clinrec_catalog.json")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < CATALOG_MAX_AGE:
        items = _json.load(open(path, encoding="utf-8"))
    else:
        items = clinrec_fetch.catalog()
    want = set(words) - GENERIC
    adults = None if not age else age.lower().startswith(("adult", "взросл"))
    scored = []
    for it in items:
        names = it["Name"] + " " + " ".join(m.get("MkbName", "") for m in it.get("Mkbs") or [])
        hit = len(want & _stems(names))
        if hit and (adults is None or ("Взрос" in it["AgeCategoryStr"]) == adults):
            scored.append((hit, "Взрос" in it["AgeCategoryStr"], it["PublishDateStr"], it))
    if not scored:
        return []
    scored.sort(key=lambda x: x[:3], reverse=True)
    best = scored[0][0]
    added = []
    local = os.path.join(HEALTH_DIR, "clinrec")
    have = {f.split()[0] for f in os.listdir(local)} if os.path.isdir(local) else set()
    for hit, _, _, it in scored[:2]:  # лучшая и, если так же подходит, вторая (например, взрослая и детская)
        if hit == best and hit > local_best and it["CodeVersion"] not in have:
            head, n = clinrec_index.add(clinrec_fetch.fetch(it))
            added.append(f"КР {head['code']} «{head['title']}» ({head['age'].lower()})")
    return added


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
        Search the Russian clinical guidelines (клинические рекомендации Минздрава РФ; common conditions are local, any other current guideline is downloaded automatically when the query names its condition; separate ones for adults and children) for exact passages: doses, regimens, targets, durations, criteria, recommendation grades. Returns the matching passages with guideline code and section. Use it first for any clinical question.
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

        names = lambda: {c: _stems(t + " " + (m or "")) for c, t, m in con.execute("select code, title, mkb from guidelines")}
        added = []
        if not code:
            # в каталоге всех действующих КР есть та, что совпадает с запросом лучше локальных («ревматоидный артрит»
            # при локальной «Псориатический артрит») — скачать её до поиска; каталог — локальный файл, проверка быстрая
            local_best = max((len(set(words) & n) for n in names().values()), default=0)
            con.close()
            try:
                added = _fetch_missing(words, age, local_best)
            except Exception as e:
                added = [f"(не удалось скачать КР с cr.minzdrav.gov.ru: {e})"]
            con = _clinrec()
        try:
            heads = {r[0]: r for r in con.execute("select code, title, age, published, url from guidelines")}
            rows = []
            if not code:
                # КР, в названии или диагнозах которой больше всего слов запроса («пневмония», «подагра»): сначала фрагменты
                # из неё — иначе длинные таблицы и приложения других КР перебивают её по bm25
                score = {c: len(set(words) & n) for c, n in names().items()}
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
        if added:
            lines[1:1] = ["Скачано с cr.minzdrav.gov.ru и добавлено в базу: " + "; ".join(added), ""]
        for n, (c, section, text) in enumerate(rows, 1):
            lines.append(f"[{n}] {_guideline_line(heads[c])}\n    Раздел: {section}  → read_guideline(\"{c}\", \"{section.split(' › ')[-1][:40]}\")")
            if n == 1 and len(full) <= SECTION_CHARS:
                lines.append("    (весь подраздел)\n    " + full.replace("\n", "\n    "))
            else:
                lines.append("    " + text[:1500].replace("\n", "\n    "))
        lines.append("\nCite as «КР <code>, раздел <section>». The first result is the whole subsection: base the regimen on it. "
                     "Read other subsections with read_guideline when needed.\nNext step for any treatment question (dose, how often, how "
                     "long, which drug or regimen, \"is this too much\", \"how much is best\"): the guideline gives the allowed range, trials "
                     "show what works better within it — call search_evidence now (intervention, condition, aspect: dose / frequency / "
                     "duration / regimen / safety / efficacy, comparator if two options).")
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
        # глава целиком («3. Лечение»): её вводный текст и все подразделы — иначе модель видела только введение
        # без доз и решала, что в КР их нет
        subs = [s for s in sections if s.startswith(name + " › ")] if " › " not in name else []
        text = "\n".join(sections[name] + [f"\n### {s.split(' › ', 1)[1]}\n" + "\n".join(sections[s]) for s in subs])
        offset = max(0, int(offset or 0))
        more = (f"\n[… ещё {len(text) - offset - SECTION_CHARS} символов: read_guideline(\"{code}\", \"{name[:40]}\", offset={offset + SECTION_CHARS})]"
                if len(text) > offset + SECTION_CHARS else "")
        return f"{_guideline_line(head)}\nРаздел: {name}\n\n{text[offset:offset + SECTION_CHARS]}{more}"

    async def search_evidence(self, intervention: str, condition: str = "", aspect: str = "", comparator: str = "", years: int = 0) -> str:
        """
        Evidence for a treatment question, by level: guidelines, meta-analyses and systematic reviews, randomized trials, large comparative and observational studies. You describe the question; the tool builds the PubMed search with MeSH terms itself. For each study: design (from PubMed), number of patients, what it compared (title) and the result sentences with numbers.
        Use it for every question about how to treat: which dose, how often, how long, which regimen, how safe, drug A or drug B.
        :param intervention: The drug or treatment in English, one item: "allopurinol", "metformin extended release", "radioiodine".
        :param condition: The disease in English: "gout", "type 2 diabetes". Empty if the question is about the drug in general.
        :param aspect: What is asked, one of: "dose" (how much: starting, maximum, high vs low), "frequency" (how many times a day: once daily vs twice daily or divided doses — use this for any "once or twice a day" question, not "regimen"), "duration" (how long, when to stop), "regimen" (which treatment scheme: drug combination vs monotherapy, titration strategy — not the number of doses per day), "safety" (adverse effects), "efficacy"; empty for all.
        :param comparator: The alternative drug or treatment when two are compared ("febuxostat", "surgery"); empty otherwise.
        :param years: Only the last N years; 0 (default) for all — classic trials are often old.
        :return: Studies grouped by level of evidence with PubMed links.
        """
        aspect = (aspect or "").strip().lower()
        if aspect and aspect not in ASPECTS:
            aspect = next((k for k, pat in ASPECT_ALIASES.items() if re.search(pat, aspect)), "")
        try:
            res, mesh = await _evidence((intervention or "").strip(), (condition or "").strip(), aspect, (comparator or "").strip(), int(years or 0))
        except Exception as e:
            return f"PubMed error: {e}. Try search_medical_literature with a short query."
        terms = " | ".join(f"{a} → {b or 'нет рубрики MeSH, поиск по словам'}" for a, b in
                           zip((intervention, condition, comparator), mesh) if a)
        if not res:
            return f"Nothing found ({terms}, aspect={aspect or 'all'}). Check the English names, drop the comparator or the aspect."
        tiers, relaxed, icite = res
        lines = [f"Доказательства: {terms}; аспект: {aspect or 'все'}", ""]
        if relaxed:
            lines.append(f"(на уровнях «{', '.join(relaxed)}» по аспекту «{aspect}» ничего — показано без него)\n")
        for name, cards in tiers:
            lines.append(f"## {name}")
            for c in cards:
                info = icite.get(c["pmid"]) or {}
                cites = f", цитирований {info.get('citation_count')}" if info.get("citation_count") is not None else ""
                n = f", n={c['n']}" if c["n"] else ""
                lines.append(f"- {c['title']}\n  {_design(c['types'])}{n} | {c['journal']} {c['year']}{cites} | https://pubmed.ncbi.nlm.nih.gov/{c['pmid']}/")
                if c["key"]:
                    lines.append(f"  Результаты: {c['key']}")
            lines.append("")
        lines.append("Use the design and n exactly as given above. Base the answer on studies whose title compares what was asked; "
                     "say what each compared and the result numbers. Where levels disagree, prefer meta-analyses and RCTs, and say so.")
        return "\n".join(lines)

    async def search_medical_literature(self, query: str, study_type: str = "any", years: int = 0) -> str:
        """
        Search PubMed for clinical studies and reviews, ranked by relevance, study design and citation impact; returns titles, journal, year, study type, citations and the results/conclusions of each abstract with PubMed links.
        For "which dose / which drug is better" questions search randomized trials that compare exactly that (study_type="rct", e.g. "allopurinol dose escalation gout"), then meta-analyses (study_type="meta"). Write the query in English with medical terms.
        :param query: 3-5 English concept words as article titles would say them, no "vs", quotes or filler: drug, condition, what is compared ("allopurinol dose escalation gout", "metformin extended release", "warfarin duration venous thromboembolism"). Long queries find nothing.
        :param study_type: "any" (default), "rct" (randomized controlled trials), "meta" (meta-analyses and systematic reviews), "guideline", "review".
        :param years: Only the last N years; 0 (default) for all years — classic trials are often old.
        :return: Up to 8 ranked studies with links.
        """
        try:
            st = (study_type or "any").lower()
            result = await _pubmed(query, st, int(years or 0))
            if result.startswith("No PubMed results") and st != "any":
                # с фильтром по дизайну пусто — без фильтра (обзоры Cochrane и старые РКИ размечены не всегда)
                result = f"(nothing with study_type={st}; all designs:)\n" + await _pubmed(query, "any", int(years or 0))
            return result
        except Exception as e:
            pubmed_error = f"(PubMed unavailable: {e}; Europe PMC fallback)\n"
        years = max(1, min(int(years or 10), 50))
        parts = [f"({query})", f"PUB_YEAR:[{date.today().year - years} TO {date.today().year}]"]
        if (study_type or "any").lower() in ("meta", "review", "guideline"):
            parts.append(EVIDENCE)
        evidence = study_type
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
        lines = [pubmed_error + f'Europe PMC: "{query}" | {data.get("hitCount")} found | showing {len(results)} | evidence: {evidence} | years: last {years}', ""]
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
                 "US FDA label, not a Russian guideline: cite these doses as «инструкция FDA», never as КР; when the Russian guideline "
                 "gives a dose, the guideline dose comes first. Use the label mainly for contraindications, interactions, adverse effects, pregnancy."]
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
