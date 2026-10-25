"""
title: Навыки по задаче
description: Включает навыки document-analysis (приложен документ или спрашивают о нём), data-analysis (таблицы, расчёты, графики) и technical-translation (просьба перевести) ровно в тех сообщениях, где они нужны.
author: local
version: 0.1.0
"""

import re

# приложенный документ или вопрос про документ
DOCUMENT = re.compile(r"документ|договор|\bpdf\b|\bdocx?\b|файл[еау]?\b|спецификац|техзадани|\bтз\b|регламент|инструкци[яию] (?:в|из)|"
                      r"в (?:этом |приложенном )?(?:тексте|файле|документе)|приложенн|прочитай|резюмир|выжимк|конспект|"
                      r"\b(?:this|the attached) (?:document|file|pdf)\b|summari[sz]e", re.I)
# таблицы, расчёты, графики
DATA = re.compile(r"\bcsv\b|\bxlsx?\b|excel|таблиц|график|диаграмм|построй|посчитай|подсчитай|статистик|средн(?:ее|ий|юю)|медиан|"
                  r"процент|тренд|динамик|корреляц|\b(?:plot|chart|dataframe|pandas)\b", re.I)
# перевод
TRANSLATE = re.compile(r"переведи|перевод|переводи|\btranslate\b|на английский|на русский|по-английски|по-русски|in english|into russian", re.I)


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _has_document(body, message):
    """Приложен файл, который не картинка (картинки идут через image_url и навык картинок)."""
    files = list(body.get("files") or []) + list(message.get("files") or [])
    for f in files:
        if not isinstance(f, dict):
            continue
        kind = (f.get("type") or "").lower()
        name = ((f.get("file") or {}).get("filename") or f.get("name") or "").lower()
        if kind == "image" or re.search(r"\.(png|jpe?g|webp|gif|bmp)$", name):
            continue
        return True
    return False


class Filter:
    def inlet(self, body: dict) -> dict:
        last = next((m for m in reversed(body.get("messages") or []) if m.get("role") == "user"), None)
        if not last:
            return body
        text = _text(last.get("content"))
        skills = set()
        if _has_document(body, last) or DOCUMENT.search(text):
            skills.add("document-analysis")
        if DATA.search(text):
            skills.add("data-analysis")
        if TRANSLATE.search(text):
            skills.add("technical-translation")
        if skills:
            body["skill_ids"] = sorted(set(body.get("skill_ids") or []) | skills)
        return body
