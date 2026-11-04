"""Terminal interface.

  mochi                       interactive chat
  mochi "do something"        run one task interactively, then exit
  mochi --unattended --task-file f.txt   (used by scheduled tasks; approvals are refused)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .core import ROOT, Agent, ensure_llm, list_models, load_config, make_policy, save_local_setting

console = Console()


def approver(category: str, summary: str) -> str:
    console.print(Panel(summary, title=f"[bold yellow]Approval needed: {category}", border_style="yellow"))
    return Prompt.ask("[yellow]Allow?[/] [y]es / [n]o / [a]lways this session", choices=["y", "n", "a"], default="n")


def interactive_events(kind: str, data: dict) -> None:
    if kind == "tool_call":
        args = data["args"] if len(data["args"]) < 300 else data["args"][:300] + "…"
        console.print(f"[cyan]→ {data['name']}[/] [dim]{args}[/]")
    elif kind == "tool_result" and data["name"] in ("set_plan", "update_plan") and not data["result"].startswith("ERROR"):
        console.print(Panel(data["result"].removeprefix("Plan:\n"), title="plan", border_style="dim", expand=False))
    elif kind == "tool_result" and data["name"] in ("save_skill", "save_lesson"):
        console.print(f"  [magenta]📚 {data['result']}[/]")
    elif kind == "tool_result":
        r = data["result"].strip().replace("\n", " ⏎ ")
        style = "red" if r.startswith(("ERROR", "DENIED")) else "dim"
        console.print(f"  [{style}]{r[:240]}{'…' if len(r) > 240 else ''}[/]")
    elif kind == "nudge":
        console.print("  [dim]↻ nudging her to finish the remaining steps…[/]")
    elif kind == "image":
        console.print(f"  [magenta]👀 looking at {', '.join(Path(p).name for p in data['paths'])}[/]")
    elif kind == "note":
        console.print(f"[italic]{data['text'][:500]}[/]")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mochi")
    ap.add_argument("task", nargs="*", help="one-shot task")
    ap.add_argument("--unattended", action="store_true", help="no human present: refuse anything needing approval")
    ap.add_argument("--task-file", help="read the task from a file")
    ap.add_argument("--config", help="path to config.yaml")
    ap.add_argument("--model", help="use this LM Studio model for this run only (see /models)")
    args = ap.parse_args(argv)

    cfg = load_config(Path(args.config) if args.config else None)
    if args.model:
        cfg["llm"]["model"] = args.model
    task = Path(args.task_file).read_text(encoding="utf-8") if args.task_file else " ".join(args.task)

    if args.unattended:
        log = ROOT / "logs" / f"run_{time.strftime('%Y%m%d_%H%M%S')}.log"
        log.parent.mkdir(exist_ok=True)
        with log.open("w", encoding="utf-8") as f:
            def ev(kind, data):
                f.write(f"[{time.strftime('%H:%M:%S')}] {kind}: {str(data)[:2000]}\n"); f.flush()
            try:
                ensure_llm(cfg, log=lambda s: ev("info", {"msg": s}))
                agent = Agent(cfg, make_policy(cfg, approver=None), on_event=ev)
                answer = agent.run(task)
                f.write(f"\nFINAL ANSWER:\n{answer}\n")
                (agent.policy.workspace / "reports").mkdir(exist_ok=True)
                name = Path(args.task_file).stem if args.task_file else "task"
                (agent.policy.workspace / "reports" / f"{name}_{time.strftime('%Y%m%d_%H%M')}.md").write_text(
                    f"# {name}\n\n**Task:** {task}\n\n{answer}\n", encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                f.write(f"\nFAILED: {type(e).__name__}: {e}\n")
                return 1
        return 0

    with console.status("Checking LM Studio..."):
        ensure_llm(cfg, log=lambda s: console.print(f"[dim]{s}[/]"))
    agent = Agent(cfg, make_policy(cfg, approver=approver), on_event=interactive_events)
    console.print(Panel.fit(
        f"[bold magenta]🍡 {cfg['agent']['name']}[/] · model [cyan]{cfg['llm']['model']}[/] · workspace [green]{agent.policy.workspace}[/]\n"
        f"{len(agent.registry.tools)} tools · commands: /models  /model <n>  /reset  /tools  /allowed  /exit",
        border_style="magenta"))

    def show_models() -> list[dict]:
        models = list_models(cfg)
        t = Table(box=None, pad_edge=False)
        for col in ("#", "model", "size", "tools", "vision", ""):
            t.add_column(col)
        for i, m in enumerate(models, 1):
            cur = "← current" if m["modelKey"] == cfg["llm"]["model"] else ""
            t.add_row(str(i), m["modelKey"], f"{m.get('sizeBytes', 0) / 2**30:.1f} GB",
                      "✓" if m.get("trainedForToolUse") else "[red]✗[/]", "✓" if m.get("vision") else "", cur)
        console.print(t)
        console.print("[dim]Switch with /model <number or name>. Models without tool support can't use Mochi's tools.[/]")
        return models

    def switch_model(choice: str) -> None:
        models = list_models(cfg)
        pick = None
        if choice.isdigit() and 1 <= int(choice) <= len(models):
            pick = models[int(choice) - 1]
        else:
            hits = [m for m in models if choice.lower() in m["modelKey"].lower()]
            pick = hits[0] if len(hits) == 1 else None
            if len(hits) > 1:
                console.print(f"[yellow]'{choice}' matches several: {', '.join(m['modelKey'] for m in hits)}[/]"); return
        if not pick:
            console.print(f"[red]No model matches '{choice}'. Type /models to see the list.[/]"); return
        key = pick["modelKey"]
        if key == cfg["llm"]["model"]:
            console.print(f"[dim]Already using {key}.[/]"); return
        if not pick.get("trainedForToolUse"):
            console.print("[yellow]Warning: this model isn't marked for tool use, so tools may not work.[/]")
        old = cfg["llm"]["model"]
        cfg["llm"]["model"] = key
        try:
            with console.status(f"Loading {key} (≈1 min)…"):
                ensure_llm(cfg, log=lambda s: None)
        except Exception as e:  # noqa: BLE001
            cfg["llm"]["model"] = old
            console.print(f"[red]Couldn't load {key}: {e}. Staying on {old}.[/]"); return
        save_local_setting("llm", "model", key)
        agent.refresh_model_info()
        agent.messages[0] = agent.system_message()
        console.print(f"[magenta]🍡 Now using [bold]{key}[/]. Saved as default in config.local.yaml.[/]")

    def handle(text: str) -> None:
        t0 = time.time()
        try:
            answer = agent.run(text)
        except KeyboardInterrupt:
            console.print("[red]Interrupted.[/]"); return
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]Error: {type(e).__name__}: {e}[/]"); return
        console.print(Panel(Markdown(answer), title=f"{cfg['agent']['name']} · {time.time() - t0:.0f}s", border_style="magenta"))

    if task:
        handle(task)
        return 0
    while True:
        try:
            text = Prompt.ask("\n[bold cyan]you[/]").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text in ("/exit", "/quit"):
            break
        if text == "/reset":
            agent.reset(); agent.policy.session_allowed.clear(); console.print("[dim]Conversation reset.[/]"); continue
        if text == "/tools":
            console.print(", ".join(agent.registry.tools)); continue
        if text == "/models":
            show_models(); continue
        if text.startswith("/model"):
            arg = text[len("/model"):].strip()
            if not arg:
                console.print(f"Current model: [cyan]{cfg['llm']['model']}[/]. Type /models to list, /model <n> to switch.")
            else:
                switch_model(arg)
            continue
        if text == "/allowed":
            console.print(agent.policy.session_allowed or "(nothing auto-approved)"); continue
        handle(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
