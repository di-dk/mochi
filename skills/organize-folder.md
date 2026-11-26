name: organize-folder
description: Sort a messy folder (Downloads, Desktop) into tidy subfolders by type and date, with a preview and undo list

1. Ask which folder. list_dir it once (not recursively). If it has more than 300 items, work on the newest 300.
2. Propose a layout by file type: Images (jpg png gif webp), Documents (pdf docx doc txt md rtf), Spreadsheets and data
   (xlsx xls csv json), Videos, Audio, Archives, Installers, Code, Other. If the user names the folders, use exactly
   those and put every file in one of them (txt and md are documents). Do not create more than 9 folders. Leave shortcuts and anything modified in the last 24 hours alone.
3. Write organize/<YYYY-MM-DD>-plan.md listing "old path -> new path" for every move. Show a summary count per
   folder and 5 example moves. Wait for approval.
4. After approval: make_folder for each folder, then move_path for each file (it never overwrites: a name clash gets
   " (2)"). No shell needed. Append every move to organize/<YYYY-MM-DD>-undo.md as "new path -> old path".
5. Verify with list_dir that the counts match the plan. Name every file that is still in the top folder. Never say
   "sorted" or "done" while files are left over: either move them or say which ones you left and why.

RULES
- Never delete anything. Never move files out of the folder the user named.
- If a move fails, log it and carry on; report the failures at the end.

Final answer: counts moved per folder, failures, and the undo file path.
