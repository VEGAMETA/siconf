"""
title: Навык поиска по запросу
description: Включает навык web-research для сообщения, где просят найти что-то в интернете или спрашивают свежие новости, версии, цены, и подставляет точный диапазон дат для «эта неделя», «за месяц», «недавно»: модели не нужно считать даты самой.
author: local
version: 0.2.0
"""

import re
from datetime import date, timedelta

SKILL = "web-research"

# «найди», «погугли», «поищи в интернете»
FIND = re.compile(r"найди|найти|поищи|поиска?ть|погугли|загугли|в интернете|в сети\b|\bsearch\b|\bgoogle\b|\bfind\b|look up", re.I)
# свежая информация: новости, релизы, версии, цены, «за неделю»
FRESH = re.compile(r"новост|что нового|свеж|актуальн|вышл[аио]?\b|выход[ия]т|релиз|анонс|обновлени|последн(?:яя|ий|ие|юю) (?:верси|новост|обновлен)|"
                   r"за (?:эту|прошлую|последнюю) (?:неделю|месяц)|за неделю|сегодня|вчера|цен[аыу]\b|сколько стоит|курс\b|"
                   r"\b(?:news|latest|released?|release notes|changelog|price|this week)\b", re.I)

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _window(text, today):
    """Относительное время в сообщении -> (описание, начало, конец, period для search_web)."""
    # у страниц магазинов нет даты публикации: фильтр по времени отсёк бы почти все цены
    if re.search(r"цен[аыу]\b|сколько стоит|курс\b|\bprice", text, re.I):
        return None
    if re.search(r"сегодня|\btoday\b", text, re.I):
        return "today", today, today, "day"
    if re.search(r"вчера|\byesterday\b", text, re.I):
        return "yesterday", today - timedelta(days=1), today - timedelta(days=1), "day"
    if re.search(r"прошл\w* недел|\blast week\b", text, re.I):
        monday = today - timedelta(days=today.weekday() + 7)
        return "last week", monday, monday + timedelta(days=6), "month"
    if re.search(r"эт\w* недел|на неделе|\bthis week\b", text, re.I):
        return "this week", today - timedelta(days=today.weekday()), today, "week"
    if re.search(r"(?:за|последн\w*) недел|\bpast week\b", text, re.I):
        return "the last 7 days", today - timedelta(days=7), today, "week"
    if re.search(r"эт\w* месяц|\bthis month\b", text, re.I):
        return "this month", today.replace(day=1), today, "month"
    if re.search(r"(?:за|последн\w*) месяц|недавн|свеж|последн\w* новост|\brecent", text, re.I):
        return "the last 30 days", today - timedelta(days=30), today, "month"
    if re.search(r"эт\w* год|\bthis year\b", text, re.I):
        return "this year", today.replace(month=1, day=1), today, "year"
    return None


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _append(message, note):
    content = message.get("content")
    if isinstance(content, str):
        message["content"] = content + note
    elif isinstance(content, list):
        content.append({"type": "text", "text": note})


class Filter:
    def inlet(self, body: dict) -> dict:
        # без кнопки «Веб-поиск» инструментов поиска нет — и навык не нужен
        if not (body.get("features") or {}).get("web_search"):
            return body
        last = next((m for m in reversed(body.get("messages") or []) if m.get("role") == "user"), None)
        if not last:
            return body
        text = _text(last.get("content"))
        if not (FIND.search(text) or FRESH.search(text)):
            return body
        body["skill_ids"] = sorted(set(body.get("skill_ids") or []) | {SKILL})
        today = date.today()
        window = _window(text, today)
        if window:
            name, start, end, period = window
            _append(last, f"\n\n[Context: today is {today.isoformat()} ({WEEKDAYS[today.weekday()]}). "
                          f'"{name}" means {start.isoformat()} to {end.isoformat()}. Call search_web with period="{period}".]')
        return body
