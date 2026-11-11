name: arxiv-papers
description: Find, read and cite arXiv papers by keyword, author, category or ID (free API, no key)

1. Search: http_request GET https://export.arxiv.org/api/query?search_query=all:WORD1+WORD2&max_results=5
   Newest first: add &sortBy=submittedDate&sortOrder=descending . Next page: add &start=N (0-based).
2. Field prefixes: all: ti: (title) au: (author) abs: (abstract) cat: (category: cs.AI cs.CL cs.CV cs.LG ...).
   Join with +AND+ / +OR+ / +ANDNOT+, e.g. search_query=au:hinton+AND+cat:cs.LG . Phrase: ti:"chain+of+thought"
3. Known paper: http_request GET https://export.arxiv.org/api/query?id_list=2402.03300 (comma-separate several).
4. The reply is Atom XML. Each <entry> has <id> (ends in the versioned ID, e.g. 1706.03762v7), <title>,
   <published>, <author><name>, <summary> (the abstract) and <category term=...>. Read them from the text.
   Use run_python (xml.etree.ElementTree) only when there are many entries to tabulate.
5. Read: fetch_url https://arxiv.org/abs/ID for the abstract page. Full text: fetch_url https://arxiv.org/html/ID
   when it exists, else download_file https://arxiv.org/pdf/ID and inspect_pdf the saved PDF.
6. Impact and related work (optional, JSON from Semantic Scholar, no key):
   http_request GET https://api.semanticscholar.org/graph/v1/paper/arXiv:ID?fields=title,year,citationCount
   Cited by: same URL base + /citations?fields=title,authors,year&limit=10 . It cites: + /references?...
7. BibTeX on request: @article with title, author (names joined by " and "), year, eprint = ID,
   archivePrefix = arXiv, primaryClass = first category, url = https://arxiv.org/abs/ID

RULES
- Go slowly: one arXiv request every 3 seconds, one Semantic Scholar request per second.
- If <summary> says withdrawn or retracted, do not present the entry as a valid paper.
- Cite the versioned ID you actually read (v1, v2 ...); the plain ID always points at the latest version.
- Never invent a paper, author or ID. Report only entries the API returned.
- Final answer: numbered papers with ID, title, authors, date, a 1-2 line gist and the abs link.
