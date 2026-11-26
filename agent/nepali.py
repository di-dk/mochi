"""Nepali helpers: the Bikram Sambat (BS) calendar, Devanagari digits and Nepali number grouping.

Date arithmetic comes from the `nepali-datetime` package (checked against the Nepali New Year dates and Bijaya Dashami
2082); the Devanagari names below are written here in the standard spellings. BS runs about 56 years 8 months ahead of
AD and the year starts in mid-April (Baisakh 1). Supported years: BS 1975-2100 (AD 1918-2043).
"""
from __future__ import annotations

import datetime as dt
import re

MONTHS_NE = ["बैशाख", "जेठ", "असार", "साउन", "भदौ", "असोज", "कात्तिक", "मंसिर", "पुष", "माघ", "फागुन", "चैत"]
MONTHS_EN = ["Baisakh", "Jestha", "Asar", "Shrawan", "Bhadra", "Ashwin", "Kartik", "Mangsir", "Poush", "Magh",
             "Falgun", "Chaitra"]
DAYS_NE = ["सोमबार", "मंगलबार", "बुधबार", "बिहीबार", "शुक्रबार", "शनिबार", "आइतबार"]     # Monday first, like Python
DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_NE_DIGITS = "०१२३४५६७८९"
_TO_NE = str.maketrans("0123456789", _NE_DIGITS)
_TO_ASCII = str.maketrans(_NE_DIGITS, "0123456789")


def to_nepali_digits(text: str) -> str:
    return str(text).translate(_TO_NE)


def to_ascii_digits(text: str) -> str:
    return str(text).translate(_TO_ASCII)


def group_lakh(n: int | float | str, decimals: int = 0) -> str:
    """Nepali/Indian digit grouping: 1234567 -> 12,34,567 (lakh and crore), ASCII digits."""
    x = float(to_ascii_digits(str(n)).replace(",", ""))
    s = f"{abs(x):.{decimals}f}"
    whole, _, frac = s.partition(".")
    head, tail = whole[:-3], whole[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    out = ",".join(parts + [tail]) if parts else tail
    return ("-" if x < 0 else "") + out + ("." + frac if frac else "")


def money(n: int | float | str, devanagari: bool = True, decimals: int = 0) -> str:
    """Nepali rupees: रु. १२,३४,५६७ (or 'Rs. 12,34,567')."""
    g = group_lakh(n, decimals)
    return "रु. " + to_nepali_digits(g) if devanagari else "Rs. " + g


def _nd():
    import nepali_datetime as nd
    return nd


def today_line() -> str:
    """One line with today's date in both calendars, computed fresh, for her instructions."""
    r = convert("")
    return (f"Today is {r['ad_en']} = BS {r['bs_ne']} ({r['bs']}). Use exactly this for 'today'; "
            "call nepali_date for any other date.")


def parse(text: str) -> tuple[str, tuple[int, int, int]]:
    """'YYYY-MM-DD' -> ('AD', (y, m, d)); 'YYYY-MM-DD BS' or Devanagari digits -> ('BS', ...)."""
    t = to_ascii_digits(text).strip()
    cal = "BS" if re.search(r"\b(BS|B\.S\.|बि\.?\s?सं\.?|वि\.?\s?सं\.?)\b", t, re.I) else "AD" if re.search(r"\bAD\b|\bA\.D\.\b", t, re.I) else ""
    m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", t)
    if not m:
        raise ValueError("Give a date as YYYY-MM-DD (AD) or YYYY-MM-DD BS.")
    y, mo, d = (int(v) for v in m.groups())
    if not cal:
        cal = "BS" if 1975 <= y <= 2100 else "AD"          # 2000-2100 can only be BS in practice; 1918-2043 AD otherwise
        if 1975 <= y <= 2043 and not re.search(r"BS", t, re.I):
            cal = "AD"                                      # ambiguous years are read as AD unless marked BS
    return cal, (y, mo, d)


def convert(text: str = "") -> dict:
    """Convert a date between AD and BS (empty text = today). Returns both calendars with names and weekday."""
    nd = _nd()
    if not text.strip():
        ad = dt.date.today()
    else:
        cal, (y, mo, d) = parse(text)
        try:
            ad = nd.date(y, mo, d).to_datetime_date() if cal == "BS" else dt.date(y, mo, d)
        except ValueError as e:
            raise ValueError(f"That is not a valid {cal} date ({e}).") from None
    try:
        bs = nd.date.from_datetime_date(ad)
    except (ValueError, OverflowError):
        raise ValueError("That date is outside the supported range (BS 1975-2100, AD 1918-2043).") from None
    wd = ad.weekday()
    return {"ad": ad.isoformat(), "bs": f"{bs.year:04d}-{bs.month:02d}-{bs.day:02d}", "bs_year": bs.year,
            "bs_month": bs.month, "bs_day": bs.day, "weekday_en": DAYS_EN[wd], "weekday_ne": DAYS_NE[wd],
            "month_en": MONTHS_EN[bs.month - 1], "month_ne": MONTHS_NE[bs.month - 1],
            "bs_ne": f"{to_nepali_digits(bs.year)} {MONTHS_NE[bs.month - 1]} {to_nepali_digits(bs.day)}, {DAYS_NE[wd]}",
            "ad_en": ad.strftime("%A, %d %B %Y")}
