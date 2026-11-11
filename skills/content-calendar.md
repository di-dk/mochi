name: content-calendar
description: Plan a multi-platform social media campaign as a dated spreadsheet of ready-to-post drafts

1. Ask for what is missing: goal, audience, core message or offer, platforms, date range, posts per week,
   voice, links, and any claims that are required or forbidden.
2. Gather source facts: read_file / read_document / inspect_pdf for the user's material, fetch_url for their
   pages. List claims you could not verify and assets that are missing.
3. Choose 4-6 themes and mix them: education, proof, product, community, behind the scenes, conversation.
4. Fill the slots: one row per post, spread over the date range, tied to launch dates or events.
5. Write each post for its platform: own hook, length and format. Do not paste the same copy everywhere.
6. Review every row: facts correct, no repeats, link works, rights to any quote or image, alt text present.
   Set Status to "draft", "needs review" or "approved" (approved only after the user says so).
7. create_spreadsheet("content-calendar.xlsx", rows), then read_spreadsheet to verify row count and dates.
8. If images are wanted, comfy_txt2img per post and put the file path in the Asset column.

COLUMNS
Date | Platform | Theme | Goal | Format | Hook | Copy | CTA | Link | Asset | Alt text | Metric | Status

RULES
- Every post serves the campaign goal. Drop filler posts instead of padding the schedule.
- Use only facts from the user's material. No invented numbers, testimonials or promises about the future.
- You cannot post or schedule on any platform. The deliverable is the draft package; never say "scheduled".
- A generated image is an asset, not a published post.

Final answer: the date range, posts per platform, themes used, unverified claims and missing assets,
the count of rows per Status, and the spreadsheet path.
