name: price-monitor
description: Watch a product, flight, hotel or listing and alert when price or availability hits a target

SETUP (once, with the user)
1. Pin the exact item: URL, product/listing ID, variant (size, colour, seller, condition), quantity,
   location; for travel also dates, travellers and cabin/room type. Two variants must not be confusable.
2. Pin the alert rule: currency, all-in or pre-tax price, maximum price, stock/availability rule, shipping,
   refundability, and a cooldown between alerts.
3. Baseline: fetch_url the page (browser_open + browser_read if the price is missing from the text).
   Note the time, price, fees/taxes, availability and terms. Do not schedule until this works once.
4. write_file monitors/<name>.json: {"item": {}, "rule": {}, "last_good": {"time": "", "price": 0,
   "currency": "", "total": 0, "available": true}, "last_alert": null}
5. schedule_task (e.g. every 6 hours; never poll so often that the site blocks you) with the prompt:
   "read_skill price-monitor, then run the CHECK for monitors/<name>.json"

CHECK (every scheduled run)
6. read_file the state file, then fetch the page again the same way as the baseline.
7. Split what you see: base price, mandatory fees, shipping/taxes, total, availability. Keep the source
   currency. Convert only with a rate you looked up now, and note its time.
8. Fetch failed, or the page is an error or bot wall: the state is unknown. Do NOT overwrite last_good.
   Skip this run, or report the failure.
9. Compare like with like (all-in against all-in). Alert when the rule is newly met: total at or below the
   maximum, the wanted availability appears, or the price is clearly lower than at the last alert.
10. No repeats: same price and availability as last_alert, or cooldown not over -> stay silent.
11. edit_file the state: new last_good, and last_alert if you alert. Then notify, or stay silent.

RULES
- Check variant, seller, dates and terms match the pinned item. Never say the item is reserved.
- Alert text: exact item and variant, all-in price with source currency, availability and terms, the
  target, time checked, source link, and anything uncertain.
