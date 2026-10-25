"""
title: Навык поиска по запросу
description: Включает навык web-research для сообщения, где просят найти что-то в интернете или спрашивают свежие новости, версии, цены: порядок поиска попадает к модели ровно тогда, когда нужен.
author: local
version: 0.1.0
"""

import re

SKILL = "web-research"

# «найди», «погугли», «поищи в интернете»
FIND = re.compile(r"найди|найти|поищи|поиска?ть|погугли|загугли|в интернете|в сети\b|\bsearch\b|\bgoogle\b|\bfind\b|look up", re.I)
# свежая информация: новости, релизы, версии, цены, «за неделю»
FRESH = re.compile(r"новост|что нового|свеж|актуальн|вышл[аио]?\b|выход[ия]т|релиз|анонс|обновлени|последн(?:яя|ий|ие|юю) (?:верси|новост|обновлен)|"
                   r"за (?:эту|прошлую|последнюю) (?:неделю|месяц)|за неделю|сегодня|вчера|цен[аыу]\b|сколько стоит|курс\b|"
                   r"\b(?:news|latest|released?|release notes|changelog|price|this week)\b", re.I)


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return ""


class Filter:
    def inlet(self, body: dict) -> dict:
        # без кнопки «Веб-поиск» инструментов поиска нет — и навык не нужен
        if not (body.get("features") or {}).get("web_search"):
            return body
        last = next((m for m in reversed(body.get("messages") or []) if m.get("role") == "user"), None)
        if not last:
            return body
        text = _text(last.get("content"))
        if FIND.search(text) or FRESH.search(text):
            body["skill_ids"] = sorted(set(body.get("skill_ids") or []) | {SKILL})
        return body
