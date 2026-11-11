name: stocks
description: Look up stock or crypto prices, find a ticker, get price history or compare tickers (read-only)

Data comes from Yahoo Finance: free, no key, unofficial, so it can rate-limit or change without notice.
Use http_request GET with headers {"User-Agent": "Mozilla/5.0"}. If query1 fails, try the same path on query2.
1. Ticker unknown: https://query1.finance.yahoo.com/v1/finance/search?q=COMPANY&quotesCount=5&newsCount=0
   Confirm symbol, name, exchange and type with the user's intent before you quote a price.
2. Quote: https://query1.finance.yahoo.com/v8/finance/chart/SYMBOL?interval=1d&range=1d
   Read chart.result[0].meta: regularMarketPrice, chartPreviousClose, currency, regularMarketVolume,
   fiftyTwoWeekHigh, fiftyTwoWeekLow. Change = price - previous close; change % = change / previous * 100.
3. History: the same URL with range=1mo (default), 3mo, 6mo, 1y or 5y. The reply has timestamp[] and
   indicators.quote[0] with open/high/low/close/volume lists.
   Report min, max, average and total return % = (last close - first close) / first close * 100.
   Many rows: use run_python for the arithmetic. Do not do it in your head.
4. Compare: one row per ticker with price, change % and 52-week range. Use a table
   (create_spreadsheet if the user wants a file).
5. Crypto: add -USD to the symbol (BTC -> BTC-USD, ETH -> ETH-USD) and treat it like a ticker.
6. Both hosts fail: web_search "<TICKER> stock price", fetch_url a quote page from the results, and say
   which page the figure came from.

RULES
- Several tickers: wait a second between requests to avoid rate limits.
- Requests keep failing: the source changed or is limiting you. Say so. Do not loop.
- Market cap and P/E are often missing. Write "not available". Never guess a number.
- Every figure must come from a reply you fetched in this task, with the time you read it.
- Read-only: no orders, no accounts, no logins. This is information, not investment advice.
- Final answer: ticker and name, price with currency, change and change %, the time read, and the source.
  For history add range, min, max, average and total return. For compare give the table.
