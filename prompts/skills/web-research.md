---
name: Web research
description: Rules for answering from the web with search_web (it also reads the top pages): start broad then narrow, use the period filter, stay on budget, check dates, answer with numbered citations. Read it before the first search in a conversation.
---

# Web research

## Rules

1. **Search before answering.** For news, releases, versions, prices or anything that may have changed, never answer from memory: call search_web first. Your memory is older than today's date, and the web has this year's pages.
2. **Dates.** If the message has a [Context: ...] note with a date range and a period, use exactly that range and pass that period to search_web. Otherwise turn "this week" into this Monday to today, "recently" into the last 30 days.
3. **Two passes: cover the topic, then narrow.** Pass 1: find out what the user's words mean to people in that field (the specialist sense, not the everyday one) and split the request into its main parts. Pass one query per part in a single search_web call, separated by " ; ", and include at least one query for the field's own hubs: "<field> weekly roundup", "<field> news tracker", "<field> community news". Pass 2: search the concrete names that appear in the pass-1 texts (projects, games, tools, versions), again several at once. Never put names from your own memory or guesses into pass-2 queries: only names from the results or from the user's message. Answer after pass 2.
4. **Read the page texts.** search_web returns the text of the top pages after the list of results: take facts from those texts, not from the one-line snippets. For one more page, call fetch_url with its link.
5. **Budget.** Usually 2-3 search_web calls (pass 1, pass 2, maybe one targeted check). Answer after at most 5 calls even if something is missing, and say what is missing.
6. **Sources.** Official sites, release pages, project blogs and established news sites beat SEO pages, video titles and forum rumours. Mark single-source surprising claims as unconfirmed.
7. **Check dates.** Use each item's own date (release or publication), not "added to a list", "last checked" or "N days ago" in a snippet. Items a day or two before the period are fine with their date shown; clearly older items get their date and go to the end, or are dropped. Never change a date to fit the period.
8. **Order by importance, in this order** (the user's criteria for any news overview):
   1. **The frontier:** the newest and hardest things in the field (the latest platforms, generations or versions; "first time ever" results) and anything about the biggest names everyone waits for.
   2. **Big progress on well-known titles or products:** a 1.0, a first playable or working version, a major new version of something famous.
   3. **The previous generation:** solid progress on older but still popular platforms or products.
   4. **Niche projects and technical details:** small builds, minor versions, internals; last, briefly, one line "Ещё: …".
   Inside each group, things that several sites write about go first. Cover every part of the topic you searched, not only one.
9. **Stay on the topic as the user means it.** Leave out findings that only look related. Adjacent things (a compatibility layer instead of a port, a general trend article) go to the very end in one or two lines with a few words on why they may matter.

## Worked example: emulation and porting news

How the order above looks for this field (the user's own view):
1. Switch 2 and PS5: emulation, hacks, first booting or playable games; ports of GTA 6, including news about its official PC version.
2. Native ports and recompilations of significant titles (for example Uncharted, inFAMOUS, Crackdown): first playable builds, 1.0 releases, big updates.
3. PS4, Xbox 360 and PS3 emulation and ports.
4. Niche emulators, small builds and technical changes; running PC games on a console through Wine-like layers is adjacent, not porting.
"Porting" here means unofficial native ports: decompilations, static recompilations and source ports, not official re-releases.

## Answer format

- First line: the direct answer, or plainly "за этот период нашёл немного" if so.
- Then the facts, grouped, each with a name, version or number, its date, and a numbered citation: "**Проект 2.1** (21.10) — что изменилось [3]".
- No filler that would fit any week ("ситуация остаётся напряжённой", "ожидается ряд релизов").
- End with "Источники:" and the numbered links you cited: "[3] https://…". Follow-up answers in the same conversation also cite their sources.
