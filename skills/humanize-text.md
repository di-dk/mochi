name: humanize-text
description: Rewrite a draft so it stops sounding AI-written: cut stock patterns, keep the meaning, add voice

1. Get the text: pasted, or read_file / read_document. If the user gives a sample of their own writing, read it
   first and copy its sentence length, word level, punctuation habits and pet phrases.
2. Find every pattern from the REMOVE list and rewrite those parts. Keep every fact and the intended tone.
3. Ask yourself "what still sounds machine-made?", note 1-3 leftovers, and revise once more.
4. Pasted text: reply with the final version. File: write_file the result to a new file ("<name>-humanized")
   and show the changed parts. Do not overwrite the original unless asked.

REMOVE
- Inflated importance: pivotal, testament, "plays a key role", "evolving landscape", "marks a shift".
- Ad words: vibrant, stunning, renowned, nestled, groundbreaking, seamless. Vague sources: "experts say".
- AI vocabulary: delve, crucial, foster, showcase, underscore, tapestry, intricate, additionally, leverage.
- Trailing -ing phrases that fake depth (", highlighting its importance").
- "serves as / stands as / boasts" where "is / has" works. "Not just X, but Y". Forced groups of three.
- Several synonyms for one thing; "from X to Y" where there is no real scale; strained metaphors.
- Em dashes, scattered bold, emoji, Title Case Headings, bullets that start with a bold label.
- Chatbot leftovers: "Great question", "I hope this helps", "let me know", "as of my last update".
- Filler and hedges: "in order to", "it is important to note", "could potentially".
- Signposting ("let's dive in"), questions answered at once, openers like "So," or "Interestingly,".
- Poster-style fragments, mic-drop last lines, "and that's okay", generic upbeat endings.

ADD
- Mixed sentence lengths, specific details instead of vague claims, plain "is / are / has".
- An opinion or mixed feeling, and "I", where the format allows it.
- Never invent facts, names, quotes or numbers to sound specific. Not for manuals; use simple-english there.

Final answer: the rewrite, then 2-4 bullets on what changed (and the file path if one was written).
