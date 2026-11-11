name: blocked-page-recovery
description: Use when a page will not load (403/429, "Just a moment", paywall, bot wall): find a copy

Do not retry the same URL again and again. Work down this ladder and stop at the first real hit.
1. Wayback Machine: http_request GET https://archive.org/wayback/available?url=URL
   Take archived_snapshots.closest.url and its timestamp from the JSON, then fetch_url that snapshot URL.
   List more snapshots: https://web.archive.org/cdx/search/cdx?url=URL&output=json&limit=10
   (a 503 there means busy: go back to the first API, do not hammer it).
2. archive.today: fetch_url https://archive.ph/newest/URL . If it fails, try the same path on archive.md,
   then archive.li, then archive.is. Good for paywalled news that Wayback lacks. It rate-limits hard.
3. API pivot (after 2-3 blocks on one site): try the same host's /api/..., /graphql or a .json form of the
   URL with http_request; look for a feed (/feed, /rss, <link rel="alternate">) or /sitemap.xml.
4. Last resort: browser_open(url), then browser_read. Close it with browser_close.

CHECK EVERY RESULT (a 200 status can lie)
- The text must contain the page's real title words or expected content. Size alone proves nothing.
- Reject pages titled "Just a moment", "Attention Required", "Redirecting" or "Google Search",
  rate-limit notices, and tiny stubs that only redirect back to the original site.
- Never use Google Cache (dead) or AMP caches (they return redirect stubs).
- Never use generic "web proxy" sites, and never send cookies or logins through any third party.

CITING
- A Wayback or archive.today copy is a snapshot. Always write "as archived YYYY-MM-DD".
  Never present it as the live page.
- If the user needs current data (prices, stock, breaking news), say the snapshot may be out of date.
- A page read live in the browser is cited normally.
- Final answer: the content or summary, which route worked, the URL you read, and the snapshot date.
  If every route failed, list what you tried.
