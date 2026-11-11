name: api-debugging
description: Debug a REST or GraphQL API call: wrong status, auth failure, bad payload or odd data

Find the failing layer first, then fix. Go in order and do not skip a layer.
1. Reach: http_request GET on the base URL or a /health path. No answer = DNS, VPN, proxy or firewall.
2. Slow or dead? Use run_python with httpx and timeout=httpx.Timeout(30, connect=5):
   ConnectTimeout = cannot reach the host; ReadTimeout = reached it but the server is slow.
3. TLS: a certificate error means expired, self-signed or wrong hostname. Never turn verification off.
4. Auth: is the header really sent? Right scheme (Bearer, Basic, X-Api-Key, or ?api_key= in the URL)?
   Right environment (staging key on prod)? JWT: decode the middle part with run_python and check exp.
5. Request: correct method, path, version prefix, trailing slash. Content-Type must match the body.
   Send JSON as JSON, not as a form string. Check required fields and URL-encoded query values.
6. Response: read status and Content-Type before parsing. HTML or an empty body where JSON is expected
   is the bug. GraphQL often answers 200 on failure: always look at the "errors" field.
7. Meaning: is the id the one you asked for? Timezone? Only page 1? Follow next_cursor / next_page.

STATUS HINTS
- 401 credentials missing, wrong or expired. 403 logged in but no permission, scope or IP allowed.
- 404 wrong path, id, API version or base URL. 409 duplicate create or stale ETag.
- 422 valid JSON, wrong data: the body names the fields (type, required, enum value).
- 429 rate limit: wait for Retry-After, then retry with growing pauses.
- 5xx server side: retry with backoff; keep X-Request-Id / X-Trace-Id / CF-Ray for the provider.

RULES
- Never print, store or put tokens in files or answers; write <REDACTED>. The user supplies the token.
- POST/PUT/PATCH/DELETE change real data and ask the user first. Reproduce with GET when you can.
- fetch_url the provider's docs for the endpoint instead of guessing the format.

Final answer: Finding (endpoint, status, request id), Repro (method, URL, headers with the token
redacted, body), Root cause, Fix.
