"""Terminal interface.

  mochi                       interactive chat
  mochi "do something"        run one task interactively, then exit
  mochi --gui                 her own chat window (same agent, same settings)
  mochi --unattended --task-file f.txt   (used by scheduled tasks; approvals are refused)
  mochi --bench [name ...]    time the installed models and show which is fastest

While she is working you can keep typing: a line + Enter is handed to her before her next step, /stop makes her
stop. One background thread reads the keyboard and routes each line to whoever is waiting for it.
"""
from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .core import ROOT, Agent, ensure_llm, list_models, load_config, make_policy, save_local_setting

console = Console()


class Keyboard:
    """Single reader of stdin. Each typed line goes to exactly one place: an approval question that is waiting,
    the busy agent (as an extra message, or /stop), or the idle prompt (as the next command)."""

    def __init__(self):
        self.commands: queue.Queue = queue.Queue()     # lines typed while idle (None = end of input)
        self.answers: queue.Queue = queue.Queue()      # lines typed while an approval question is open
        self.agent = None
        self.busy = False
        self.asking = False
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        while True:
            try:
                line = input().strip()
            except (EOFError, OSError):
                self.commands.put(None)
                self.answers.put("n")
                return
            self.route(line)

    def route(self, line: str) -> None:
        if self.asking:
            self.answers.put(line)
        elif self.busy and self.agent is not None:
            if not line:
                return
            if line.lower() in ("/stop", "stop", "/cancel"):
                self.agent.stop.set()
                console.print("  [yellow]■ stopping…[/]")
            else:
                self.agent.inbox.put(line)
                console.print("  [green]↪ got it, she will see this before her next step[/]")
        else:
            self.commands.put(line)

    def ask(self, prompt: str) -> str | None:
        """Next line typed at the idle prompt; None when input ended. Ctrl+C raises KeyboardInterrupt."""
        console.print(prompt, end="")
        while True:
            try:
                return self.commands.get(timeout=0.2)
            except queue.Empty:
                continue

    def approve(self, category: str, summary: str) -> str:
        console.print(Panel(summary, title=f"[bold yellow]Approval needed: {category}", border_style="yellow"))
        self.asking = True
        try:
            while True:
                console.print("[yellow]Allow?[/] \\[y]es / \\[n]o / \\[a]lways this session (n): ", end="")
                while True:
                    try:
                        answer = (self.answers.get(timeout=0.2) or "n").lower()
                        break
                    except queue.Empty:
                        continue
                if answer[:1] in ("y", "n", "a"):
                    return answer[:1]
                console.print("[red]Please answer y, n or a.[/]")
        finally:
            self.asking = False


_live = {"text": "", "open": False, "on": True}   # the reply currently being written on screen


def _close_live() -> None:
    if _live["open"]:
        console.print()
        _live["open"] = False


def interactive_events(kind: str, data: dict) -> None:
    if kind == "token":                          # show her reply while she writes it
        if not _live["on"]:
            return
        if not _live["open"]:
            console.print("\n[magenta]🍡[/] ", end="")
            _live["open"] = True
        _live["text"] += data["text"]
        console.print(data["text"], end="", markup=False, highlight=False, soft_wrap=True)
        return
    if kind == "thinking":
        _close_live()
        _live["text"] = ""
        return
    if kind == "note" and _live["text"].strip() == data["text"].strip():
        _close_live()                            # already shown live
        return
    _close_live()
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
    elif kind == "skill":
        console.print(f"  [magenta]📖 using her skill: {data['name']}[/]")
    elif kind == "steer":
        console.print(f"  [green]↪ she read your message: {data['text'][:200]}[/]")
    elif kind == "check":
        console.print("  [dim]✓ double-checking the answer against your request…[/]")
    elif kind == "condense":
        console.print(f"  [dim]⇣ memory is full: condensing an older result ({data['chars']} chars)…[/]")
    elif kind == "note":
        console.print(f"[italic]{data['text'][:500]}[/]")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mochi")
    ap.add_argument("task", nargs="*", help="one-shot task")
    ap.add_argument("--unattended", action="store_true", help="no human present: refuse anything needing approval")
    ap.add_argument("--task-file", help="read the task from a file")
    ap.add_argument("--config", help="path to config.yaml")
    ap.add_argument("--model", help="use this LM Studio model for this run only (see /models)")
    ap.add_argument("--gui", action="store_true", help="open Mochi in her own chat window")
    ap.add_argument("--bench", nargs="*", metavar="NAME",
                    help="time the installed tool-capable models (optionally only those matching NAME) and exit")
    args = ap.parse_args(argv)

    cfg = load_config(Path(args.config) if args.config else None)
    if args.model:
        cfg["llm"]["model"] = args.model
    task = Path(args.task_file).read_text(encoding="utf-8") if args.task_file else " ".join(args.task)
    if args.gui:
        from .gui import run_gui
        return run_gui(cfg)
    if args.bench is not None:
        from .bench import run_bench
        return run_bench(cfg, args.bench, console)

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
    _live["on"] = bool((cfg.get("ui") or {}).get("stream_answer", True))
    kb = Keyboard()
    agent = Agent(cfg, make_policy(cfg, approver=kb.approve), on_event=interactive_events)
    kb.agent = agent
    console.print(Panel.fit(
        f"[bold magenta]🍡 {cfg['agent']['name']}[/] · model [cyan]{cfg['llm']['model']}[/] · workspace [green]{agent.policy.workspace}[/]\n"
        f"{len(agent.registry.tools)} tools · commands: /models  /model <n>  /reset  /tools  /allowed  /exit\n"
        f"[dim]While she works: type a message + Enter to add to the task, /stop to stop her.[/]",
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
        kb.busy = True
        try:
            answer = agent.run(text)
        except KeyboardInterrupt:
            console.print("[red]Interrupted.[/]"); return
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]Error: {type(e).__name__}: {e}[/]"); return
        finally:
            kb.busy = False
        shown = _live["open"] and _live["text"].strip() == answer.strip()
        _close_live()
        if shown:                                # she already wrote it on screen: just close it off
            console.rule(f"[magenta]{cfg['agent']['name']} · {time.time() - t0:.0f}s", style="magenta")
        else:
            console.print(Panel(Markdown(answer), title=f"{cfg['agent']['name']} · {time.time() - t0:.0f}s",
                                border_style="magenta"))
        _live["text"] = ""

    if task:
        handle(task)
        return 0
    while True:
        try:
            text = kb.ask("\n[bold cyan]you[/]: ")
        except KeyboardInterrupt:
            break
        if text is None:
            break
        if not text:
            continue
        if text in ("/exit", "/quit"):
            break
        if text == "/reset":
            agent.reset(); agent.policy.session_allowed.clear(); console.print("[dim]Conversation reset.[/]"); continue
        if text == "/tools":
            loaded = {t["function"]["name"] for t in agent.registry.schemas(auto=agent._auto_tools())}
            console.print(", ".join(n if n in loaded else f"[dim]{n}[/]" for n in agent.registry.tools))
            console.print("[dim]Dim tools are not loaded yet; she loads their group when a task needs it.[/]")
            continue
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
