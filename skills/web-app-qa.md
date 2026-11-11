name: web-app-qa
description: Explore a website or web app like a tester, collect bugs with screenshots, write a bug report

Need from the user: the start URL and the scope (which features, or "whole site").
1. set_plan: list the pages and flows to test: home, navigation links (header, footer), key flows
   (search, sign-up, forms), plus edge cases (empty states, error pages, a made-up URL for the 404).
2. browser_open(url). browser_read for the text and the interactive elements.
3. browser_screenshot and LOOK: overlapping or cut-off text, broken images, unstyled parts, poor
   contrast. Use full_page=true for long pages.
4. Test each interactive element, one action at a time:
   - browser_click links and buttons. Does it go where the label says?
   - browser_fill forms with valid data, then invalid data (bad email, letters in a number field,
     very long text, special characters), then submit empty.
   - Run multi-step flows from start to end.
5. After EVERY action: browser_read or browser_screenshot. Compare what you expected with what happened.
6. For every problem, save evidence at once: browser_screenshot(path="qa/screenshots/issue-03-name.png").
   Note: URL, steps to reproduce, expected, actual, screenshot path.
7. Rate each issue. Severity: Critical (blocks a main flow or loses data), High, Medium, Low.
   Category: Functional, Visual, Accessibility, UX, Content.
8. Merge duplicates (same bug on several pages = one issue). Sort by severity, Critical first.
9. Write the report in Markdown: summary (scope, total, count per severity); one section per issue
   (title, severity, category, URL, steps, expected vs actual, screenshot); a table of all issues;
   testing notes (what was tested, what was not, blockers).
   Save with write_file as qa/report.md, or create_pdf when the user wants a PDF. Then browser_close.

RULES
- Only test what the user named. Never enter real passwords or payment data.
- Do not submit anything that sends messages, places orders or deletes data unless the user agrees.
- Report only what you saw yourself. No screenshot, no bug.

Final answer: issue counts by severity, the top 3 issues in one line each, and the report path.
