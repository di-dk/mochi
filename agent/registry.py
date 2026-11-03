"""Tool registry: functions + JSON schemas exposed to the model."""
from __future__ import annotations

import json
import traceback
from dataclasses import dataclass
from typing import Any, Callable

from .policy import Denied

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

    def add(self, name: str, description: str, properties: dict, required: list[str] | None = None):
        def deco(fn):
            self.tools[name] = Tool(name, description,
                                    {"type": "object", "properties": properties,
                                     "required": required or []}, fn)
            return fn
        return deco

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self.tools.values()]

    def call(self, name: str, raw_args: str | dict, policy) -> str:
        tool = self.tools.get(name)
        if tool is None:
            return f"ERROR: unknown tool '{name}'. Available: {', '.join(self.tools)}"
        try:
            args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args or "{}")
        except json.JSONDecodeError as e:
            return f"ERROR: tool arguments were not valid JSON ({e}). Retry with valid JSON."
        policy.audit("tool_call", tool=name, args=args)
        try:
            result = tool.fn(**args)
        except Denied as e:
            result = f"DENIED: {e}"
        except TypeError as e:
            result = f"ERROR: bad arguments for {name}: {e}"
        except Exception as e:  # tool failures go back to the model so it can recover
            result = f"ERROR: {type(e).__name__}: {e}\n{traceback.format_exc(limit=2)}"
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str, indent=1)
        policy.audit("tool_result", tool=name, chars=len(text), preview=text[:300])
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + f"\n...[truncated {len(text) - MAX_RESULT_CHARS} chars]"
        return text
