name: data-analysis
description: Analyze data and make charts: read a CSV or Excel file, compute with pandas, plot with matplotlib

Use for "analyze this data", "make a chart of ...", "what is the average / total / trend".
1. Look first: read_spreadsheet (or run_python with pandas.read_csv and df.head(), df.dtypes, len(df)). Say what the columns are.
2. Compute with run_python and pandas; print the numbers you will quote. Never work out sums, averages or percentages in your
   head: use the printed result, or calculate for a single expression.
3. Charts: matplotlib with matplotlib.use("Agg"); one clear chart per question; a title, axis labels with units, readable ticks;
   plt.tight_layout(); plt.savefig("<name>.png", dpi=150). Bar for categories, line for time, scatter for two numbers.
   Then view_image it (if you can see images) and share_file it.
4. Answer in plain words first (the finding), then the key numbers, then the file name of the chart.
5. Say what you did to the data (rows dropped, missing values, units guessed). Do not invent data; if a column is missing, say so.
6. Save results the user may want as .xlsx (create_spreadsheet) or .csv, with the exact name asked.
