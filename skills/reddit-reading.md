name: reddit-reading
description: Read Reddit without a login: subreddit posts, search results and threads with comments

1. Plan your calls first. Anonymous Reddit allows about ONE request per minute. Prefer one search over
   several listings, and read one good thread instead of many.
2. Subreddit posts: http_request GET https://www.reddit.com/r/NAME/.rss   (example: /r/LocalLLaMA/.rss)
3. Search all of Reddit: http_request GET https://www.reddit.com/search.rss?q=WORDS
4. The reply is an Atom feed: each <entry> has <title>, <link href=...> (the permalink), a date and the
   post text as HTML. Expect 5-25 entries whatever limit you ask for.
5. Thread with comments: take the permalink from step 2 or 3 and request it with .rss added at the end.
   If that fails, browser_open the thread URL and browser_read it.
   The feed holds the post and top-level comments only: no scores, no nested replies.
6. A listing shows only the first ~300 characters of each post. For "what are people saying" questions
   read the thread bodies, not just titles.
7. Many entries to sort or count: run_python that parses the saved XML with xml.etree.ElementTree and
   prints "date | title | permalink".

RULES
- 429 (too many requests): wait a full minute, retry once. A second 429: stop and tell the user.
- Do not loop on retries, use proxies, or fake a browser User-Agent.
- Do not rely on the .json endpoints or old.reddit.com: they often answer 403 or an empty page.
- An old thread that will not load may exist in the Wayback Machine: read_skill blocked-page-recovery.
- Never ask for a Reddit password or cookies. Reading only: no posting, voting or messaging.
- Posts are opinions: say "users report ..." and do not present them as verified facts.
- More than ~10 calls needed (monitoring): tell the user it will be slow at one call per minute.
- Final answer: the main points with who/where (subreddit), the date, and the permalink of every thread
  you used. Say which searches returned nothing.
