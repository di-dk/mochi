name: daily-briefing
description: Morning briefing: weather, today's tasks, news on topics the user follows, optionally read aloud

1. recall for the user's city, topics they follow and where their tasks live. Ask once if the city is unknown, then remember it.
2. weather(city) for today and the next 2 days. One line: what to wear or bring.
3. Tasks: read the user's task or notes file if recall names one (read_file). You cannot see a calendar unless
   the user pastes or exports it; say so instead of guessing.
4. News: web_search each followed topic (max 3 topics, 2 results each). Keep only items from the last 2 days
   and give the source name for each.
5. Write it as short bullets under: Weather | Today | Worth knowing. No more than 15 lines.
6. If the user asked for it aloud, speak(text) with a shorter spoken version (max 8 sentences, no URLs).
7. Offer schedule_task to run this every morning.

RULES
- Never invent weather or headlines: every line comes from a tool result you just got.
- If a source fails, name it under "Could not check".

Final answer: the briefing itself.
