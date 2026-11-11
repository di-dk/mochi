name: systematic-debugging
description: Find the root cause of a bug, failing test or error before changing any code (4 phases)

RULE: no fix until you can say WHY it breaks. Never guess-and-patch.
1. set_plan with: reproduce, isolate, hypothesis, fix, verify.
2. Read the whole error and stack trace. Note file, line, error code. search_files for the error text,
   read_file the code around it.
3. Build ONE repro command that fails on this exact symptom and will pass once it is fixed, e.g.
   run_powershell: python -m pytest tests/test_x.py::test_name -q   (or a tiny run_python script).
   It must be fast and give the same result every run. Cannot reproduce? Gather more data, do not guess.
4. Check what changed: run_powershell "git log --oneline -10" and "git diff"; also new packages or config.
5. Several components? Print what goes in and out at each boundary, run once, find where it turns wrong.
   Then trace the bad value back to where it is first created.
6. Shrink the repro: remove one input or step at a time while it still fails.
7. Find similar code that works (search_files). List every difference, even small ones.
8. Write 3-5 possible causes. For each: "if this is the cause, then doing Y will show Z". Rank them by
   likely and cheap to check. Test the top one with the smallest probe. Change one thing at a time.
   Tag temporary prints with [DEBUG-x1] so one search_files finds them all for cleanup.
9. Cause confirmed: add a failing regression test, then make ONE fix at the source of the bad value.
   No extra "while I am here" edits.
10. Run the repro, then the full test suite. Remove the debug prints.

RULES
- A probe that proves nothing means a NEW hypothesis, not another fix stacked on top.
- After 3 failed fixes STOP: the design is probably wrong. Explain that and ask the user how to go on.
- If you do not understand something, say so and ask or research (web_search the exact error text).
- save_lesson when the cause was surprising.

Final answer: root cause in one sentence, the evidence, what you changed (file + line), the test
command and its result, anything still open.
