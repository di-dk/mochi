"""Offline checks on the built-in skill recipes: format, size, and that they only name real tools."""
import re
from pathlib import Path

from agent.tools_extra import BUILTIN_SKILLS, parse_skill, skills_index

FILES = sorted(BUILTIN_SKILLS.glob("*.md"))
# Tools of other agents that must never leak into a Mochi recipe.
FOREIGN = re.compile(r"\b(web_extract|delegate_task|skill_view|execute_code|cronjob|terminal\()", re.I)


def test_builtin_skills_fit_the_index():
    assert len(FILES) <= 48, "skills_index only lists the first 48 skills to the model"
    listed = skills_index(Path("no-such-workspace"))
    for f in FILES:
        assert f"- {f.stem}:" in listed


def test_builtin_skill_format():
    for f in FILES:
        lines = f.read_text(encoding="utf-8").splitlines()
        assert lines[0] == f"name: {f.stem}", f.name
        assert lines[1].startswith("description: ") and len(lines[1]) <= 125, f.name
        assert lines[2] == "", f.name
        s = parse_skill(f)
        assert s["name"] == f.stem and s["description"] and s["builtin"]
        assert len(s["text"]) <= 3500, f"{f.name} is too long for a small model"
        assert not FOREIGN.search(s["text"]), f"{f.name} names a tool Mochi does not have"
