name: learn-new-skill
description: Teach yourself something you don't know how to do: research, try safely, verify, then save it as a skill

Use when a request needs something you have no skill or lesson for. Never answer "I can't" before doing this.
1. find_skills with 2-3 keywords and recall. If a close recipe exists, use it and adapt it. Then look for a ready
   skill in git: list_git_skills query=<keyword> (default repo anthropics/skills; any public GitHub repo works).
   import_skill asks the user first; read_skill it, test it on a small task, and fix or save_skill what you change.
2. Tell the user in one line what you are going to learn, then set_plan: research, small test, verify, save.
3. Research: web_search 2-3 focused queries (add "official docs" or the tool's name), then fetch_url the best 1-2
   pages (official docs, README, man page first; blogs last). Note the exact commands or API calls and the URLs.
   Also check what you already have: use_tools lists tool groups, run_shell "<program> --help", comfy_node_info.
4. Try the smallest safe test in the workspace with throwaway files. Change one thing at a time. Read the whole
   error. After 3 identical failures, search the error text or change approach (a 4th identical call is blocked).
5. Anything risky (installing software, deleting, changing system settings, spending money, sending data out,
   signing in, files outside the workspace): stop and ask the user, say exactly what and why. Never skip an approval.
6. Verify with a real check: read the output back, view_image, inspect_pdf, run it twice. Only what passed counts.
7. save_skill: name = the task in 2-4 words, description = when to use it, steps = the exact recipe that worked
   (tools, arguments, settings), pitfalls, and sources = the URLs. save_lesson for every mistake you made.
8. Answer: the result first, then "I learned: <skill name>", and anything you could not do and why.
If it will not work, say what you tried and what is missing. Do not pretend, and do not save untested steps.
