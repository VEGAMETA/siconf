"""
title: Поиск в интернете с чтением страниц
description: Заменяет встроенный search_web: ищет через SearXNG с фильтром по времени и сразу читает лучшие страницы, чтобы модели хватало одного вызова (небольшие модели плохо делают цепочки «поиск → открыть страницу → уточнить»).
author: local
version: 0.1.0
"""

import asyncio
import json
import re
import urllib.parse
from datetime import date, timedelta

import aiohttp
from open_webui.retrieval.utils import get_content_from_url

SEARXNG = "http://127.0.0.1:8888/search"
RESULTS = 8            # сколько результатов показать модели
PAGE_CHARS = 4000      # символов текста с каждой прочитанной страницы
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
        Start with a short, broad query; then call again with names found in the results to narrow down.
        :param query: Search query, short and concrete (names, page type such as "release notes" or "weekly roundup"). The period filter handles dates, so the year is optional.
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
        try:
            results = await _searxng(query, period)
            note = ""
            if period and len(results) < MIN_FRESH:
                older = await _searxng(query, "")
                seen = {r.get("url") for r in results}
                results += [r for r in older if r.get("url") not in seen]
                note = f"Only {len(results) - len([r for r in older if r.get('url') not in seen])} results within the period; older results added below, check their dates."
        except Exception as e:
            return f"Search error: {e}. SearXNG at {SEARXNG} may be down."
        results = [r for r in results if r.get("url")][:RESULTS]
        if not results:
            return f'No results for "{query}". Try shorter or different words, or another language.'

        # читаем страницы по порядку, пропуская видео и пустые; до трёх штук
        to_read = [i for i, r in enumerate(results) if not any(d in r["url"] for d in SKIP_READ)]
        texts = await asyncio.gather(*[_read(__request__, results[i]["url"]) for i in to_read[:5]])
        pages = [(i, t) for i, t in zip(to_read[:5], texts) if len(t) >= MIN_PAGE_CHARS][:3]

        today = date.today()
        head = f'Search: "{query}" | today: {today.isoformat()}'
        if period:
            head += f" | period: {period} ({(today - timedelta(days=PERIOD_DAYS[period])).isoformat()} to {today.isoformat()})"
        lines = [head]
        if note:
            lines.append(note)
        lines.append("")
        page_text = dict(pages)
        for n, r in enumerate(results, 1):
            published = (r.get("publishedDate") or "")[:10]
            if not published and (n - 1) in page_text:
                found = DATE_RE.search(page_text[n - 1][:3000])
                published = f"{found.group(0)} (first date on the page)" if found else ""
            lines.append(f"[{n}] {r.get('title', '').strip()} — {r['url']}" + (f" | date: {published}" if published else " | date: unknown"))
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
