name: web-research
description: Answer current or factual questions from the web: use the official source, cite it, never guess from memory

Use for "latest version", "price", "who won", "what is the current ...", news, opening hours, anything that can change.
1. Never answer a current fact from memory. Search first (web_search); prefer the official site (the project's own website,
   the company, the government, the organizer) over blogs and forums.
2. If search fails or gives nothing useful, fetch_url the official page you know holds the answer (for example a project's
   download page, a company's pricing page, an official results page). Wikipedia summaries are only a fallback for
   background, not for "latest" facts.
3. Read the page and quote the exact value from it. If two sources disagree, say so and prefer the official one.
4. Answer: the finding first, then the source URL, then the date or version it refers to ("as of the page you read").
5. If you could not verify it, say so plainly and say what you tried. Do not fill the gap with a guess.
6. Numbers from pages (prices, totals, differences) go through calculate; dates through date_math.
