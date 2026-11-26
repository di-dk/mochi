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
             "Give 2026-11-26 (AD) or 2083-08-10 BS (Devanagari digits work too). Returns both calendars with the "
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
             "Format numbers the Nepali way. mode: 'digits' (1234 -> १२३४), 'ascii' (१२३४ -> 1234), 'group' (1234567 -> "
             "12,34,567: lakh and crore grouping) or 'money' (-> रु. १२,३४,५६७). devanagari=false keeps ASCII digits "
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
