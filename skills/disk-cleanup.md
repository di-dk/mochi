name: disk-cleanup
description: Find what fills a drive and which files are duplicates, then propose a safe cleanup the user approves

1. Ask which folder or drive to look at (default: the user's Downloads folder). Never start with C:\Windows.
2. disk_usage(path, top=15) to see the biggest folders and files.
3. find_duplicates(path, min_kb=500) on the folders that look worth it.
4. Group findings: duplicates | old installers and archives (.exe, .msi, .zip, .iso) | huge media | caches
   | unknown. For each give size, full path and why it is probably safe or not.
5. Write cleanup/<YYYY-MM-DD>-plan.md (write_file) with the groups, the total space that could be freed and a
   suggested action per item. Show the plan to the user.
6. Delete or move something ONLY after the user approves that exact item or group. Prefer moving to a
   "to-delete" folder inside the same drive first so it can be undone. Never touch Windows, Program Files,
   AppData, game save folders or anything the plan did not list.

RULES
- find_duplicates only reports; keep the oldest or best-named copy of each set and say which.
- Report real numbers from the tools, not estimates.

Final answer: space that could be freed, the plan file path, and what you still need approval for.
