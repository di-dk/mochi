"""Everyday helpers: speak aloud, weather, what is eating the disk, duplicate files."""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import httpx

from .policy import Policy
from .registry import Registry

S = {"type": "string"}
B = {"type": "boolean"}
I = {"type": "integer"}

WMO = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "rime fog",
       51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
       71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers", 81: "rain showers",
       82: "violent showers", 95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail"}


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _walk_sizes(root: Path, limit: int = 200_000):
    """Yield (path, size) for every file under root, skipping links and unreadable entries."""
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        for f in filenames:
            p = os.path.join(dirpath, f)
            try:
                if os.path.islink(p):
                    continue
                yield p, os.path.getsize(p)
            except OSError:
                continue
            seen += 1
            if seen >= limit:
                return


def add_more_tools(reg: Registry, policy: Policy, cfg: dict) -> None:
    @reg.add("speak", "Say text out loud through the speakers. Max ~1500 characters. language: the ISO code of the "
                      "text (nl, fr, de, es, it, ja, ...) so a matching voice is used; say it in the language you write.",
             {"text": S, "language": S}, ["text"])
    def speak(text: str, language: str = ""):
        text = text.strip()[:1500]
        if not text:
            return "Nothing to say."
        from . import platform_compat as pc
        ok, err = pc.speak(text, language)
        return "Spoke it." if ok else f"Could not speak: {err}"

    @reg.add("calculate",
             "Exact arithmetic. ALWAYS use this instead of working numbers out yourself. Supports + - * / // % ** (), "
             "round, abs, min, max, sqrt, pi, e, percentages ('15% of 2340', '8%'), and thousands commas. Returns the result.",
             {"expression": S}, ["expression"])
    def calculate(expression: str):
        import ast
        import math
        import operator as op
        e = expression.strip().replace("×", "*").replace("÷", "/").replace("^", "**")
        e = re.sub(r"(?<=\d),(?=\d{3}\b)", "", e)                                   # 2,340 -> 2340
        e = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*of\s+", r"(\1/100)*", e, flags=re.I)        # 15% of 2340
        e = re.sub(r"(\d+(?:\.\d+)?)\s*%(?!\s*[\d(])", r"(\1/100)", e)               # 8%  (a lone percent)
        bin_ops = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv, ast.FloorDiv: op.floordiv,
                   ast.Mod: op.mod, ast.Pow: op.pow}
        funcs = {"round": round, "abs": abs, "min": min, "max": max, "sqrt": math.sqrt}
        consts = {"pi": math.pi, "e": math.e}

        def ev(n):
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
                return n.value
            if isinstance(n, ast.BinOp) and type(n.op) in bin_ops:
                a, b = ev(n.left), ev(n.right)
                if isinstance(n.op, ast.Pow) and (abs(b) > 1000 or abs(a) > 1e12):
                    raise ValueError("that power is too large")
                return bin_ops[type(n.op)](a, b)
            if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
                return ev(n.operand) if isinstance(n.op, ast.UAdd) else -ev(n.operand)
            if isinstance(n, ast.Name) and n.id in consts:
                return consts[n.id]
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in funcs and not n.keywords:
                return funcs[n.func.id](*[ev(a) for a in n.args])
            raise ValueError("only numbers, + - * / // % ** and a few functions are allowed")
        try:
            v = ev(ast.parse(e, mode="eval").body)
        except ZeroDivisionError:
            return "ERROR: division by zero."
        except (ValueError, SyntaxError, TypeError, OverflowError) as ex:
            return f"ERROR: cannot calculate {expression!r}: {ex}"
        if isinstance(v, float) and v == int(v) and abs(v) < 1e15:
            v = int(v)
        elif isinstance(v, float):
            v = float(f"{v:.12g}")
        return f"{expression.strip()} = {v:,}" if isinstance(v, int) else f"{expression.strip()} = {v}"

    @reg.add("date_math",
             "Exact date arithmetic. ALWAYS use this for days between dates, adding or subtracting days/weeks/months, or the "
             "weekday of a date. start (and end) as YYYY-MM-DD, 'today', or like '14 July 2026'. With end: the difference. With "
             "days/weeks/months: start plus that (negative to go back). With neither: weekday and week number of start.",
             {"start": S, "end": S, "days": I, "weeks": I, "months": I}, ["start"])
    def date_math(start: str, end: str = "", days: int = 0, weeks: int = 0, months: int = 0):
        import calendar
        import datetime as dtm

        def parse(s: str):
            s = s.strip()
            if s.lower() == "today":
                return dtm.date.today()
            for f in ("%Y-%m-%d", "%d %B %Y", "%B %d %Y", "%B %d, %Y", "%d %b %Y", "%b %d %Y", "%b %d, %Y", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    return dtm.datetime.strptime(s, f).date()
                except ValueError:
                    continue
            raise ValueError(f"cannot read the date {s!r}; use YYYY-MM-DD")
        try:
            a = parse(start)
            if end.strip():
                b = parse(end)
                sign, lo, hi = (1, a, b) if b >= a else (-1, b, a)
                m = (hi.year - lo.year) * 12 + hi.month - lo.month - (1 if hi.day < lo.day else 0)
                ny, nm = lo.year + (lo.month - 1 + m) // 12, (lo.month - 1 + m) % 12 + 1
                rest = (hi - lo.replace(year=ny, month=nm, day=min(lo.day, calendar.monthrange(ny, nm)[1]))).days
                n = (hi - lo).days
                return (f"From {a.strftime('%A')} {a.isoformat()} to {b.strftime('%A')} {b.isoformat()}: {sign * n} days "
                        f"({n // 7} weeks {n % 7} days; {m} months {rest} days)")
            if days or weeks or months:
                y, mo = a.year + (a.month - 1 + months) // 12, (a.month - 1 + months) % 12 + 1
                r = a.replace(year=y, month=mo, day=min(a.day, calendar.monthrange(y, mo)[1])) + dtm.timedelta(days=days + 7 * weeks)
                return f"{a.isoformat()} {months:+d} months {weeks:+d} weeks {days:+d} days = {r.isoformat()} ({r.strftime('%A')})"
            iso = a.isocalendar()
            return f"{a.isoformat()} is a {a.strftime('%A')}, day {a.timetuple().tm_yday} of the year, ISO week {iso[1]}"
        except ValueError as ex:
            return f"ERROR: {ex}"

    @reg.add("translate_text",
             "Translate text with a DEDICATED translation pass: far more accurate than translating in your head while "
             "you also manage tools. to: the target language ('Nepali', 'Dutch', 'ja'...); source: optional; tone: "
             "'polite' (default), 'casual' or 'formal'. For Nepali the checked glossary is used automatically. Long text "
             "is split into chunks. Use it for every translation, then read the result once and fix obvious slips.",
             {"text": S, "to": S, "source": S, "tone": S}, ["text", "to"])
    def translate_text(text: str, to: str, source: str = "", tone: str = "polite"):
        from openai import OpenAI

        from .core import ROOT, api_key
        llm = cfg["llm"]
        model = llm.get("translator_model") or llm["model"]
        text = text.strip()
        if not text:
            return "Nothing to translate."
        system = ("You are a careful professional translator" + (f" from {source}" if source else "")
                  + f" into {to}. Keep the meaning, the tone ({tone}), names, numbers, links, Markdown and placeholders "
                  "such as {name} or %s exactly as they are. Write natural, idiomatic text that a native speaker would "
                  "write, not a word-for-word copy. Output ONLY the translation, with no notes, quotes or explanations.")
        if to.strip().lower() in ("nepali", "ne", "nep", "nepalese", "नेपाली"):
            gloss = ROOT / "skills" / "nepali-glossary.md"
            system += ("\n\nNepali rules: write Devanagari; use तपाईं-level politeness; postpositions are written attached to "
                       "the word (घरमा, मलाई, शुक्रबारसम्म); never use Hindi words or Hindi grammar (है, में, करता, आप); use "
                       "everyday words; keep dates as they are. Use the checked vocabulary and patterns below exactly.\n\n"
                       + (gloss.read_text(encoding="utf-8").split("\n\n", 1)[-1] if gloss.exists() else ""))
        client = OpenAI(base_url=llm["base_url"], api_key=api_key(cfg), timeout=600)
        paras, chunks, cur = text.split("\n"), [], ""
        for line in paras:                                   # about 1800 characters per request
            if len(cur) + len(line) > 1800 and cur:
                chunks.append(cur)
                cur = ""
            cur += line + "\n"
        chunks.append(cur)
        if len(text) > 20000:
            return "ERROR: that is more than 20,000 characters; translate it in parts."
        out = []
        for ch in chunks:
            kw = dict(model=model, temperature=0.2, messages=[{"role": "system", "content": system},
                                                              {"role": "user", "content": ch.strip()}])
            try:
                r = client.chat.completions.create(**kw, **({"reasoning_effort": "none"} if llm.get("reasoning_effort") else {}))
            except Exception:  # noqa: BLE001  (a model that does not know reasoning_effort)
                r = client.chat.completions.create(**kw)
            piece = (r.choices[0].message.content or "").strip()
            if not piece:
                return f"ERROR: the translation model ({model}) returned nothing. Try again or set llm.translator_model."
            glitch = re.compile(r"[\u0900-\u097f\u0600-\u06ff\u0590-\u05ff][A-Za-z]|[A-Za-z][\u0900-\u097f\u0600-\u06ff\u0590-\u05ff]")
            if glitch.search(piece):          # a stray Latin letter inside a word (models sometimes slip): ask once more
                kw2 = dict(kw, temperature=0.0)
                try:
                    r2 = client.chat.completions.create(**kw2, **({"reasoning_effort": "none"} if llm.get("reasoning_effort") else {}))
                except Exception:  # noqa: BLE001
                    r2 = client.chat.completions.create(**kw2)
                again = (r2.choices[0].message.content or "").strip()
                if again and not glitch.search(again):
                    piece = again
                else:
                    bad = glitch.search(piece)
                    piece += f"\n(⚠ check the spelling near '{piece[max(0, bad.start() - 6):bad.end() + 6]}': a Latin letter slipped into a word)"
            out.append(piece)
        return "\n".join(out)

    @reg.add("nepali_date",
             "Convert a date between the Gregorian (AD) and the Nepali Bikram Sambat (BS) calendar; empty = today. "
             "Give YYYY-MM-DD (AD) or YYYY-MM-DD BS (Devanagari digits work too); leave it empty for today. Returns both calendars with the "
             "weekday and the month in Nepali and English. Use it for EVERY Nepali date: month lengths change every "
             "year, so never work out a BS date yourself. Years BS 1975-2100.", {"date": S})
    def nepali_date(date: str = ""):
        try:
            from . import nepali
            r = nepali.convert(date)
        except ValueError as e:
            return f"ERROR: {e}"
        except ImportError:
            return "ERROR: the nepali-datetime package is not installed (pip install nepali-datetime)."
        return (f"AD: {r['ad_en']} ({r['ad']})\nBS: {r['bs']}  =  {r['bs_ne']}\n"
                f"Month: {r['month_ne']} ({r['month_en']}), weekday: {r['weekday_ne']} ({r['weekday_en']})")

    @reg.add("nepali_format",
             "Format a number the Nepali way. mode: 'digits' (ASCII to Devanagari digits), 'ascii' (Devanagari to ASCII "
             "digits), 'group' (lakh and crore grouping) or 'money' (rupees with that grouping). devanagari=false keeps ASCII digits "
             "for group/money.", {"value": S, "mode": S, "devanagari": B}, ["value"])
    def nepali_format(value: str, mode: str = "group", devanagari: bool = True):
        from . import nepali
        try:
            if mode == "digits":
                return nepali.to_nepali_digits(value)
            if mode == "ascii":
                return nepali.to_ascii_digits(value)
            dec = 2 if "." in nepali.to_ascii_digits(value).replace(",", "") else 0
            if mode == "money":
                return nepali.money(value, devanagari, dec)
            g = nepali.group_lakh(value, dec)
            return nepali.to_nepali_digits(g) if devanagari else g
        except ValueError:
            return f"ERROR: {value!r} is not a number."

    @reg.add("weather", "Current weather and a 3-day forecast for a city (Open-Meteo, no key needed).",
             {"city": S}, ["city"])
    def weather(city: str):
        g = httpx.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": city, "count": 1},
                      timeout=20).json()
        if not g.get("results"):
            return f"No place called '{city}' found."
        place = g["results"][0]
        w = httpx.get("https://api.open-meteo.com/v1/forecast", timeout=20, params={
            "latitude": place["latitude"], "longitude": place["longitude"], "timezone": "auto",
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum", "forecast_days": 3,
        }).json()
        c, d = w["current"], w["daily"]
        lines = [f"{place['name']}, {place.get('country', '')}: now {c['temperature_2m']}°C "
                 f"(feels {c['apparent_temperature']}°C), {WMO.get(c['weather_code'], 'unknown')}, "
                 f"wind {c['wind_speed_10m']} km/h, humidity {c['relative_humidity_2m']}%"]
        for i, day in enumerate(d["time"]):
            lines.append(f"{day}: {d['temperature_2m_min'][i]}–{d['temperature_2m_max'][i]}°C, "
                         f"{WMO.get(d['weather_code'][i], 'unknown')}, rain {d['precipitation_sum'][i]} mm")
        return "\n".join(lines)

    @reg.add("disk_usage", "Find what is taking space: the biggest subfolders and files under a folder.",
             {"path": S, "top": I}, ["path"])
    def disk_usage(path: str, top: int = 10):
        root = policy.check_read(path)
        if not root.is_dir():
            return f"{root} is not a folder."
        top = max(1, min(int(top), 30))
        per_dir: dict[str, int] = defaultdict(int)
        files: list[tuple[int, str]] = []
        total = 0
        for p, size in _walk_sizes(root):
            total += size
            files.append((size, p))
            rel = Path(p).relative_to(root).parts
            per_dir[rel[0] if len(rel) > 1 else "(files here)"] += size
        files.sort(reverse=True)
        out = [f"{root}: {human(total)} in total (scan stops at 200,000 files)", "Biggest folders:"]
        out += [f"  {human(s):>9}  {n}" for n, s in sorted(per_dir.items(), key=lambda kv: -kv[1])[:top]]
        out.append("Biggest files:")
        out += [f"  {human(s):>9}  {p}" for s, p in files[:top]]
        return "\n".join(out)

    @reg.add("find_duplicates", "List duplicate files (same content) under a folder. Only reports; never deletes.",
             {"path": S, "min_kb": I}, ["path"])
    def find_duplicates(path: str, min_kb: int = 100):
        root = policy.check_read(path)
        if not root.is_dir():
            return f"{root} is not a folder."
        by_size: dict[int, list[str]] = defaultdict(list)
        for p, size in _walk_sizes(root):
            if size >= max(1, int(min_kb)) * 1024:
                by_size[size].append(p)
        groups: list[tuple[int, list[str]]] = []
        for size, paths in by_size.items():
            if len(paths) < 2:
                continue
            by_hash: dict[str, list[str]] = defaultdict(list)
            for p in paths:
                try:
                    h = hashlib.sha256()
                    with open(p, "rb") as fh:
                        for chunk in iter(lambda: fh.read(1 << 20), b""):
                            h.update(chunk)
                    by_hash[h.hexdigest()].append(p)
                except OSError:
                    continue
            groups += [(size, g) for g in by_hash.values() if len(g) > 1]
        if not groups:
            return f"No duplicates of {max(1, int(min_kb))} KB or more under {root}."
        groups.sort(key=lambda g: -g[0] * (len(g[1]) - 1))
        wasted = sum(s * (len(g) - 1) for s, g in groups)
        out = [f"{len(groups)} duplicate set(s), about {human(wasted)} wasted. Nothing was deleted."]
        for size, g in groups[:15]:
            out.append(f"{human(size)} x{len(g)}:")
            out += [f"    {p}" for p in g]
        return "\n".join(out)
