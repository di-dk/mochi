name: decision-questionnaire
description: When a decision needs facts only someone else has, write a questionnaire for that person to fill in

First check the answer is not findable by you (workspace files, web_search). Use this only when another
person holds the knowledge.

1. Ask the user: who will receive it? (role, expertise, relationship). Do not ask the user the subject
   questions; they cannot answer them, which is why the document exists.
2. Ask the user: what must you be able to decide or do once the answers are back? Get a concrete list.
3. Draft questions that cover every item from step 2, aimed at what the recipient knows and the user does not.
4. write_file("questionnaires/<topic-slug>.md") using the layout below. If the user wants to send a Word or PDF
   file, also create_docx or create_pdf from the same text.
5. Check: every step-2 item has at least one question; each question has an empty answer line under it.

LAYOUT
# <Title>
Purpose: why this exists and which decision depends on it.
From / To / How the answers will be used.
## Context - one short paragraph for someone who was not part of the discussion.
## How to answer - deadline, rough effort; "I don't know" and partial answers are welcome.
## <Theme> - group questions by theme when there are more than about five.
### <One question>  then, only if it could be misread, "Why this matters: <one line>", then an empty "> " line.
## Anything else? - what did we not ask that we should know?

RULES
- One idea per question. Split any question containing "and" or "or".
- Most important question first; the reader may stop early.
- Context is one paragraph, not the whole history.

Final answer: the file path, the number of questions, and the list of needs each one covers.
