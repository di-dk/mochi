"""A small model copies example sentences from its own instructions (a cat video when asked for a panda, a fake lesson, a stale
date). Examples are gone from tool descriptions and recipes, a lint keeps them out, a guard refuses a call that pastes one, and
the creative tools check that the prompt is about what the user asked for."""
import re
from types import SimpleNamespace

import pytest

from agent.core import ROOT, load_config, make_policy
from agent.registry import QUOTED, Registry, parroted
from agent.tools import build_tools
from tests.test_comfy_expert import env, call  # noqa: F401  (a fake ComfyUI and Ollama)


def tool(desc):
    return SimpleNamespace(description=desc)


def test_the_guard_catches_a_pasted_example_but_not_ordinary_text():
    t = tool("Make a picture. prompt: one sentence, e.g. 'A friendly robot waves hello to everyone at the park'. Short: 'a cat'.")
    assert parroted(t, {"prompt": "A friendly robot waves hello to everyone at the park"})
    assert parroted(t, {"prompt": "a friendly ROBOT waves hello, to everyone at the park!!"})            # case and punctuation
    assert parroted(t, {"prompt": "Scene: A friendly robot waves hello to everyone at the park, at night"})   # inside longer text
    assert not parroted(t, {"prompt": "A panda doing kung fu in a bamboo forest"})
    assert not parroted(t, {"prompt": "a cat"})                                                              # short quotes are ignored
    assert not parroted(tool("no examples here"), {"prompt": "anything at all"})
    assert not parroted(t, {"n": 3, "ok": True})


def test_the_registry_refuses_a_parroted_call_and_runs_a_normal_one(tmp_path):
    cfg = load_config(ROOT / "config.yaml")
    cfg["sandbox"]["workspace"] = str(tmp_path / "ws")
    pol = make_policy(cfg, approver=None)
    pol.audit_path = tmp_path / "a.jsonl"
    reg, ran = Registry(), []
    reg.add("paint", "Paint it. For example 'A friendly robot waves hello to everyone at the park' is the style.",
            {"prompt": {"type": "string"}}, ["prompt"])(lambda prompt: ran.append(prompt) or "painted")
    out = reg.call("paint", {"prompt": "A friendly robot waves hello to everyone at the park"}, pol)
    assert out.startswith("ERROR") and "example text from my own instructions" in out and ran == []
    assert "parroted_example" in pol.audit_path.read_text()
    assert reg.call("paint", {"prompt": "a panda"}, pol) == "painted" and ran == ["a panda"]


def test_no_tool_description_contains_an_example_sentence_she_could_paste():
    cfg = load_config(ROOT / "config.yaml")
    import tempfile
    from pathlib import Path
    cfg["sandbox"]["workspace"] = str(Path(tempfile.mkdtemp()) / "ws")
    pol = make_policy(cfg, approver=None)
    pol.audit_path = Path(tempfile.mkdtemp()) / "a.jsonl"
    bad = {t.name: q for t in build_tools(pol, cfg).tools.values()
           for q in QUOTED.findall(t.description) if len(q.split()) >= 6 and "<" not in q}
    assert not bad, f"these tool descriptions contain a quoted example sentence: {bad}"


@pytest.mark.parametrize("name", sorted(p.stem for p in (ROOT / "skills").glob("*.md")
                                        if p.stem.startswith("comfy") or p.stem in ("about-mochi", "learn-new-skill")))
def test_the_creative_recipes_have_no_sample_prompt_to_copy(name):
    text = (ROOT / "skills" / f"{name}.md").read_text(encoding="utf-8")
    long_quotes = [q for q in re.findall(r'"([^"\n]{45,})"', text) if len(q.split()) >= 7 and "<" not in q]
    assert not long_quotes, f"{name} has a quoted sample sentence a small model will copy: {long_quotes}"


def test_the_example_dates_and_paths_are_gone():
    import agent.tools_more as tm
    src = (ROOT / "agent" / "tools_more.py").read_text(encoding="utf-8")
    assert "Give 2026-11-26" not in src and "YYYY-MM-DD" in src
    assert "cat.png" not in (ROOT / "agent" / "tools.py").read_text(encoding="utf-8")
    assert "winter coat" not in (ROOT / "agent" / "tools_auto.py").read_text(encoding="utf-8").split("def draw_myself")[0][-900:]


# ------------------------------------------------------------------ the prompt must be about the user's request
def run_tool(env, request, tool_name, **args):
    env[2].user_request, env[2].off_topic_seen = request, set()
    return call(env, tool_name, **args)


def test_a_cat_prompt_for_a_panda_request_is_stopped_once(env):                       # the transcript
    req = "make a video of kung fu panda"
    cat = "A cute orange cat dancing on its hind legs in a cozy living room, smooth motion, warm light."
    out = run_tool(env, req, "comfy_video", prompt=cat)
    assert out.startswith("ERROR") and "nothing to do with what the user asked" in out and "kung fu panda" in out
    assert env[3].jobs == []                                                           # no GPU time was wasted
    good = call(env, "comfy_video", prompt="A panda practising kung fu kicks in a bamboo forest, smooth motion")
    assert "Made a" in good and len(env[3].jobs) == 1


def test_an_identical_repeat_is_let_through_in_case_the_user_said_that_one(env):
    req = "make a video of the thing we talked about, panda"
    assert run_tool(env, req, "comfy_video", prompt="A dog running on a beach").startswith("ERROR")
    assert "Made a" in call(env, "comfy_video", prompt="A dog running on a beach")


@pytest.mark.parametrize("request_text", ["नमस्ते, एउटा भिडियो बनाउनुहोस् पाण्डा को", "make a video", "make a video of that", ""])
def test_requests_that_cannot_be_judged_are_not_blocked(env, request_text):
    assert "Made a" in run_tool(env, request_text, "comfy_video", prompt="A dog running on a beach")


def test_pictures_are_checked_too_but_her_own_internal_calls_are_not(env):
    out = run_tool(env, "draw a red dragon", "comfy_txt2img", prompt="a blue cat sitting on a sofa")
    assert out.startswith("ERROR") and "red dragon" in out


def test_each_request_starts_with_a_clean_slate(env):
    from tests.test_smart import make_agent
    agent, _ = make_agent((env[0], env[1], env[2]), [("ok", [])])
    env[2].off_topic_seen = {"stale prompt"}
    agent.run("make a video of kung fu panda")
    assert env[2].user_request == "make a video of kung fu panda" and env[2].off_topic_seen == set()
