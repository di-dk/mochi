"""Offline tests: tool groups, skill auto-matching, chunked trimming, streaming, live steering/stop, final check."""
import threading
from types import SimpleNamespace as NS

import pytest

from agent import smart
from agent.core import STOPPED, Agent, load_config, make_policy
from agent.tools import build_tools
from agent.tools_extra import all_skills


@pytest.fixture
def env(tmp_path):
    cfg = load_config()
    cfg["sandbox"]["workspace"] = str(tmp_path / "ws")
    cfg["video"] = {}
    policy = make_policy(cfg, approver=lambda c, s: "n")
    policy.audit_path = tmp_path / "audit.jsonl"
    return cfg, policy, build_tools(policy, cfg)


def make_agent(env, replies, events=None):
    """An Agent whose model is a script: each entry is (text, [(tool, json_args), ...])."""
    cfg, policy, reg = env
    seen = []

    class Client:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    seen.append({**kw, "messages": [dict(m) for m in kw["messages"]]})
                    text, calls = replies.pop(0)
                    tcs = [NS(id=f"c{len(seen)}_{i}", function=NS(name=n, arguments=a))
                           for i, (n, a) in enumerate(calls)]
                    return NS(choices=[NS(message=NS(content=text, tool_calls=tcs or None))])

    agent = Agent.__new__(Agent)
    agent.cfg, agent.policy, agent.registry, agent.vision = cfg, policy, reg, False
    agent.client = Client
    agent.on_event = (lambda k, d: events.append((k, d))) if events is not None else (lambda k, d: None)
    agent.messages = [{"role": "system", "content": "s"}]
    return agent, seen


def names(kw):
    return {t["function"]["name"] for t in kw["tools"]}


# ---------------------------------------------------------------- tool groups
def test_every_tool_is_core_or_grouped(env):
    reg = env[2]
    grouped = set().union(*smart.GROUPS.values())
    assert not (grouped & smart.CORE)
    unknown = set(reg.tools) - grouped - smart.CORE - {"make_video", "list_my_videos"}
    assert not unknown, f"new tools need a group in agent/smart.py (or CORE): {unknown}"


def test_only_needed_tool_groups_are_sent(env):
    reg = env[2]
    core = {t["function"]["name"] for t in reg.schemas(auto=True)}
    assert {"read_file", "web_search", "use_tools", "read_skill"} <= core
    assert not core & {"run_python", "browser_open", "create_pdf", "comfy_txt2img", "schedule_task", "app_click"}
    assert len(core) < len(reg.schemas()) / 2
    agent, seen = make_agent(env, [("hi", [])])
    agent.run("please make a pdf report about bees")
    assert "create_pdf" in names(seen[0]) and "comfy_txt2img" not in names(seen[0])


def test_use_tools_and_auto_load_on_call(env):
    cfg, policy, reg = env
    out = reg.call("use_tools", {"groups": ["media", "nope"]}, policy)
    assert "Loaded media" in out and "Unknown group" in out and "media" in reg.enabled_groups
    assert "system" not in reg.enabled_groups
    reg.call("system_info", {}, policy)                  # calling a tool that was not loaded loads its group
    assert "system" in reg.enabled_groups


def test_groups_all_sends_everything(env):
    env[0]["tools"] = {"groups": "all"}
    agent, seen = make_agent(env, [("hi", [])])
    agent.run("hello there")
    assert len(seen[0]["tools"]) == len(env[2].tools)


# ---------------------------------------------------------------- skill auto-match
@pytest.mark.parametrize("request_text, skill", [
    ("find recent arxiv papers about diffusion models", "arxiv-papers"),
    ("turn these meeting notes into action items", "meeting-action-items"),
    ("make me flashcards to review spanish verbs", "flashcards"),
    ("research solar panels and make a sourced pdf report", "pdf-report"),
    ("what is the stock price of that ticker", "stocks"),
])
def test_skill_is_matched(env, request_text, skill):
    got = smart.match_skill(request_text, all_skills(env[1].workspace))
    assert got and got["name"] == skill


@pytest.mark.parametrize("request_text", ["hi mochi", "how are you today?", "thanks, that is great", "what time is it"])
def test_small_talk_matches_no_skill(env, request_text):
    assert smart.match_skill(request_text, all_skills(env[1].workspace)) is None


def test_matched_skill_is_handed_over_with_its_tools(env):
    events = []
    agent, seen = make_agent(env, [("ok", [])], events)
    agent.run("find recent arxiv papers about diffusion models")
    user = seen[0]["messages"][-1]["content"]
    assert "your skill 'arxiv-papers' matches" in user and "export.arxiv.org" in user
    assert ("skill", {"name": "arxiv-papers"}) in events
    assert "http_request" in names(seen[0])              # the recipe names it, so its group is loaded


# ---------------------------------------------------------------- context
def test_trim_waits_then_cuts_in_one_chunk(env):
    cfg = env[0]
    cfg["llm"]["context_length"] = 1500                  # budget = 4800 chars
    cfg["context"] = {"condense": False}
    agent, _ = make_agent(env, [])
    for i in range(3):
        agent.messages += [{"role": "user", "content": f"q{i}"},
                           {"role": "assistant", "content": "", "tool_calls": [
                               {"id": f"t{i}", "type": "function", "function": {"name": "fetch_url", "arguments": "{}"}}]},
                           {"role": "tool", "tool_call_id": f"t{i}", "content": "x" * 700},
                           {"role": "assistant", "content": "a" * 100}]
    before = [dict(m) for m in agent.messages]
    agent._trim()
    assert agent.messages == before                      # under budget: nothing is touched (cache stays valid)
    agent.messages += [{"role": "user", "content": "q9"}, {"role": "tool", "tool_call_id": "z", "content": "y" * 1800}]
    agent._trim()
    size = sum(len(str(m)) for m in agent.messages)
    assert size < 4800 * 0.75 and agent.messages[0]["content"] == "s"
    assert agent.messages[-1]["content"] == "y" * 1800    # the newest result is kept whole


def test_condense_replaces_old_results_and_falls_back(env):
    cfg = env[0]
    cfg["llm"]["context_length"] = 1000
    agent, seen = make_agent(env, [("- bees: 42 hives, source https://x.test", [])])
    agent.messages += [{"role": "user", "content": "q"},
                       {"role": "assistant", "content": "", "tool_calls": [
                           {"id": "t1", "type": "function", "function": {"name": "fetch_url", "arguments": "{}"}}]},
                       {"role": "tool", "tool_call_id": "t1", "content": "long page " * 400}]
    agent.messages += [{"role": "assistant", "content": "n"}] * 7
    agent._trim("count the hives")
    tool = next(m for m in agent.messages if m["role"] == "tool")
    assert tool["content"].startswith("[condensed from 4000 chars") and "42 hives" in tool["content"]
    assert "count the hives" in seen[0]["messages"][0]["content"] and "`fetch_url`" in seen[0]["messages"][0]["content"]
    assert smart.condense(NS(chat=NS(completions=NS(create=lambda **k: 1 / 0))), "m", "t", "x", "abc" * 900) is None


# ---------------------------------------------------------------- streaming
def chunk(content=None, calls=None):
    return NS(choices=[NS(delta=NS(content=content, tool_calls=calls))])


def test_streamed_reply_is_assembled(env):
    agent, _ = make_agent(env, [])
    stream = [chunk("Let me "), chunk("look."),
              chunk(calls=[NS(index=0, id="a1", function=NS(name="read_file", arguments='{"pa'))]),
              chunk(calls=[NS(index=0, id=None, function=NS(name=None, arguments='th": "x.txt"}'))]),
              chunk(calls=[NS(index=1, id=None, function=NS(name="wait", arguments='{"seconds": 1}'))]),
              NS(choices=[])]
    agent.client = NS(chat=NS(completions=NS(create=lambda **kw: iter(stream))))
    text, calls = agent._complete({})
    assert text == "Let me look."
    assert calls[0] == {"id": "a1", "name": "read_file", "arguments": '{"path": "x.txt"}'}
    assert calls[1]["name"] == "wait" and calls[1]["id"]             # a missing id gets one


def test_stop_cuts_a_streaming_reply(env):
    agent, _ = make_agent(env, [])

    def slow_stream(**kw):
        yield chunk("thinking ")
        agent.stop.set()                                  # the user types /stop while she is writing
        yield chunk("more")
        raise AssertionError("the stream should have been abandoned")

    agent.client = NS(chat=NS(completions=NS(create=slow_stream)))
    assert agent.run("write me a very long essay") == STOPPED
    assert agent.messages[-1]["role"] == "user"           # the half-written reply is not kept


# ---------------------------------------------------------------- steering while busy
def test_message_sent_while_busy_reaches_the_next_step(env):
    cfg = env[0]
    cfg["agent"]["final_check"] = False
    events = []
    agent, seen = make_agent(env, [("", [("wait", '{"seconds": 0}')]), ("done, in French", [])], events)
    agent.registry.tools["wait"].fn = lambda seconds=0: agent.inbox.put("answer in French please") or "waited"
    assert agent.run("say hello") == "done, in French"
    second_call = seen[1]["messages"]
    assert second_call[-1]["role"] == "user" and "answer in French please" in second_call[-1]["content"]
    assert second_call[-2]["role"] == "tool"              # inserted after the tool results, never between them
    assert any(k == "steer" for k, _ in events)


def test_message_arriving_during_the_final_answer_is_not_lost(env):
    cfg = env[0]
    cfg["agent"]["final_check"] = False
    agent, seen = make_agent(env, [("first answer", []), ("revised answer", [])])
    real = agent._complete

    def complete(kwargs, quiet=False):
        out = real(kwargs, quiet)
        if len(seen) == 1:
            agent.inbox.put("also mention the price")
        return out

    agent._complete = complete
    assert agent.run("describe the product") == "revised answer"
    assert len(seen) == 2 and "also mention the price" in seen[1]["messages"][-1]["content"]


def test_stop_between_steps(env):
    agent, seen = make_agent(env, [("", [("wait", '{"seconds": 0}')]), ("never reached", [])])
    agent.registry.tools["wait"].fn = lambda seconds=0: agent.stop.set() or "waited"
    assert agent.run("do a long job") == STOPPED and len(seen) == 1
    agent2, _ = make_agent(env, [("hello again", [])])
    assert agent2.run("hi") == "hello again"              # a fresh run starts un-stopped
    assert isinstance(agent.stop, threading.Event)


# ---------------------------------------------------------------- final check
TWO_TOOLS = ("", [("wait", '{"seconds": 0}'), ("wait", '{"seconds": 0}')])


def test_final_check_done_returns_the_answer_and_cleans_up(env):
    events = []
    agent, seen = make_agent(env, [TWO_TOOLS, ("Here is the result.", []), ("DONE", [])], events)
    assert agent.run("do the thing") == "Here is the result."
    assert "System check before finishing" in seen[2]["messages"][-1]["content"]
    assert agent.messages[-1] == {"role": "assistant", "content": "Here is the result."}
    assert any(k == "check" for k, _ in events)


def test_final_check_can_trigger_a_fix(env):
    agent, seen = make_agent(env, [TWO_TOOLS, ("All done.", []), ("", [("wait", '{"seconds": 0}')]),
                                   ("Now it is really done.", [])])
    assert agent.run("do the thing") == "Now it is really done."
    assert len(seen) == 4                                 # only one check per task


def test_no_final_check_for_plain_chat(env):
    agent, seen = make_agent(env, [("Hello!", [])])
    assert agent.run("hi") == "Hello!" and len(seen) == 1


# ---------------------------------------------------------------- keyboard routing (cli)
def test_typed_lines_go_to_the_right_place(env):
    from agent.cli import Keyboard
    kb = Keyboard()                                       # under pytest stdin is closed: the reader thread ends
    agent, _ = make_agent(env, [])
    kb.agent = agent
    kb.route("hello")                                     # idle: a new command
    assert "hello" in list(kb.commands.queue)
    kb.busy = True
    kb.route("use metric units")                          # busy: handed to the running task
    kb.route("")
    assert agent.inbox.get_nowait() == "use metric units" and agent.inbox.empty()
    assert not agent.stop.is_set()
    kb.route("/stop")
    assert agent.stop.is_set() and agent.inbox.empty()
    kb.asking = True
    kb.route("y")                                         # an open approval question wins over everything
    assert "y" in list(kb.answers.queue) and agent.inbox.empty()


def test_approval_prompt_shows_every_answer_letter(capsys):
    """Rich eats unescaped [y] / [n] / [a] as style tags, which once printed 'es / o / lways'."""
    import queue as q
    from agent import cli
    cli.console.file = None            # use the real stdout so capsys sees it
    kb = cli.Keyboard.__new__(cli.Keyboard)
    kb.answers = q.Queue(); kb.answers.put("y"); kb.asking = False
    assert kb.approve("write", "Write a file") == "y"
    out = capsys.readouterr().out
    assert "[y]es" in out and "[n]o" in out and "[a]lways" in out
