name: data-to-spreadsheet
description: Collect data (web, files, text) into a clean Excel/CSV file, optionally with a summary document

1. Gather rows from the source (fetch_url / read_spreadsheet / read_file / search_files).
2. Decide columns; first row is the header. Keep units consistent; numbers as numbers, not strings.
3. create_spreadsheet(path.xlsx, rows). Formulas are allowed: "=SUM(B2:B20)".
4. VERIFY with read_spreadsheet: row count and a few values.
5. If a write-up is wanted: create_docx or create_pdf with a table of the key rows and the file path.
