"""Run a battery of realistic tasks against the REAL model and check the results. Finds what she cannot do yet, instead of
the user finding it in a chat. Not part of the test suite (it is slow and needs Ollama, the internet and ComfyUI).

  python tools/battery.py                 # everything
  python tools/battery.py pdf xlsx        # only these tasks
Each task runs in a throw-away workspace. Routine approvals (running Python, shell, browser clicks) are granted; package
installs, sudo, deletes, and anything outside the workspace are refused, exactly like a careful user would."""
from __future__ import annotations

import copy
import json
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent.core import ROOT, Agent, load_config, make_policy  # noqa: E402

RISKY = re.compile(r"pip3? install|sudo|rm\s+-rf|curl[^|]*\||wget[^|]*\||chmod\s+-R|mkfs|dd if=", re.I)


def files(ws: Path, *pats):
    return [p for pat in pats for p in ws.rglob(pat) if ".scratch" not in p.parts and "skills" not in p.parts]


def prep_text(ws):
    (ws / "notes.txt").write_text("Project Aurora launches on 14 March. Budget: 48,000 euros. Lead: Maria Jansen. Risk: supplier delay.")


def prep_csv(ws):
    (ws / "people.csv").write_text("name,age,city\nAnna,31,Ghent\nBram,27,Leuven\nChloe,45,Brussels\n")


def prep_mix(ws):
    for n in ("a.txt", "b.txt", "photo1.jpg", "photo2.jpg", "report.pdf", "data.csv"):
        (ws / n).write_text("x")


def prep_image(ws):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (320, 240), (220, 60, 60))
    ImageDraw.Draw(im).ellipse((80, 50, 240, 190), fill=(60, 120, 220))
    im.save(ws / "photo.png")


def prep_invoice(ws):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(ws / "invoice.pdf"), pagesize=A4)
    c.drawString(72, 760, "Invoice 2026-114 for Studio Nova")
    c.drawString(72, 740, "Design work ....... 900.00 EUR")
    c.drawString(72, 720, "Hosting ........... 334.50 EUR")
    c.drawString(72, 700, "Total due: 1,234.50 EUR")
    c.save()


def grey(p: Path) -> bool:
    from PIL import Image
    im = Image.open(p).convert("RGB").resize((20, 20))
    return all(abs(r - g) < 6 and abs(g - b) < 6 for r, g, b in im.getdata())


TASKS = {
    "math": dict(prompt="What is 15% of 2,340, and how many days are there between 1 March 2026 and 14 July 2026?",
                 check=lambda ws, a: ("351" in a and "135" in a, "expects 351 and 135")),
    "fib": dict(prompt="Write and run a Python script that prints the first 20 Fibonacci numbers, then tell me the last one it printed.",
                check=lambda ws, a: (("4181" in a or "6765" in a), "expects 4181 (or 6765)")),
    "xlsx": dict(prompt="Make an Excel spreadsheet squares.xlsx with the numbers 1 to 10 and their squares, and a total row for the squares.",
                 check=lambda ws, a: _xlsx(ws)),
    "pdf": dict(prompt="Create a one-page PDF report called brussels.pdf about Brussels with a short intro and a Sources section.",
                check=lambda ws, a: _pdf(ws, "brussels", "Brussels")),
    "organize": dict(prompt="Sort the files in my workspace into folders by type: images, documents and data.", prep=prep_mix,
                     check=lambda ws, a: _organized(ws)),
    "summary": dict(prompt="Read notes.txt and tell me the launch date, the budget and who leads the project.", prep=prep_text,
                    check=lambda ws, a: ("14 March" in a and "48,000" in a.replace(" ", "") .replace("€", "") or "48000" in a, "expects date and budget") if "Maria" in a and ("14" in a) else (False, "expects 14 March, 48,000, Maria Jansen")),
    "csv": dict(prompt="Convert people.csv to JSON and save it as people.json.", prep=prep_csv, check=lambda ws, a: _json(ws)),
    "invoice": dict(prompt="Open invoice.pdf and tell me the total due.", prep=prep_invoice,
                    check=lambda ws, a: ("1,234.50" in a or "1234.50" in a, "expects 1,234.50")),
    "dutch": dict(prompt="Translate to Dutch: 'Good morning, how are you today?'",
                  check=lambda ws, a: (re.search(r"goedemorgen|goede morgen", a, re.I) is not None, "expects Goedemorgen")),
    "web": dict(prompt="Search the web and tell me what the Python programming language's latest stable release is. Give the source URL.",
                check=lambda ws, a: (re.search(r"3\.1\d", a) is not None and "http" in a, "expects a 3.1x version and a URL")),
    "nepali_date": dict(prompt="आजको मिति नेपालीमा भन्नुहोस्", check=lambda ws, a: _nepali_date(a)),
    "memory": dict(prompt="Remember that my favourite colour is teal. Then tell me what you will remember.",
                   check=lambda ws, a: ("teal" in a.lower() and "memory.md" in "".join(p.name for p in ws.rglob("memory.md")), "expects teal saved in memory.md")),
    "image": dict(prompt="Make a picture of a red dragon.", check=lambda ws, a: (bool(files(ws, "*txt2img*.png")) and not files(ws, "*self*.png"), "expects a text-to-image png, NOT a self-portrait")),
    "edit": dict(prompt="Make photo.png black and white and save it as photo_bw.png.", prep=prep_image,
                 check=lambda ws, a: (any(grey(p) for p in files(ws, "photo_bw*.png", "*bw*.png", "*grey*.png", "*gray*.png")), "expects a grey image")),
    "video": dict(prompt="Make a short video of a panda eating bamboo.", check=lambda ws, a: (bool(files(ws, "*.webm", "*.mp4")), "expects a video")),
    "self": dict(prompt="Draw yourself wearing sunglasses.", check=lambda ws, a: (bool(files(ws, "*self*.png")), "expects a self-portrait png")),
}


def _xlsx(ws):
    from openpyxl import load_workbook
    f = files(ws, "*.xlsx")
    if not f:
        return False, "no xlsx"
    vals = {c.value for row in load_workbook(f[0], data_only=False).active.iter_rows() for c in row}
    return (100 in vals or "100" in vals) and any(v in (385, "385") or (isinstance(v, str) and v.startswith("=")) for v in vals), "expects 100 and a total (385 or a formula)"


def _pdf(ws, stem, word):
    from pypdf import PdfReader
    f = files(ws, f"{stem}*.pdf")
    if not f:
        return False, "no pdf"
    txt = " ".join((p.extract_text() or "") for p in PdfReader(str(f[0])).pages)
    return word in txt and "ource" in txt, "expects the word and a Sources section"


def _organized(ws):
    dirs = {p.parent.name.lower() for p in ws.rglob("*") if p.is_file() and p.parent != ws and ".scratch" not in p.parts}
    left = [p.name for p in ws.iterdir() if p.is_file()]
    return len(dirs) >= 2 and not left, f"expects files in folders (folders={sorted(dirs)}, left over={left})"


def _json(ws):
    f = files(ws, "people.json")
    if not f:
        return False, "no people.json"
    d = json.loads(f[0].read_text(encoding="utf-8"))
    return isinstance(d, list) and len(d) == 3 and d[0].get("name") == "Anna", "expects 3 records"


def _nepali_date(a):
    sys.path.insert(0, str(ROOT))
    from agent import nepali
    r = nepali.convert("")
    return (nepali.to_nepali_digits(str(r["bs_day"])) in a and r["month_ne"] in a), f"expects {r['bs_ne']}"


def run(name: str, spec: dict) -> dict:
    cfg = copy.deepcopy(load_config())
    ws = Path(tempfile.mkdtemp(prefix=f"battery_{name}_")) / "ws"
    ws.mkdir(parents=True)
    cfg["sandbox"]["workspace"] = str(ws)
    approvals, tools = [], []

    def approver(cat, summary):
        ok = cat in ("python", "shell", "browser_action", "launch", "clipboard", "network_write") and not RISKY.search(summary)
        approvals.append((cat, "y" if ok else "n", summary[:80]))
        return "y" if ok else "n"

    pol = make_policy(cfg, approver=approver)
    pol.audit_path = ws.parent / "audit.jsonl"
    agent = Agent(cfg, pol, on_event=lambda k, d: tools.append(d["name"]) if k == "tool_call" else None)
    if spec.get("prep"):
        spec["prep"](ws)
    t0 = time.time()
    try:
        answer = agent.run(spec["prompt"])
        err = ""
    except Exception as e:  # noqa: BLE001
        answer, err = "", f"{type(e).__name__}: {e}"
    secs = time.time() - t0
    try:
        ok, why = spec["check"](ws, answer or "")
    except Exception as e:  # noqa: BLE001
        ok, why = False, f"checker crashed: {type(e).__name__}: {e}"
    return {"task": name, "ok": bool(ok), "secs": round(secs), "why": why if not ok else "", "error": err, "tools": tools[:12],
            "denied": [a for a in approvals if a[1] == "n"][:3], "answer": (answer or "")[:300]}


def prep_sales(ws):
    (ws / "sales.csv").write_text("month,sales\nJan,120\nFeb,150\nMar,90\nApr,200\n")


def prep_txts(ws):
    for n in ("one.txt", "two.txt", "three.md"):
        (ws / n).write_text("x")


TASKS.update({
    "chart": dict(prompt="Make a bar chart of the monthly sales in sales.csv and save it as sales.png.", prep=prep_sales,
                  check=lambda ws, a: ((ws / "sales.png").exists() and (ws / "sales.png").stat().st_size > 3000, "expects sales.png")),
    "rename": dict(prompt="Rename every .txt file in my workspace so its name starts with old_.", prep=prep_txts,
                   check=lambda ws, a: (all((ws / n).exists() for n in ("old_one.txt", "old_two.txt")) and not (ws / "one.txt").exists() and (ws / "three.md").exists(), "expects old_one.txt old_two.txt, three.md untouched")),
    "dates": dict(prompt="What weekday is 25 December 2026, and how many days are there from 26 November 2026 until then?",
                  check=lambda ws, a: ("Friday" in a and "29" in a, "expects Friday and 29")),
    "email": dict(prompt="Write a short polite email to my landlord asking him to fix a leaking kitchen tap, and save it as email.txt.",
                  check=lambda ws, a: ((ws / "email.txt").exists() and "tap" in (ws / "email.txt").read_text(errors="ignore").lower(), "expects email.txt mentioning the tap")),
    "vat": dict(prompt="I have three invoices: 1,234.50, 678.90 and 2,001.25 euros. What is the total, and how much is 21% VAT on that total?",
                check=lambda ws, a: (("3,914.65" in a or "3914.65" in a) and ("822.0" in a or "822.1" in a), "expects 3,914.65 and about 822.08")),
    "json": dict(prompt="Create a JSON file config.json with name set to demo, port set to 8080 and debug set to false.",
                 check=lambda ws, a: _config(ws)),
})


def _config(ws):
    f = files(ws, "config.json")
    if not f:
        return False, "no config.json"
    d = json.loads(f[0].read_text(encoding="utf-8"))
    return d.get("port") == 8080 and d.get("debug") is False and d.get("name") == "demo", "expects name demo, port 8080, debug false"


if __name__ == "__main__":
    pick = sys.argv[1:] or list(TASKS)
    out = ROOT / "logs" / "battery.jsonl"
    out.parent.mkdir(exist_ok=True)
    for name in pick:
        r = run(name, TASKS[name])
        out.open("a", encoding="utf-8").write(json.dumps({**r, "ts": time.strftime("%F %T")}, ensure_ascii=False) + "\n")
        print(f"{'PASS' if r['ok'] else 'FAIL'}  {name:12} {r['secs']:>4}s  tools={r['tools'][:5]}  {r['why'] or r['error']}", flush=True)
        if not r["ok"]:
            print("      answer:", r["answer"].replace("\n", " ")[:200], "| denied:", r["denied"], flush=True)
