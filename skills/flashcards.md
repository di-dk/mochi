name: flashcards
description: Make, review and quiz spaced-repetition flashcards stored as JSON decks in the workspace

DECK: flashcards/<deck>.json (default deck "general") holds a JSON list of cards:
  {"id": 1, "q": "...", "a": "...", "due": "YYYY-MM-DD", "streak": 0, "status": "learning"}

ADD
1. "Remember this" / "make a card": write one Q/A pair. Q tests one fact; A is short and starts with the answer.
   A bare fact with no card request: ask before saving. Ordinary questions or tasks: do not use this skill.
2. read_file the deck (missing -> start with []). Append the card with the next id and due = today.
   write_file the whole list back.
3. Quiz from a source (fetch_url, read_file, inspect_pdf): make 5 cards from its important or surprising facts.
   No true/false, no date-only questions, answers under 240 characters. Save them, then review them.

REVIEW
1. read_file the deck. Due = status "learning" and due <= today. None due -> say so and stop.
2. Show ONE question and wait. Never show or hint at the answer first.
3. Grade the reply, tell the user the right answer and the next review date, then update the card:
   correct (key fact right, any wording) -> due = today + 7 days, streak + 1; at streak 3 -> status "retired"
   partial (close, core detail missing)  -> due = today + 3 days, streak = 0; say what was missing
   wrong                                 -> due = today + 1 day,  streak = 0
   user says "retire this card"          -> status "retired"
4. Ask the next card. write_file the updated deck every 5 cards and at the end; read_file once to confirm it saved.

OTHER
- Stats: count total, learning, retired, due today.
- Export: create_spreadsheet("flashcards/<deck>.xlsx") with columns question, answer, deck.
- Import: read_spreadsheet a .csv/.xlsx with question and answer columns; add each row as a new card.
- Delete a card or deck only when the user names it and confirms.
- Feedback is plain text, brief and neutral. Example: "Not quite. Answer: 1989. Next review tomorrow."

Final answer: cards added or reviewed, counts correct/partial/wrong, how many are still due, deck path.
