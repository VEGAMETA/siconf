---
name: Web research
description: How to search the web well with search_web and fetch_url: plan specific queries with the current date, open the best pages, check dates, cross-check, and answer with dated facts and links. Read it before the first search in a conversation.
---

# Web research

Follow these steps whenever you answer from the web (news, releases, versions, prices, "find", "what's new", comparisons).

## 1. Pin down the question

- What exactly is asked: one fact, a list of events, a comparison, a recommendation?
- Turn relative time into exact dates from today's date: "this week" = Monday to today, "this month" = the 1st to today, "recently" = about the last 30 days. Today's date is real; your training ends earlier, so the answer is usually newer than anything you remember. Never use an older year in queries.
- What would count as a good answer: dated items with names and versions, not general trends.

## 2. Plan queries before searching

Write 2-4 queries in your thoughts, then run them. A good query has:
- concrete names: projects, products, companies, people, model numbers (for a phone: the exact model; for software: the project name);
- the period in words: "October 2026", "2026";
- a type of page that holds the answer: "release notes", "changelog", "progress report", "week in review", "roundup", "price", "review", "documentation", "GitHub releases";
- English for international or technical topics, Russian for Russian topics (prices in Russian shops, Russian services, local news); both when unsure.

Bad: "latest news about X". Good: "<project name> release notes October 2026", "<field> weekly roundup October 2026", "<product model> price".

## 3. Search, judge, refine

- After each search_web call, judge the results: on topic? dated inside the period? from a real source?
- If results are junk (unrelated sites, other years), do not repeat the same words: add names, a site name, quotes, the month and year, or switch language.
- Snippets are short and often undated. Open the 1-3 best pages with fetch_url (a weekly roundup, an official changelog or release page, a tracker list) and take the facts from the page itself. For news over a period and for "what's new / latest version" questions, opening at least one page is required, not optional.
- Budget: usually up to 5 searches and 3 pages. Stop earlier when the question is answered with dated facts from a primary source or two independent sources.

## 4. Check what you found

- Date of every item: is it inside the asked period? "Added to a list on Oct 21" is not "released on Oct 21". Drop or clearly label older items.
- Source quality: official sites, GitHub releases and project blogs beat aggregators; forums and Reddit are rumours until confirmed. Say "по слухам" or "не подтверждено" for single-source surprising claims.
- When sources disagree, say so and give both.
- Do not fill gaps from memory. If nothing was found for the period, say so plainly and give the nearest dated items, labelled with their dates.

## 5. Check yourself before answering

- Did I run every search and open every page I planned? If not, do it now.
- Does every item have a date inside the asked period (or a clear label that it is older) and a link?
- Is anything taken from memory or from a snippet I did not verify? Remove it or mark it "по моим данным, не проверено".
- Does the answer actually answer the question in the first line?

## 6. Answer

- First line: the direct answer (or "за эту неделю нашёл вот что / ничего крупного не нашёл").
- Then grouped facts, each with a name, version or number, date, and a link: "**Проект 2.1** (17.10) — что изменилось… ([источник](url))".
- No generic filler that would fit any week ("ситуация остаётся напряжённой", "активно обсуждается").
- End with caveats (unconfirmed items, gaps) and a short list of sources.

## Finding good sources on any topic

Do not rely on remembered site names; find where the topic lives:
- **The hub first.** Every active field has places that collect its news: weekly roundups, release trackers, curated "awesome" lists, community wikis, changelog pages. Search for them by type: "<topic> weekly roundup <month year>", "<topic> news tracker", "<topic> release tracker", "awesome <topic>", then open the best one with fetch_url.
- **Primary sources for facts.** For a specific project or product, its official site, documentation, blog and GitHub releases page (github.com/<owner>/<repo>/releases) beat news articles; for a company, its press releases.
- **Orientation for unknown topics.** When the field is new to you, a quick search for an overview (Wikipedia, a recent explainer) gives the names of the main projects; then search those names.
- **Local topics** (prices, shops, services, laws of the user's country): search in the user's language and prefer that country's shops, marketplaces and official sites.
- **Blocked pages:** some sites block automatic fetching (error, empty page, a "verify you are human" page). Do not retry: use the search snippets of that site or another source.

## Typical tasks

- **News for a period:** search weekly roundups and news trackers for the field, then official blogs of the main projects; open the roundup page.
- **Latest version of software:** the official releases page or GitHub releases; give the version, date and 1-2 key changes.
- **Prices:** two or three shops or marketplaces for the user's country, with the date checked; give a range, not a single number.
- **How to do something:** official documentation first, then a recent guide; check that the steps fit the current version.
- **A name, meme or quote you cannot recall:** search with the details the user gave, in the user's language and in English.
