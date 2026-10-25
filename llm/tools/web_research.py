"""
title: Поиск в интернете с чтением страниц
description: Заменяет встроенный search_web: ищет через SearXNG с фильтром по времени и сразу читает лучшие страницы, чтобы модели хватало одного вызова (небольшие модели плохо делают цепочки «поиск → открыть страницу → уточнить»).
author: local
version: 0.2.0
"""

import asyncio
import json
import re
import urllib.parse
from datetime import date, timedelta

import aiohttp
from open_webui.retrieval.utils import get_content_from_url

SEARXNG = "http://127.0.0.1:8888/search"
MAX_QUERIES = 4        # запросов в одном вызове (через « ; »)
PER_QUERY = 6          # результатов с каждого запроса
MAX_RESULTS = 16       # всего результатов в ответе модели
MAX_FETCH = 8          # страниц пробуем открыть
MAX_PAGES = 4          # страниц отдаём текстом
PAGE_CHARS = 3500      # символов текста с каждой страницы
MIN_PAGE_CHARS = 300   # меньше — пустая страница или заглушка «вы робот?»
FETCH_TIMEOUT = 25     # секунд на одну страницу
MIN_FRESH = 3          # если за период нашлось меньше — повтор без фильтра по времени
# видео и соцсети: текста страницы там нет
SKIP_READ = ("youtube.com", "youtu.be", "tiktok.com", "instagram.com", "facebook.com", "x.com", "twitter.com", "vk.com/video")
PERIOD_DAYS = {"day": 1, "week": 7, "month": 31, "year": 366}
DATE_RE = re.compile(
    r"\b20\d\d-[01]\d-[0-3]\d\b|\b[0-3]?\d\.[01]\d\.20\d\d\b|"
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? [0-3]?\d,? 20\d\d\b|"
    r"\b[0-3]?\d (?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря) 20\d\d\b"
)


async def _searxng(query, period):
    params = {"q": query, "format": "json"}
    if period in PERIOD_DAYS:
        params["time_range"] = period
    url = SEARXNG + "?" + urllib.parse.urlencode(params)
    async with aiohttp.ClientSession(trust_env=False) as s:
        async with s.get(url, timeout=aiohttp.ClientTimeout(total=40)) as r:
            data = await r.json(content_type=None)
    return data.get("results") or []


async def _read(request, url):
    try:
        text, _ = await asyncio.wait_for(get_content_from_url(request, url), FETCH_TIMEOUT)
    except Exception:
        return ""
    return re.sub(r"\s+", " ", text or "").strip()


class Tools:
    async def search_web(self, query: str, period: str = "", __request__=None, __metadata__=None, __messages__=None) -> str:
        """
        Search the web and read the best pages in one call. Use it for news, releases, versions, prices and any fact that may have changed.
        For a broad topic, pass several short queries at once, separated by " ; ", one per part of the topic (for example new program releases ; game ports ; tools), so the search covers it from all sides.
        :param query: One short, concrete query, or 2-4 queries separated by " ; ". Names and page types ("release notes", "weekly roundup") help; the period filter handles dates, so the year is optional.
        :param period: Only pages from this recent period: "day", "week", "month" or "year". Empty for any time. Use "week" for "this week", "month" for "recently" or "this month".
        :return: Numbered results with title, link, date and snippet, followed by the text of the top pages.
        """
        features = (__metadata__ or {}).get("features") or {}
        if __metadata__ is not None and not features.get("web_search"):
            return "Web search is off: the user has not enabled the «Веб-поиск» button. Tell the user and do not claim to have searched."
        period = (period or "").strip().lower()
        if period not in PERIOD_DAYS:
            period = ""
        if not period:
            # модель часто не передаёт period: берём его из подсказки фильтра research_skill_auto в последнем сообщении
            last = next((m for m in reversed(__messages__ or []) if m.get("role") == "user"), None)
            content = (last or {}).get("content")
            if isinstance(content, list):
                content = " ".join(p.get("text", "") for p in content if isinstance(p, dict))
            hint = re.search(r'\[Context:[^\]]*period="(\w+)"', content or "")
            if hint and hint.group(1) in PERIOD_DAYS:
                period = hint.group(1)
        queries = [q.strip() for q in re.split(r"\s*;\s*|\n", query or "") if q.strip()][:MAX_QUERIES] or [query]

        async def one(q):
            results = await _searxng(q, period)
            if period and len(results) < MIN_FRESH:
                seen = {r.get("url") for r in results}
                results += [dict(r, older=True) for r in await _searxng(q, "") if r.get("url") not in seen]
            return [r for r in results if r.get("url")][:PER_QUERY]

        try:
            per_query = await asyncio.gather(*[one(q) for q in queries])
        except Exception as e:
            return f"Search error: {e}. SearXNG at {SEARXNG} may be down."

        # по очереди из каждого запроса, без повторов: каждая часть темы попадает в начало списка
        results, seen = [], set()
        for row in range(PER_QUERY):
            for res in per_query:
                if row < len(res) and res[row]["url"] not in seen:
                    seen.add(res[row]["url"])
                    results.append(res[row])
        results = results[:MAX_RESULTS]
        if not results:
            return f'No results for "{query}". Try shorter or different words, or another language.'

        # читаем страницы в том же порядке, пропуская видео и пустые
        to_read = [i for i, r in enumerate(results) if not any(d in r["url"] for d in SKIP_READ)][:MAX_FETCH]
        texts = await asyncio.gather(*[_read(__request__, results[i]["url"]) for i in to_read])
        pages = [(i, t) for i, t in zip(to_read, texts) if len(t) >= MIN_PAGE_CHARS][:MAX_PAGES]

        today = date.today()
        head = "Search: " + " ; ".join(f'"{q}"' for q in queries) + f" | today: {today.isoformat()}"
        if period:
            head += f" | period: {period} ({(today - timedelta(days=PERIOD_DAYS[period])).isoformat()} to {today.isoformat()})"
        lines = [head, ""]
        page_text = dict(pages)
        for n, r in enumerate(results, 1):
            published = (r.get("publishedDate") or "")[:10]
            if not published and (n - 1) in page_text:
                found = DATE_RE.search(page_text[n - 1][:3000])
                published = f"{found.group(0)} (first date on the page)" if found else ""
            tail = f" | date: {published}" if published else " | date: unknown"
            if r.get("older"):
                tail += " | outside the period filter"
            lines.append(f"[{n}] {r.get('title', '').strip()} — {r['url']}{tail}")
            snippet = re.sub(r"\s+", " ", r.get("content") or "").strip()
            if snippet:
                lines.append(f"    {snippet[:300]}")
        if pages:
            lines.append("\nPage texts (read these; cite them by their number):")
            for i, text in pages:
                cut = text[:PAGE_CHARS] + (" […]" if len(text) > PAGE_CHARS else "")
                lines.append(f"\n[{i + 1}] {results[i]['url']}\n{cut}")
        else:
            lines.append("\nNo page could be read (blocked or empty). Use the snippets and say that details are unverified.")
        return "\n".join(lines)
