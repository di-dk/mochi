name: simple-english
description: Rewrite docs, instructions or error messages in short, unambiguous Simplified Technical English

1. Get the text: pasted, or read_file / read_document. If the user only wants a check, list each problem as
   "offending text -> fixed text" and stop there.
2. Label each passage PROCEDURE (tells the reader what to do) or DESCRIPTION (explains a thing).
3. Pick one word per thing and per action (only "settings"; only "make sure that") and use it everywhere.
4. Rewrite with the rules below.
5. Self-check: count the words in the 3 longest sentences. Look for contractions, "should", "has been",
   semicolons, and any "if"/"when" that does not start its sentence. Fix what you find.
6. Pasted text: answer in chat. File: write_file to a new file; keep the original.

RULES
- Procedure: max 20 words per sentence, one instruction per sentence, imperative ("Install the driver.").
- Description: max 25 words per sentence, one new fact per sentence, one topic and max 6 sentences per paragraph.
- Condition first, then the command: "If the build fails, read the log."
- Active voice and simple tenses. No "has been", no "is being". Write "compress the file", not "do compression".
- Modals: only can, will, must. should -> must (or delete it). may / might / could -> can.
- Full grammar: keep "the", "a", "that". No contractions, no semicolons, no e.g. / i.e. / etc.
- No -ing verbs after a comma. Noun chains of 3 words at most. No phrasal verbs ("set up" -> "configure").
- Do not use a noun as a verb or a verb as a noun.
- Delete empty words: simply, just, easily, robust, powerful, seamless.
- Replace: utilize -> use; in order to -> to; prior to -> before; allows you to -> you can.
- Risk notes: start with "WARNING:" (injury) or "CAUTION:" (damage), then the command, then the risk.
- Never change code, commands, file paths, identifiers, quoted errors or product names.
- Not for marketing or blog text. Say so and offer humanize-text instead.

Final answer: the rewritten text (or the list of problems), the one-word choices you made, and the file path.
