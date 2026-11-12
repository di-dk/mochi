"""Everyday helpers: speak aloud, weather, what is eating the disk, duplicate files."""
from __future__ import annotations

import hashlib
import os
import subprocess
from collections import defaultdict
from pathlib import Path

import httpx

from .policy import Policy
from .registry import Registry

S = {"type": "string"}
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
    @reg.add("speak", "Say text out loud through the speakers (Windows voice). Max ~1500 characters.",
             {"text": S}, ["text"])
    def speak(text: str):
        text = text.strip()[:1500]
        if not text:
            return "Nothing to say."
        script = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                  " $s.Speak([Console]::In.ReadToEnd())")
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script], input=text, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=180)
        return "Spoke it." if r.returncode == 0 else f"Could not speak: {r.stderr.strip()[:200]}"

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
