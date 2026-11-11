name: plan-interview
description: Stress-test a plan or idea with tough questions before building ("grill me", "poke holes")

Use before complex or risky work, or when a plan is vague. Not for reviewing finished code or tiny tasks.
1. Restate the plan in 2-3 lines. Picture it as a tree: each decision opens further decisions.
2. Look up facts yourself first: list_dir, search_files, read_file, fetch_url. Never ask the user for
   something you can find. Ask the user only for decisions.
3. Ask ROUND 1: every question that can be answered right now, numbered, in one message. Format:
   Q1 - <short title>: <question, with options if useful>
   Recommendation: <your answer and a one-line reason>
4. A question that depends on an answer you do not have yet goes in a LATER round.
5. Wait for the answers. Work out which questions are now unblocked. Ask the next round.
6. Repeat until no decision is left open or silently assumed.

COVER THESE
- Goal: what is the real objective? What is in scope and what is out? Limits: time, tech, budget, users.
- Each technical choice: why this and not X? What if it fails? Worst case? How do you roll back?
  If the project already has a pattern for this, point it out.
- Edge cases: unexpected user actions, a dependency being down, 100x the expected volume, security.

RULES
- Be critical. If everything looks fine, look harder.
- "I don't know" is not an answer: offer 2-3 options with trade-offs and recommend one.
- No code and no file changes during the interview.
- Use the language the user writes in.

FINISH
7. Summarize ALL decisions as bullets. List what is still open and what is explicitly out of scope.
8. Ask: "Aligned? Shall I start, or adjust something?" Do not act until the user says yes.
9. If the user wants it kept, write_file the summary as plan.md; then set_plan from it.

Final answer: the decisions list, open items, out-of-scope list, and the alignment question.
