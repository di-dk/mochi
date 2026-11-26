name: translate-text
description: Translate text, files and documents between languages, keeping format, names and meaning

Use for "translate this", "put this in Dutch", "make a bilingual version", "what does this say?".
1. Settle: the source language (detect it and say which), the target language(s), the tone (formal or casual; ask only
   if it matters) and what must stay as it is (names, brand terms, code, numbers, quotes).
2. Short text: answer with the translation only, no lecture. Add one alternative only for a truly ambiguous phrase.
3. Use translate_text for every translation (a dedicated pass, much better than translating in your head).
   Files: read_document or read_file first. Keep the structure: headings, lists, tables, links, Markdown, HTML tags and
   placeholders like {name} or %s. Translate long texts in chunks of about 1500 words and keep a small glossary of the
   terms you chose, so every chunk uses the same words.
4. Save the result as a NEW file (name-nl.docx, name-fr.md ...), never over the original: create_docx, create_pdf or
   write_file. PDFs handle Latin, Cyrillic, Greek, Chinese, Japanese, Korean, Arabic and Hebrew (right to left is
   automatic); for Thai or Indic scripts use create_docx. Then share_file it.
5. Check before you answer: compare with the source. Numbers, dates, names, units and links must be intact. Change number
   and date formats only to the target's habit (1.234,56 vs 1,234.56; 26/11 vs 11/26) and say so when you do.
6. UI strings, subtitles and keys: keep similar length, leave keys and placeholders untouched.
7. If you are not confident in a language, say so, give your best attempt and mark the uncertain parts.
8. Text inside an image: view_image to read it, then give the translation in the chat.
