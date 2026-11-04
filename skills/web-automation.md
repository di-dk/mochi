name: web-automation
description: Do a task on a website headlessly (search a site, fill a form, read results) with Mochi's own browser

1. browser_open(url) — invisible by default; her profile keeps cookies/logins between sessions.
2. browser_read to get text + interactive elements (ids/names); browser_screenshot to SEE the layout (vision).
3. browser_fill(selector, value) for inputs (prefer #id or [name=...] selectors), browser_click for buttons/links.
4. After each action, browser_read or browser_screenshot to confirm the page changed as expected.
5. Never enter passwords or payment details yourself — ask the user to log in with browser_open(url, visible=true).
6. Summarize results with the page URL; browser_close when finished.
