name: convert-files
description: Convert files between formats (CSV, JSON, Excel, text, Markdown) and save them under the exact name asked

Use for "convert X to Y", "save it as name.ext", "turn this into a spreadsheet / JSON / CSV".
1. Use the EXACT file name the user gave (people.json means people.json, not people.json.docx or people-converted.json).
   If they gave only a format, keep the original name and change the extension. Never change the format they asked for.
2. Pick the tool by the OUTPUT: .xlsx create_spreadsheet; .docx create_docx; .pdf create_pdf; .json .csv .txt .md .html
   write_file (or run_python for large or tricky data). create_docx is only for Word files.
3. Read the input first (read_file, read_spreadsheet, read_document). For JSON from a table: a list of objects, one per row,
   keys from the header, numbers as numbers. For CSV from JSON: one header row. Keep UTF-8 and the original order.
4. Check: read the result back (read_file) and compare the row count with the input. Then say where the file is.
5. Big files: use run_python with the csv, json or pandas modules and print only a short summary.
If the exact name already exists, do not overwrite it silently: ask, or add " (2)".
