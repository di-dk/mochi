"""Hybrid memory search: her saved notes (workspace/memory.md) and everything said in past chats (workspace/chats/*.json).

Ranking is BM25 (exact words, works for any script including Nepali) with a recency boost: a note from today beats the same
note from a year ago, saved notes decay slower than chat lines. If `memory.embed_model` is set (an Ollama embedding model such as
nomic-embed-text) meaning-based similarity is mixed in, so "my sister's birthday" can find "Sita turns 30 on May 4". Without it,
or if the embedding server is not reachable, it is plain BM25. Everything stays on this PC.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from pathlib import Path

import httpx

TOKEN = re.compile(r"\w+", re.UNICODE)
STOP = {"the", "a", "an", "and", "or", "of", "to", "is", "are", "was", "in", "on", "for", "it", "i", "you", "my", "me", "that", "this", "with"}


def _stem(w: str) -> str:
    """Very light stemming so 'PDFs' finds 'pdf' and 'birthdays' finds 'birthday' (any script: only trailing s/es is touched)."""
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def tokens(text: str) -> list[str]:
    return [_stem(t) for t in TOKEN.findall(text.lower()) if t not in STOP and len(t) > 1]


def collect(workspace: Path, max_chats: int = 300) -> list[dict]:
    """Every searchable line: {text, source, ts, kind}. Notes are 'note', chat lines are 'chat'."""
    docs: list[dict] = []
    mem = workspace / "memory.md"
    if mem.is_file():
        for line in mem.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^- \[(\d{4}-\d{2}-\d{2})\]\s*(.*)", line)
            ts = time.mktime(time.strptime(m.group(1), "%Y-%m-%d")) if m else mem.stat().st_mtime
            docs.append({"text": (m.group(2) if m else line.lstrip("- ")), "source": "saved note " + (m.group(1) if m else ""),
                         "ts": ts, "kind": "note"})
    chats = sorted((workspace / "chats").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:max_chats]
    for f in chats:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ts = float(d.get("updated") or d.get("created") or f.stat().st_mtime)
        title = d.get("title") or f.stem
        for t in d.get("transcript") or []:
            if t.get("t") in ("user", "bot") and (t.get("text") or "").strip():
                who = "you said" if t["t"] == "user" else "I said"
                docs.append({"text": t["text"].strip(), "source": f"chat '{title}' ({who}, {time.strftime('%Y-%m-%d', time.localtime(ts))})",
                             "ts": ts, "kind": "chat"})
    return docs


def bm25(query: list[str], docs: list[list[str]], k1: float = 1.4, b: float = 0.75) -> list[float]:
    n = len(docs)
    if not n or not query:
        return [0.0] * n
    avg = sum(len(d) for d in docs) / n or 1.0
    df: dict[str, int] = {}
    for d in docs:
        for w in set(d):
            df[w] = df.get(w, 0) + 1
    out = []
    for d in docs:
        tf: dict[str, int] = {}
        for w in d:
            tf[w] = tf.get(w, 0) + 1
        s = 0.0
        for q in set(query):
            if q in tf:
                idf = math.log(1 + (n - df[q] + 0.5) / (df[q] + 0.5))
                s += idf * tf[q] * (k1 + 1) / (tf[q] + k1 * (1 - b + b * len(d) / avg))
        out.append(s)
    return out


def _embed(cfg: dict, texts: list[str]) -> list[list[float]] | None:
    """Embeddings from the local Ollama server, or None when no embedding model is configured/reachable."""
    model = (cfg.get("memory") or {}).get("embed_model")
    if not model:
        return None
    base = (cfg.get("memory") or {}).get("embed_url") or cfg["llm"]["base_url"].replace("/v1", "")
    try:
        r = httpx.post(base.rstrip("/") + "/api/embed", json={"model": model, "input": texts}, timeout=60)
        r.raise_for_status()
        return r.json()["embeddings"]
    except (httpx.HTTPError, KeyError, ValueError):
        return None


def _cos(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def search(cfg: dict, workspace: Path, query: str, limit: int = 8, now: float | None = None, embed=None) -> list[dict]:
    """The best matches for a query, most relevant first: [{text, source, score}]."""
    now = now or time.time()
    docs = collect(workspace)
    if not docs:
        return []
    q = tokens(query)
    if not q:                                           # empty query: the newest notes
        notes = [d for d in docs if d["kind"] == "note"][-limit:]
        return [{**d, "score": 0.0} for d in reversed(notes)]
    scores = bm25(q, [tokens(d["text"]) for d in docs])
    top = max(scores) or 1.0
    sem = [0.0] * len(docs)
    embedder = embed or (lambda texts: _embed(cfg, texts))
    cand = [i for i, s in enumerate(scores) if s > 0]
    if (cfg.get("memory") or {}).get("embed_model") or embed:
        pool = cand[:200] if len(cand) >= 20 else list(range(min(len(docs), 400)))
        vecs = embedder([query] + [docs[i]["text"][:500] for i in pool])
        if vecs and len(vecs) == len(pool) + 1:
            for i, v in zip(pool, vecs[1:]):
                sem[i] = max(0.0, _cos(vecs[0], v))
    ranked = []
    for i, d in enumerate(docs):
        if scores[i] <= 0 and sem[i] < 0.35:
            continue
        age_days = max(0.0, (now - d["ts"]) / 86400)
        half = 180.0 if d["kind"] == "note" else 45.0
        recency = 0.6 + 0.4 * 0.5 ** (age_days / half)
        rel = 0.65 * (scores[i] / top) + 0.35 * sem[i] if any(sem) else scores[i] / top
        ranked.append({**d, "score": round(rel * recency * (1.15 if d["kind"] == "note" else 1.0), 4)})
    if not ranked:                                      # nothing matched by words: plain substring match (the old behaviour)
        low = query.lower().split()
        for d in docs:
            if all(w in d["text"].lower() for w in low):
                ranked.append({**d, "score": 0.01})
    ranked.sort(key=lambda r: r["score"], reverse=True)
    seen, out = set(), []
    for r in ranked:                                    # the same sentence in several chats counts once
        key = hashlib.md5(r["text"].lower().encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            out.append(r)
        if len(out) >= limit:
            break
    return out
