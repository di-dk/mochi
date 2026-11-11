name: decision-brief
description: Answer a "what are my options?" question as a 1-3-1 brief: one problem, three options, one pick

Use when several approaches are viable and the trade-offs matter. Skip it for questions with one obvious
answer or when the user has already chosen.

1. Collect context: what the user said, plus files (read_file / read_document) or web_search if facts are missing.
2. PROBLEM: one sentence stating the decision or desired outcome. Say what, not how. No tool or product names.
   If the sentence needs "and", it is two problems; pick the main one.
3. OPTIONS: exactly three, labelled A, B, C. Each gets one line of description, then Pros and Cons.
   They must be different strategies, not small variations of one idea.
4. RECOMMENDATION: name one option and give the reason, tied to the user's situation. Be direct; do not hedge.
5. DEFINITION OF DONE: 3-5 concrete, checkable results for the recommended option.
6. PLAN: numbered steps to carry it out, each a specific action.
7. Reply in chat with these five labels in this order. If the user wants to forward it, create_docx or
   create_pdf with the same sections.
8. If the user picks a different option, rewrite Recommendation, Definition of Done and Plan for that option.

RULES
- One problem sentence. Three options. One recommendation. Count them before answering.
- Every option has at least one real con, including the one you recommend.
- Done criteria must be observable ("page loads in under 2 s"), not hopes ("works well").
- Do not invent facts or prices; say what you assumed.

Final answer: Problem, Options A/B/C with pros and cons, Recommendation, Definition of Done, Plan,
and the file path if a document was made.
