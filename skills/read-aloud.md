name: read-aloud
description: Read a file, web page or summary out loud with a Windows voice, in chunks

1. Get the text: read_file / read_document for files, fetch_url for a page. If it is long, offer to read a
   summary instead, and say how many minutes the full text would take (about 150 words a minute).
2. Clean it: drop URLs, table of contents, citations like [12], and markdown symbols.
3. speak(text) in chunks of at most 1200 characters, splitting at sentence ends. Between chunks check that
   the user has not typed "stop"; if they have, stop at once.
4. Do not read private data (passwords, keys, personal messages) aloud unless the user asked for that text.

Final answer: what was read, how much, and where it stopped if it was cut short.
