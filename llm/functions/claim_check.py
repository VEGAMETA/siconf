"""
title: Проверка по источникам
description: После медицинского ответа сверяет утверждения с цифрами или ссылками (дозы, проценты, n, «по данным Cochrane») с найденными в этом же ответе источниками — карточками исследований, фрагментами клинрекомендаций, инструкциями. Каждое утверждение проверяется отдельно и только по своему источнику (модель не видит остального ответа — так она не повторяет свою же ошибку). Расхождения дописываются под ответом, сам ответ не меняется.
author: local
version: 0.1.0
"""

import json
import re

import aiohttp
from pydantic import BaseModel, Field

# что считается источником: выдача инструментов medical_research
SOURCE_MARKERS = ("Доказательства:", "Клинические рекомендации Минздрава РФ", "PubMed:", "FDA drug label", "Europe PMC:",
                  "\nРаздел: ", "\nРазделы:")  # последние два — read_guideline: подраздел КР, который модель дочитала
CHECK_RE = re.compile(r"\n*\*\*Проверка по источникам[^\n]*\*\*(?:\n- [^\n]*)*\s*$")
STATS_RE = re.compile(r"(\n*\*контекст [^*\n]*\*\s*)$")
# признаки ссылки на источник: такие утверждения проверяются и без цифр («побочек меньше (Cochrane)»)
CITES = re.compile(r"Cochrane|PMID|\bКР\b|\d{2,4}_\d|РКИ|\bRCT\b|мета-анализ|meta-analys|систематическ|исследовани|\b(?:19|20)\d\d\b", re.I)
NAME_STOP = {"Meta", "Analysis", "Review", "Systematic", "Trial", "Study", "Clinical", "Journal", "Int", "Med", "The"}

PROMPT = """You check claims from a medical answer against their sources. For each claim use ONLY its source text.
Verdicts:
- SUPPORTED: the source states the same (same numbers, same direction, same group).
- CONTRADICTED: the source states something different: another number, the opposite direction (more vs less, higher vs lower, better vs worse), the result attributed to the wrong group or drug, a different study design.
- NOT_IN_SOURCE: the source does not address the claim.
Be strict about direction and about which group a number belongs to. Rounding and translation into Russian are fine.
Return JSON only: {"results": [{"id": 1, "verdict": "SUPPORTED|CONTRADICTED|NOT_IN_SOURCE", "note": "for CONTRADICTED: one short sentence in Russian, what the source actually says, with its numbers"}]}

"""


def _text(item):
    out = item.get("output")
    if isinstance(out, list):
        return " ".join(p.get("text", "") for p in out if isinstance(p, dict))
    return out if isinstance(out, str) else ""


def _numbers(text):
    """Числа как в источнике: «14,8 %» и «14.8%» — одно и то же; годы и мелкие целые не в счёт."""
    nums = set()
    for n in re.findall(r"\d+(?:[.,]\d+)?", text):
        n = n.replace(",", ".")
        if re.fullmatch(r"(19|20)\d\d", n) or (n.isdigit() and int(n) < 3):
            continue
        nums.add(n.rstrip("0").rstrip(".") if "." in n else n)
    return nums


def _chunks(sources):
    """Источники → куски: карточка исследования, фрагмент КР, раздел инструкции."""
    chunks = []
    for src in sources:
        if src.lstrip().startswith("КР ") and "\nРаздел" in src[:600]:
            parts = [src]  # подраздел КР от read_guideline — целиком: с шапкой (код КР), нужное место вырежет _window
        elif "Доказательства:" in src[:200]:
            parts = re.split(r"\n(?=- |## )", src)  # карточки исследований
        elif src.startswith("FDA drug label"):
            parts = re.split(r"\n(?=## )", src)
        else:
            parts = re.split(r"\n(?=\[\d+\] )", src)  # результаты поиска КР и PubMed: по номерам, шапка с кодом остаётся
        chunks += [p.strip() for p in parts if len(p.strip()) > 80]
    return chunks


def _window(claim, chunk, limit=2500):
    """Нужное место длинного источника: шапка и предложения с числами и словами утверждения, с соседними. Обрезка
    до первых 3000 символов теряла дозы в середине подраздела КР — и приписанные КР дозы FDA проходили проверку."""
    if len(chunk) <= limit:
        return chunk
    head, rest = chunk[:300], chunk[300:]
    sents = re.split(r"(?<=[.;:])\s+|\n", rest)
    nums = _numbers(claim)
    words = {w for w in re.findall(r"[а-яёa-z]{5,}", claim.lower())}
    scored = [(len(nums & _numbers(x)) * 3 + len(words & set(re.findall(r"[а-яёa-z]{5,}", x.lower()))), i) for i, x in enumerate(sents)]
    keep = set()
    for sc, i in sorted(scored, reverse=True)[:6]:
        if sc > 0:
            keep |= {i - 1, i, i + 1}
    text = head + " … " + " … ".join(sents[i] for i in sorted(keep) if 0 <= i < len(sents))
    return text[:limit]


def _claims(answer, limit):
    """Утверждения из ответа (до «Что уточнить» и «Источники»): строки таблиц и предложения с цифрами или ссылкой."""
    body = re.split(r"\n\**\s*«?(?:Источники|Sources)", answer)[0]
    body = re.split(r"\n#+\s*Что уточнить|\n\**«?Что уточнить", body)[0]
    pieces = []
    for line in body.split("\n"):
        if line.strip().startswith("|"):
            cells = [c.replace("**", "").strip() for c in line.strip().strip("|").split("|")]
            row = " | ".join(cells)
            if set(row) <= set("-: |") or len(row) < 30:
                continue
            if _numbers(row) or CITES.search(row):
                pieces.append(row)
            continue
        line = re.sub(r"^[\s>*#-]+", "", line).replace("**", "").strip()
        for sent in re.split(r"(?<=[.;])\s+(?=[А-ЯA-Z])", line):
            if 30 <= len(sent) <= 400 and (_numbers(sent) or CITES.search(sent)):
                pieces.append(sent)
    seen, out = set(), []
    for p in pieces:
        key = re.sub(r"\W+", "", p.lower())
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out[:limit]


def _match(claim, chunks):
    """Кусок источника для утверждения. Сначала названия: PMID, код КР, журнал и год («Cochrane 2010»), потом общие
    числа — по одним числам строка о Cochrane сопоставлялась с фрагментом КР, где случайно были те же 7,5 и 10."""
    for pm in re.findall(r"\b\d{7,8}\b", claim):
        hit = next((c for c in chunks if pm in c), None)
        if hit:
            return hit
    kr = re.findall(r"\b\d{2,4}_\d\b", claim)
    names = {w for w in re.findall(r"\b[A-Z][A-Za-z]{3,}\b", claim) if w not in NAME_STOP}
    years = set(re.findall(r"\b(?:19|20)\d\d\b", claim))
    nums = _numbers(re.sub(r"\b\d{7,8}\b|\b\d{2,4}_\d\b", "", claim))
    best, score = None, 0
    for c in chunks:
        sc = (len(nums & _numbers(c)) + 3 * sum(n in c for n in names) + 2 * sum(y in c for y in years)
              + (3 if any(k in c for k in kr) else 0))
        if sc > score:
            best, score = c, sc
    return best if score >= 2 else None


class Filter:
    class Valves(BaseModel):
        priority: int = Field(default=-1, description="Раньше строки расхода контекста (у неё 0), чтобы проверка шла над ней")
        llm_url: str = Field(default="http://127.0.0.1:8081/v1/chat/completions")
        model: str = Field(default="gemma-4-26b-a4b")
        max_claims: int = Field(default=12)

    def __init__(self):
        self.valves = self.Valves()

    def inlet(self, body: dict) -> dict:
        # прошлые блоки проверки — для человека; из истории для модели вырезаются (строку расхода вырезает её фильтр)
        for m in body.get("messages") or []:
            if m.get("role") == "assistant" and isinstance(m.get("content"), str):
                stats = STATS_RE.search(m["content"])
                m["content"] = CHECK_RE.sub("", STATS_RE.sub("", m["content"])) + (stats.group(1) if stats else "")
        return body

    async def outlet(self, body: dict) -> dict:
        last = next((m for m in reversed(body.get("messages") or []) if m.get("role") == "assistant"), None)
        if not last or not isinstance(last.get("content"), str):
            return body
        sources = [t for t in (_text(o) for o in last.get("output") or [] if o.get("type") == "function_call_output")
                   if any(mk in t for mk in SOURCE_MARKERS)]
        if not sources:
            return body
        answer = STATS_RE.sub("", last["content"])
        chunks = _chunks(sources)
        pairs = [(c, _match(c, chunks)) for c in _claims(answer, self.valves.max_claims)]
        pairs = [(c, s) for c, s in pairs if s]
        if not pairs:
            return body
        task = PROMPT + "\n\n".join(f"Claim {i}: {c}\nSource {i}: {_window(c, s)}" for i, (c, s) in enumerate(pairs, 1))
        try:
            async with aiohttp.ClientSession(trust_env=False, timeout=aiohttp.ClientTimeout(total=180)) as s:
                async with s.post(self.valves.llm_url, json={
                        "model": self.valves.model, "temperature": 0, "max_tokens": 1500,
                        "messages": [{"role": "user", "content": task}],
                        "response_format": {"type": "json_object"},
                        "chat_template_kwargs": {"enable_thinking": False}}) as r:
                    data = await r.json(content_type=None)
            results = json.loads(data["choices"][0]["message"]["content"]).get("results", [])
        except Exception:
            return body  # проверка — дополнение: если не вышло, ответ остаётся как есть
        bad = [(pairs[int(r["id"]) - 1][0], r.get("note", "")) for r in results
               if r.get("verdict") == "CONTRADICTED" and 0 < int(r.get("id", 0)) <= len(pairs)]
        if bad:
            block = (f"\n\n**Проверка по источникам: {len(pairs)} утверждений сверено, расхождения ({len(bad)}):**\n"
                     + "\n".join(f"- «{c[:220]}» — {n}" for c, n in bad))
        else:
            block = f"\n\n**Проверка по источникам: {len(pairs)} утверждений сверено, расхождений не найдено**"
        stats = STATS_RE.search(last["content"])
        last["content"] = answer.rstrip() + block + (stats.group(1) if stats else "")
        # в 0.12 интерфейс рисует ответ из output — туда тоже
        texts = [p for item in (last.get("output") or []) if item.get("type") == "message"
                 for p in (item.get("content") or []) if p.get("type") == "output_text"]
        if texts:
            t = texts[-1].get("text") or ""
            st = STATS_RE.search(t)
            texts[-1]["text"] = STATS_RE.sub("", t).rstrip() + block + (st.group(1) if st else "")
        return body
