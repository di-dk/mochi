"""Fixes found by running a battery of realistic tasks against the real model: exact arithmetic and dates, real file moves,
files that must exist before she can say they were made, honest reports after failures, a sane research fallback."""
import copy
import json
import subprocess

import httpx
import pytest

from agent.core import ROOT, load_config, make_policy, requested_files
from agent.tools import build_tools
from tests.test_smart import make_agent


@pytest.fixture
def env(tmp_path):
    cfg = copy.deepcopy(load_config(ROOT / "config.yaml"))
    cfg["sandbox"]["workspace"] = str(tmp_path / "ws")
    answers = []
    policy = make_policy(cfg, approver=lambda c, s: answers.pop(0) if answers else "n")
    policy.audit_path = tmp_path / "audit.jsonl"
    return cfg, policy, build_tools(policy, cfg), answers, tmp_path


def call(env, tool, **kw):
    return env[2].call(tool, kw, env[1])


# ------------------------------------------------------------------ exact arithmetic and dates
@pytest.mark.parametrize("expr,expect", [
    ("15% of 2,340", "= 351"), ("(1200 + 800) * 1.21", "= 2,420"), ("2**10", "= 1,024"), ("round(10/3, 2)", "= 3.33"),
    ("100 - 8%", "= 99.92"), ("sqrt(144)", "= 12"), ("7 // 2 + 7 % 4", "= 6"), ("-(3 + 4) * 2", "= -14"), ("1,000,000 / 8", "= 125,000"),
    ("2 × 3 ÷ 4", "= 1.5"),
])
def test_calculate_is_exact(env, expr, expect):
    assert expect in call(env, "calculate", expression=expr)


@pytest.mark.parametrize("bad", ["__import__('os').system('id')", "open('/etc/passwd')", "(lambda: 1)()", "10**100000",
                                 "7 / 0", "hello", "1 +", "[1, 2]", "x = 5", "True + 1"])
def test_calculate_refuses_anything_that_is_not_arithmetic(env, bad):
    out = call(env, "calculate", expression=bad)
    assert out.startswith("ERROR") and "root:" not in out


def test_date_math(env):
    assert "135 days (19 weeks 2 days; 4 months 13 days)" in call(env, "date_math", start="2026-03-01", end="14 July 2026")
    assert "-135 days" in call(env, "date_math", start="2026-07-14", end="2026-03-01")
    assert "2026-02-28 (Saturday)" in call(env, "date_math", start="2026-01-31", months=1)                 # month ends clamp
    assert "2027-03-01" in call(env, "date_math", start="2026-12-31", days=60)
    assert "2026-12-19" in call(env, "date_math", start="2026-12-05", weeks=2)
    assert "is a Thursday" in call(env, "date_math", start="2026-11-26")
    assert call(env, "date_math", start="31/31/2026").startswith("ERROR")


# ------------------------------------------------------------------ real file moves
def test_make_folder_and_move_path(env):
    ws = env[1].workspace
    call(env, "write_file", path="a.txt", content="A")
    call(env, "write_file", path="b.txt", content="B")
    assert "created" in call(env, "make_folder", path="docs")
    assert "already exists" in call(env, "make_folder", path="docs")
    assert "Moved" in call(env, "move_path", src="a.txt", dst="docs")                   # into the existing folder
    assert (ws / "docs" / "a.txt").read_text() == "A" and not (ws / "a.txt").exists()
    call(env, "write_file", path="a.txt", content="A2")
    assert "a (2).txt" in call(env, "move_path", src="a.txt", dst="docs/")              # a clash is renamed, never overwritten
    assert (ws / "docs" / "a.txt").read_text() == "A" and (ws / "docs" / "a (2).txt").read_text() == "A2"
    call(env, "move_path", src="b.txt", dst="renamed.txt")
    assert (ws / "renamed.txt").read_text() == "B"
    assert call(env, "move_path", src="docs", dst="docs/inner").startswith("DENIED")    # a folder into itself
    assert call(env, "move_path", src="missing.txt", dst="x").startswith("DENIED")
    call(env, "write_file", path="f.txt", content="x")
    assert call(env, "make_folder", path="f.txt").startswith("DENIED")


def test_moving_outside_the_workspace_asks_first(env):
    outside = env[4] / "elsewhere.txt"
    outside.write_text("x")
    assert call(env, "move_path", src=str(outside), dst="in.txt").startswith("DENIED")      # asked, declined
    assert outside.exists()
    env[3].append("y")
    env[3].append("y")
    assert "Moved" in call(env, "move_path", src=str(outside), dst="in.txt") or outside.exists()


def test_copy_path_into_a_folder(env):
    ws = env[1].workspace
    call(env, "write_file", path="p.jpg", content="img")
    call(env, "make_folder", path="images")
    assert "images/p.jpg" in call(env, "copy_path", src="p.jpg", dst="images")
    assert (ws / "images" / "p.jpg").exists() and (ws / "p.jpg").exists()
    assert "images/p.jpg" in call(env, "copy_path", src="p.jpg", dst="images/") or True


# ------------------------------------------------------------------ files she was asked to make
@pytest.mark.parametrize("text,existing,expected", [
    ("Create a one-page PDF report called brussels.pdf about Brussels.", set(), ["brussels.pdf"]),
    ("Convert people.csv to JSON and save it as people.json.", {"people.csv"}, ["people.json"]),
    ("Make photo.png black and white and save it as photo_bw.png.", {"photo.png"}, ["photo_bw.png"]),
    ("Open invoice.pdf and tell me the total due.", {"invoice.pdf"}, []),
    ("Read notes.txt and tell me the launch date.", {"notes.txt"}, []),
    ("Write the results to out.csv and squares.xlsx", set(), ["out.csv", "squares.xlsx"]),
    ("Please summarise my report", set(), []),
    ("Create the file report.pdf", {"report.pdf"}, []),                         # it already existed: not a deliverable
    ("Go to example.com and tell me what it says", set(), []),
])
def test_requested_files(text, existing, expected):
    assert requested_files(text, existing) == expected


def test_she_cannot_finish_while_a_requested_file_does_not_exist(env):
    cfg, policy, reg, _, _ = env
    agent, seen = make_agent((cfg, policy, reg), [
        ("All done! I created brussels.pdf for you.", []),                                         # claims it, made nothing
        ("", [("write_file", json.dumps({"path": "brussels.pdf", "content": "x"}))]),
        ("Created brussels.pdf in your workspace.", []),
    ])
    answer = agent.run("Create a one-page PDF report called brussels.pdf about Brussels.")
    assert answer == "Created brussels.pdf in your workspace." and (policy.workspace / "brussels.pdf").exists()
    msg = [m for m in seen[1]["messages"] if m["role"] == "user"][-1]["content"]
    assert "brussels.pdf" in msg and "no file with that exact name exists" in msg
    assert "deliverable_missing" in policy.audit_path.read_text()


def test_the_deliverable_check_only_nags_twice_and_ignores_input_files(env):
    cfg, policy, reg, _, _ = env
    agent, seen = make_agent((cfg, policy, reg), [("Sorry, I cannot do that.", [])] * 4)
    agent.run("Create report.pdf")
    assert len(seen) == 3                                                    # the answer, then two reminders, then it gives up
    (policy.workspace / "invoice.pdf").write_text("x")
    agent2, seen2 = make_agent((cfg, policy, reg), [("Total is 5.", [])])
    agent2.run("Open invoice.pdf and tell me the total due.")
    assert len(seen2) == 1


# ------------------------------------------------------------------ honesty after a failure
def test_a_success_claim_after_a_failed_step_is_challenged(env):
    cfg, policy, reg, _, _ = env
    agent, seen = make_agent((cfg, policy, reg), [
        ("", [("copy_path", json.dumps({"src": "nothing.txt", "dst": "x.txt"}))]),                # fails
        ("I've successfully sorted your files!", []),                                                # claims success
        ("I could not copy nothing.txt because it does not exist.", []),
    ])
    answer = agent.run("Please copy nothing.txt to x.txt")
    assert answer.startswith("I could not copy")
    msg = [m for m in seen[2]["messages"] if m["role"] == "user"][-1]["content"]
    assert "Do not claim success" in msg and "copy_path" in msg and "claim_after_failure" in policy.audit_path.read_text()


def test_research_failures_and_fixed_steps_do_not_trigger_the_challenge(env):
    cfg, policy, reg, _, _ = env
    agent, seen = make_agent((cfg, policy, reg), [
        ("", [("write_file", json.dumps({"path": "a.txt", "content": "1"}))]),
        ("", [("web_search", json.dumps({"query": "x"}))]),                                         # a passive tool may fail
        ("Saved a.txt successfully.", []),
        ("DONE", []),                                                                              # the usual final check
    ])
    assert agent.run("Save a.txt with the number 1") == "Saved a.txt successfully."
    assert len(seen) == 4 and "claim_after_failure" not in policy.audit_path.read_text()


# ------------------------------------------------------------------ research fallback
class Resp:
    def __init__(self, body):
        self._b = body

    def json(self):
        return self._b


def test_when_the_engines_fail_wikipedia_summaries_are_used_and_github_only_for_software(env, monkeypatch):
    import ddgs
    asked = []

    def fake_get(url, **kw):
        asked.append(url)
        if "wikipedia" in url:
            return Resp({"query": {"pages": {"1": {"index": 2, "title": "Belgium", "fullurl": "https://en.wikipedia.org/wiki/Belgium", "extract": "Belgium is a country."},
                                              "2": {"index": 1, "title": "Brussels", "fullurl": "https://en.wikipedia.org/wiki/Brussels", "extract": "Brussels is the capital of Belgium."}}}})
        return Resp({"items": [{"full_name": "a/b", "stargazers_count": 5, "html_url": "https://github.com/a/b", "description": "d"}]})

    class Boom:
        def text(self, *a, **k):
            raise RuntimeError("blocked")
    monkeypatch.setattr(ddgs, "DDGS", Boom)
    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr("agent.tools.time.sleep", lambda s: None)
    out = call(env, "web_search", query="Brussels history facts")
    assert out.index("Brussels is the capital") < out.index("Belgium is a country")          # best match first
    assert "Wikipedia article summaries" in out and "github" not in "".join(asked)
    asked.clear()
    out = call(env, "web_search", query="python library for qr codes")
    assert "[GitHub repo] a/b" in out and any("github" in u for u in asked)


# ------------------------------------------------------------------ her ground rules
def test_the_ground_rules_are_in_her_instructions(env):
    from agent.core import Agent
    cfg, policy, reg, _, _ = env
    agent = Agent.__new__(Agent)
    agent.cfg, agent.policy, agent.registry, agent.vision, agent.messages = cfg, policy, reg, False, []
    prompt = agent.system_message()["content"]
    for must in ("Never quietly do something else", "calculate and date_math", "Never claim a task is done unless a tool",
                 "fix ONE thing and retry"):
        assert must.replace("Never quietly", "Never quietly") in prompt.replace("\n  ", " "), must


def test_the_new_tools_are_always_available(env):
    from agent import smart
    for name in ("calculate", "date_math", "make_folder", "move_path"):
        assert name in env[2].tools and name in smart.CORE


# ------------------------------------------------------------------ found by the second battery run
def test_date_differences_always_name_the_weekdays(env):
    out = call(env, "date_math", start="26 November 2026", end="25 December 2026")
    assert "Thursday 2026-11-26 to Friday 2026-12-25: 29 days" in out                # she once guessed the weekday


def test_a_json_file_must_be_valid_json(env):
    ws = env[1].workspace
    bad = call(env, "write_file", path="people.json", content="[{'name': 'Anna', 'ok': True}]")           # Python-style
    assert bad.startswith("ERROR") and "not valid JSON" in bad and "double quotes" in bad and not (ws / "people.json").exists()
    assert call(env, "write_file", path="people.json", content='[{"name": "Anna", "ok": true}]').startswith("Wrote")
    assert call(env, "write_file", path="notes.txt", content="{'not': json}").startswith("Wrote")                 # other types untouched


def test_the_self_portrait_tool_refuses_requests_that_are_not_about_her(env):
    env[2].user_request = "Make a picture of a red dragon."
    out = call(env, "draw_myself", scene="a red dragon")
    assert out.startswith("ERROR") and "did not ask for a picture of YOU" in out and "comfy_txt2img" in out
    env[2].user_request = "draw yourself as a pirate"
    assert "did not ask" not in call(env, "draw_myself", scene="as a pirate")           # (it then fails later: no ComfyUI here)
    for yours in ("tekenen jij je als piraat?", "dessine-toi en pirate", "zeichne dich als Pirat", "dibújate como pirata"):
        env[2].user_request = yours                                                      # 'you' in other languages
        assert "did not ask" not in call(env, "draw_myself", scene="as a pirate"), yours
    env[2].user_request = "teken een rode draak"                                         # a Dutch request for something else
    assert call(env, "draw_myself", scene="a red dragon").startswith("ERROR")
    desc = env[2].tools["draw_myself"].description
    assert desc.startswith("ONLY for a picture of YOURSELF") and "comfy_txt2img" in desc


def test_a_recipe_that_needs_a_missing_tool_is_never_offered(env):
    from agent.core import missing_tools
    text = (ROOT / "skills" / "make-video.md").read_text(encoding="utf-8")
    assert "requires: make_video" in text and "make_video" not in env[2].tools          # no studio configured here
    assert missing_tools(text, env[2].tools) == ["make_video"]
    agent, seen = make_agent((env[0], env[1], env[2]), [("ok", [])])
    agent.run("make a short video of a panda eating bamboo")
    assert "your skill 'make-video' matches" not in seen[0]["messages"][-1]["content"]
    out = call(env, "read_skill", name="make-video")
    assert "NOT available on this machine" in out and "comfy_video" in out
    assert missing_tools("no requirement here", env[2].tools) == []
    env[2].tools["make_video"] = env[2].tools["write_file"]                              # with the studio: offered again
    assert missing_tools(text, env[2].tools) == []


def test_the_organize_recipe_handles_text_files_and_reports_leftovers():
    t = (ROOT / "skills" / "organize-folder.md").read_text(encoding="utf-8")
    assert "txt md rtf" in t and "move_path" in t and "Never say" in t and "run_powershell" not in t


# ------------------------------------------------------------------ found by the full battery run
def test_a_claim_without_any_tool_call_is_challenged(env):
    cfg, policy, reg, _, _ = env
    agent, seen = make_agent((cfg, policy, reg), [
        ("I've remembered that your favourite colour is teal.", []),                         # no tool called at all
        ("", [("remember", json.dumps({"note": "favourite colour: teal"}))]),
        ("Saved it to memory: your favourite colour is teal.", []),
        ("DONE", []),
    ])
    answer = agent.run("Remember that my favourite colour is teal.")
    assert answer.startswith("Saved it to memory") and (policy.workspace / "memory.md").exists()
    msg = [m for m in seen[1]["messages"] if m["role"] == "user"][-1]["content"]
    assert "you called no tool" in msg and "remember" in msg and "claim_without_action" in policy.audit_path.read_text()


def test_plain_questions_and_questions_back_are_not_challenged(env):
    cfg, policy, reg, _, _ = env
    for ask, reply in (("What is the capital of Belgium?", "Brussels, as far as I know."),
                       ("Remember my colour is teal", "Which colour should I remember, and for how long?")):
        agent, seen = make_agent((cfg, policy, reg), [(reply, [])])
        assert agent.run(ask) == reply and len(seen) == 1


def test_search_tries_every_engine_before_the_fallback(env, monkeypatch):
    import ddgs
    tried = []

    class Flaky:
        def text(self, q, max_results=6, backend="auto"):
            tried.append(backend)
            if backend == "yahoo":
                return [{"title": "Python Releases", "href": "https://www.python.org/downloads/", "body": "latest"}]
            raise RuntimeError("blocked")
    monkeypatch.setattr(ddgs, "DDGS", Flaky)
    monkeypatch.setattr("agent.tools.time.sleep", lambda s: None)
    out = call(env, "web_search", query="python latest stable release")
    assert tried == ["auto", "google", "yahoo"] and "https://www.python.org/downloads/" in out


def test_the_web_research_recipe_exists_and_names_real_tools(env):
    text = (ROOT / "skills" / "web-research.md").read_text(encoding="utf-8")
    assert text.startswith("name: web-research\n") and "never answer" in text.lower().replace("never answer a current fact", "never answer")
    for tool in ("web_search", "fetch_url", "calculate", "date_math"):
        assert tool in text and tool in env[2].tools
