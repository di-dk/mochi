"""`mochi --bench`: time each installed model on three fixed jobs so you can pick the fastest one that still
chooses the right tool. Nothing is executed; only the model's first reply to each job is measured."""
from __future__ import annotations

import copy
import time

from openai import OpenAI
from rich.console import Console
from rich.table import Table

from .core import Agent, ensure_llm, list_models, make_policy

ARTICLE = ("The city council met on Tuesday to vote on the new cycling plan. The plan adds 42 km of protected bike "
           "lanes over three years at a cost of 18 million euros, paid for by a parking levy. Shop owners on the "
           "main street objected that removing 120 parking spaces would hurt trade, while the hospital welcomed "
           "the plan because cycling injuries fell by 30 percent in districts that already have protected lanes. "
           "The vote passed 9 to 6. Work starts in March on the riverside section. ") * 6


def _timed(client: OpenAI, **kw) -> tuple[float, int, object]:
    t0 = time.time()
    r = client.chat.completions.create(**kw)
    dt = time.time() - t0
    usage = getattr(r, "usage", None)
    return dt, (getattr(usage, "completion_tokens", 0) or 0), r.choices[0].message


def bench_model(cfg: dict, key: str) -> dict:
    cfg = copy.deepcopy(cfg)
    cfg["llm"]["model"] = key
    t0 = time.time()
    ensure_llm(cfg, log=lambda s: None)
    row = {"model": key, "load": time.time() - t0}
    agent = Agent(cfg, make_policy(cfg, approver=None))
    client, system = agent.client, agent.messages[0]
    tools = agent.registry.schemas(auto=True)
    row["prompt_chars"] = len(system["content"]) + len(str(tools))

    dt, toks, _ = _timed(client, model=key, temperature=0.3, messages=[
        system, {"role": "user", "content": "Say hello in one short sentence."}], tools=tools)
    row["chat"] = dt                                            # first call: includes reading the whole prompt
    dt, toks, msg = _timed(client, model=key, temperature=0.3, messages=[
        system, {"role": "user", "content": "Which files are in my workspace folder right now?"}], tools=tools)
    row["tool"] = dt
    row["tool_ok"] = bool(msg.tool_calls) and msg.tool_calls[0].function.name in ("list_dir", "find_files")
    dt, toks, _ = _timed(client, model=key, temperature=0.3, messages=[
        {"role": "user", "content": "Summarise this in exactly 3 short bullet points:\n\n" + ARTICLE}])
    row["summary"] = dt
    row["tok_s"] = toks / dt if dt and toks else 0.0
    return row


def run_bench(cfg: dict, names: list[str], console: Console) -> int:
    models = [m for m in list_models(cfg) if m.get("trainedForToolUse")]
    if names:
        models = [m for m in models if any(n.lower() in m["modelKey"].lower() for n in names)]
    if not models:
        console.print("[red]No tool-capable models matched. Run /models to see what is installed.[/]")
        return 1
    original = cfg["llm"]["model"]
    console.print(f"[dim]Benchmarking {len(models)} model(s). Each one is loaded in turn (about a minute each).[/]")
    rows = []
    for m in models:
        key = m["modelKey"]
        try:
            with console.status(f"{key}…"):
                rows.append(bench_model(cfg, key))
        except Exception as e:  # noqa: BLE001 - one model failing to load must not stop the others
            console.print(f"[red]{key}: {type(e).__name__}: {str(e)[:200]}[/]")
    t = Table(box=None, pad_edge=False)
    for col in ("model", "load", "first reply", "tool choice", "right tool", "summary", "tokens/s"):
        t.add_column(col)
    for r in sorted(rows, key=lambda r: r["tool"]):
        t.add_row(r["model"] + (" ← current" if r["model"] == original else ""), f"{r['load']:.0f}s",
                  f"{r['chat']:.1f}s", f"{r['tool']:.1f}s", "✓" if r["tool_ok"] else "[red]✗[/]",
                  f"{r['summary']:.1f}s", f"{r['tok_s']:.0f}" if r["tok_s"] else "?")
    console.print(t)
    console.print("[dim]first reply = cold start, reads the whole prompt once. tool choice = a warm step, the "
                  "number that matters most. Switch with /model <name>.[/]")
    try:
        with console.status(f"Reloading {original}…"):
            ensure_llm(cfg, log=lambda s: None)
    except Exception as e:  # noqa: BLE001
        console.print(f"[yellow]Could not reload {original}: {e}[/]")
    return 0
