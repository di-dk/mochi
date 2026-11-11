name: grounded-citations
description: Answer or write a document where every outside fact has a numbered [n] citation and Sources list

1. Start a ledger: write_file citations/ledger.json with {"sources": []}. Keep the old one only when
   continuing a draft that already uses its numbers.
2. Each time web_search / fetch_url / browser_read returns a page you will use, add it to the ledger BEFORE
   writing prose: {"id": next number, "url": exact URL from the tool result, "title": "...", "quotes": []}.
   The same URL always keeps the same id. Never add a URL from memory. Never renumber.
3. Draft with the id right after each sentence the source supports, no space before the bracket:
   Ice floats because it is less dense than liquid water.[1][2]
4. End with "Sources:" and one line per CITED id: [n] Title - URL. Copy each URL from the ledger file.
5. Check before delivering: read_file the ledger; every [n] in the text exists there, every listed source
   is cited, and the URLs match. Fix and check again.
6. Documents: write the Markdown the same way, then create_pdf or create_docx with Sources as last section.

FACT-CHECK MODE (medical, legal, money, safety, disputed claims, or when the user asks)
- For each source, copy one exact sentence from the fetched page text into its "quotes". No paraphrase.
- An important claim you could not source gets [unverified] instead of a number. If many do, search more.
- Disputed fact: find a second independent source, cite both readings, say which you weight and why.
- Print each source's quote under its line in Sources, so the reader can check claim -> source -> words.

RULES
- At most 3 ids per sentence. Cite sentence by sentence, not all at the end.
- A search snippet supports only what it literally says. fetch_url the page before citing its body.
- Claims from your own knowledge get no citation. Forum posts are opinion: write "users report".
- Give figures, dates and names exactly as the source states them. For gaps write "no source found for X".
- Skip citations for casual chat, creative writing or a quick mid-task lookup.
- Final answer: the cited text plus the Sources list (and the file path if you made a document).
