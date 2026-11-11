name: rss-feeds
description: Read the newest entries of an RSS/Atom/JSON feed, or find the feed behind a site URL

1. Have a feed URL? http_request GET it (you need the raw XML; fetch_url would strip the tags).
2. Only a site URL? http_request the page and look for <link rel="alternate" ...> that points to a feed.
   None: try SITE/feed, SITE/rss.xml, SITE/atom.xml. Still none: check the footer and SITE/sitemap.xml
   before you say the site has no feed.
3. Known feed patterns:
   GitHub: https://github.com/OWNER/REPO/releases.atom (also .../commits/BRANCH.atom and .../tags.atom)
   YouTube channel: https://www.youtube.com/feeds/videos.xml?channel_id=UC...
   Hacker News: https://hnrss.org/frontpage and https://hnrss.org/newest?q=TERM
   arXiv category: https://rss.arxiv.org/rss/cs.CL
   Reddit: https://www.reddit.com/r/NAME/.rss (about 1 request per minute; see reddit-reading)
   Substack/WordPress: SITE/feed . Medium: medium.com/feed/@user . Ghost: SITE/rss/
4. Read the entries. RSS: each <item> has <title>, <link>, <pubDate>. Atom: each <entry> has <title>,
   <link href=...>, <published> or <updated>. JSON Feed: the "items" list.
   Short feed: read it from the text. Long feed: run_python that fetches with httpx, parses with
   xml.etree.ElementTree and prints "date | title | link" for the newest N entries, newest first.
5. "Since last check": keep the newest date seen in feeds/<name>.json and next time show only later entries.
   For a repeating digest use schedule_task, and notify when there are new entries.
6. Full article: fetch_url the entry link. Feed summaries are often cut short.

RULES
- A 200 reply that is an HTML page is not a feed: go to step 2.
- 403 from a feed host: read_skill blocked-page-recovery.
- Entries with no date go last, and are left out of "since" results.
- In reports cite the entry link, not the feed URL.
- Final answer: newest first, one line each: date - title - link (plus a short summary if asked),
  and which feed URL you used.
