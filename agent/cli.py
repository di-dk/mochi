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

from .core import ROOT, Agent, ensure_llm, load_config, make_policy

console = Console()


def approver(category: str, summary: str) -> str:
    console.print(Panel(summary, title=f"[bold yellow]Approval needed: {category}", border_style="yellow"))
    return Prompt.ask("[yellow]Allow?[/] [y]es / [n]o / [a]lways this session", choices=["y", "n", "a"], default="n")


def interactive_events(kind: str, data: dict) -> None:
    if kind == "tool_call":
        args = data["args"] if len(data["args"]) < 300 else data["args"][:300] + "…"
        console.print(f"[cyan]→ {data['name']}[/] [dim]{args}[/]")
    elif kind == "tool_result":
        r = data["result"].strip().replace("\n", " ⏎ ")
        style = "red" if r.startswith(("ERROR", "DENIED")) else "dim"
        console.print(f"  [{style}]{r[:240]}{'…' if len(r) > 240 else ''}[/]")
    elif kind == "note":
        console.print(f"[italic]{data['text'][:500]}[/]")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mochi")
    ap.add_argument("task", nargs="*", help="one-shot task")
    ap.add_argument("--unattended", action="store_true", help="no human present: refuse anything needing approval")
    ap.add_argument("--task-file", help="read the task from a file")
    ap.add_argument("--config", help="path to config.yaml")
    args = ap.parse_args(argv)

    cfg = load_config(Path(args.config) if args.config else None)
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
        f"{len(agent.registry.tools)} tools · commands: /reset  /tools  /allowed  /exit", border_style="magenta"))

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
        if text == "/allowed":
            console.print(agent.policy.session_allowed or "(nothing auto-approved)"); continue
        handle(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
