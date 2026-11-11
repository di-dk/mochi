name: spike
description: Build small throwaway experiments to check if an idea is feasible or to compare approaches

Use when the user says "can this even work?", "try X quickly", "compare A and B" before a real build.
Do not use when docs or existing code can answer it (just research) or the idea is already proven.
1. Split the idea into 2-5 feasibility questions. Write each as: Given ..., when ..., then <something
   you can observe>. Give each a risk: high, medium or low. Skip this if the user named one exact spike.
2. Order by risk: the question most likely to kill the idea goes first. Show the table and ask
   "Build all in this order, or adjust?" Wait for the answer. Then set_plan.
3. Per spike, research just enough: web_search, fetch_url the real docs. If there is a real choice,
   list approach, pros, cons, maintained or not. Pick one and say why. Pure logic needs no research.
4. Build in its own folder: spikes/001-short-name/ with main.py (or index.html) and README.md.
   Two approaches to one question share the number: 002a-..., 002b-...
5. Make it something the user can try. Prefer in this order: a script that takes input and prints
   output, a small HTML page, a tiny local server, a test with clear asserts.
6. Hardcode everything. No config system, no build tools, no extra packages.
7. Run it with run_python or run_powershell. One happy run is not proof: try edge cases, bad input,
   bigger input. Follow up anything surprising.
8. End each README.md with: Verdict (VALIDATED, PARTIAL or INVALIDATED), What worked, What did not,
   Surprises, Recommendation for the real build.
   PARTIAL = works only under limits; list them. INVALIDATED is a useful result, not a failure.
9. Comparison spikes: build both, then a table (quality, setup effort, speed, limits) and name a winner.
10. Asked "what next?": look for spikes never tried together, unproven assumptions, or another angle
    on a PARTIAL or INVALIDATED one. Offer 2-4 candidates.

RULE: spike code is disposable. Never polish it or copy it into the real project as is.

Final answer: a table of spike, question, verdict; the key evidence; folder paths; what to build next.
