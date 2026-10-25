---
name: Web research
description: Rules for answering from the web with search_web (it also reads the top pages): start broad then narrow, use the period filter, stay on budget, check dates, answer with numbered citations. Read it before the first search in a conversation.
---

# Web research

## Rules

1. **Search before answering.** For news, releases, versions, prices or anything that may have changed, never answer from memory: call search_web first. Your memory is older than today's date, and the web has this year's pages.
2. **Dates.** If the message has a [Context: ...] note with a date range and a period, use exactly that range and pass that period to search_web. Otherwise turn "this week" into this Monday to today, "recently" into the last 30 days.
3. **Cover the whole topic, then narrow.** For a broad request ("news of a field"), first split the field into its main parts (for example: new program releases, games or products, tools and utilities, hardware) and pass one short query per part in a single search_web call, separated by " ; " (2-5 words each, plus a page type when useful: "weekly roundup", "release notes"). Read what came back, then search again with the concrete names you found.
4. **Read the page texts.** search_web returns the text of the top pages after the list of results: take facts from those texts, not from the one-line snippets. For one more page, call fetch_url with its link.
5. **Budget.** Usually 2-4 search_web calls. Stop when the question is answered with dated facts from good sources; answer after at most 6 calls even if something is missing, and say what is missing.
6. **Sources.** Official sites, release pages, project blogs and established news sites beat SEO pages, video titles and forum rumours. Mark single-source surprising claims as unconfirmed.
7. **Check dates.** Keep only items whose own date is inside the asked period; "added to a list", "last checked" or "N days ago" in a snippet is not a release date. Label or drop older items. Never move an item into the period to fill the answer.

8. **Order by importance.** Put first what matters to many people: widely known titles, products and franchises, big releases (1.0, a new major version, a first playable version), and things several sites write about. Cover every part of the topic you searched, not only one. Small builds and minor updates go last, in one line "Ещё: …". If the user's memory says what they care about, put that first.

## Answer format

- First line: the direct answer, or plainly "за этот период нашёл немного" if so.
- Then the facts, grouped, each with a name, version or number, its date, and a numbered citation: "**Проект 2.1** (21.10) — что изменилось [3]".
- No filler that would fit any week ("ситуация остаётся напряжённой", "ожидается ряд релизов").
- End with "Источники:" and the numbered links you cited: "[3] https://…".
