"""Tool registry: functions + JSON schemas exposed to the model."""
from __future__ import annotations

import json
import traceback
from dataclasses import dataclass
from typing import Any, Callable

from .policy import Denied
from .smart import group_of

MAX_RESULT_CHARS = 12000


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    fn: Callable[..., Any]

    def schema(self) -> dict:
        return {"type": "function",
                "function": {"name": self.name, "description": self.description,
                             "parameters": self.parameters}}


class Registry:
    def __init__(self):
        self.tools: dict[str, Tool] = {}
        self.pending_images: list[tuple[str, str]] = []   # (path, caption) to show a vision model
        self.vision = False                              # set by Agent when the model can see
        self._repeat, self._last_sig = 0, None
        self.enabled_groups: set[str] = set()            # tool groups loaded for this session

    def attach_image(self, path, caption: str = "") -> str:
        """Queue an image to be shown to the model after the current tool call."""
        if not self.vision:
            return " (the current model cannot view images; switch to a vision model such as gemma to see it)"
        self.pending_images.append((str(path), caption))
        return " (image attached below so you can see it)"

    def drain_images(self) -> list[tuple[str, str]]:
        imgs, self.pending_images = self.pending_images, []
        return imgs

    def add(self, name: str, description: str, properties: dict, required: list[str] | None = None):
        def deco(fn):
            self.tools[name] = Tool(name, description,
                                    {"type": "object", "properties": properties,
                                     "required": required or []}, fn)
            return fn
        return deco

    def schemas(self, auto: bool = False) -> list[dict]:
        """All tool schemas, or with auto=True only core tools plus the groups loaded so far."""
        if not auto:
            return [t.schema() for t in self.tools.values()]
        return [t.schema() for n, t in self.tools.items()
                if (g := group_of(n)) is None or g in self.enabled_groups]

    def call(self, name: str, raw_args: str | dict, policy) -> str:
        tool = self.tools.get(name)
        if tool is None:
            return f"ERROR: unknown tool '{name}'. Available: {', '.join(self.tools)}"
        try:
            args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args or "{}")
        except json.JSONDecodeError as e:
            return f"ERROR: tool arguments were not valid JSON ({e}). Retry with valid JSON."
        policy.audit("tool_call", tool=name, args=args)
        if group_of(name):                       # a tool from a group that was not loaded yet: load it
            self.enabled_groups.add(group_of(name))
        try:
            result = tool.fn(**args)
        except Denied as e:
            result = f"DENIED: {e}"
        except TypeError as e:
            result = f"ERROR: bad arguments for {name}: {e}"
        except Exception as e:  # tool failures go back to the model so it can recover
            result = f"ERROR: {type(e).__name__}: {e}\n{traceback.format_exc(limit=2)}"
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str, indent=1)
        # Loop breaker: the same tool failing the same way 3x in a row -> tell the model to change approach.
        sig = (name, text.splitlines()[0][:200]) if text.startswith(("ERROR", "DENIED")) else None
        self._repeat = self._repeat + 1 if sig and sig == getattr(self, "_last_sig", None) else (1 if sig else 0)
        self._last_sig = sig
        if self._repeat >= 3:
            text += ("\n\n(System: this exact error happened 3 times in a row. Stop repeating this call — change the "
                     "arguments, inspect first (e.g. app_inspect / browser_read), use a different tool, or explain "
                     "the problem to the user.)")
        policy.audit("tool_result", tool=name, chars=len(text), preview=text[:300])
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + f"\n...[truncated {len(text) - MAX_RESULT_CHARS} chars]"
        return text
