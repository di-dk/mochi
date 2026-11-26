"""Mochi as a ComfyUI expert: pre-flight checks, one-call video, GPU memory, recovery, starting ComfyUI. A fake ComfyUI
(and a fake Ollama) stand in for the real servers; one opt-in test runs against the real ComfyUI."""
import copy
import json
import os
import subprocess

import httpx
import pytest

from agent.core import ROOT, load_config, make_policy
from agent.tools import build_tools

MODEL_KEYS = {"unet_name", "lora_name", "clip_name", "vae_name", "ckpt_name"}
TEMPLATES = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "workflows").glob("*.json")}


class Resp:
    def __init__(self, body=None, status=200, content=b""):
        self._b, self.status_code, self.content = body, status, content
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        return self._b

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("x", request=None, response=None)


class FakeServers:
    """ComfyUI on :8188 and Ollama on :11434."""

    def __init__(self):
        self.up, self.missing_models, self.missing_nodes = True, set(), set()
        self.jobs, self.unloaded, self.posts, self.outcomes = [], [], [], []   # outcomes: per job "ok" or an error text
        self.loaded_llm = ["qwen3:14b"]

    def info(self):
        out = {}
        for wf in TEMPLATES.values():
            for node in (v for k, v in wf.items() if not k.startswith("_")):
                ct = node["class_type"]
                if ct in self.missing_nodes:
                    continue
                spec = out.setdefault(ct, {"input": {"required": {}, "optional": {}}})
                for k, v in node["inputs"].items():
                    if k in MODEL_KEYS and isinstance(v, str):
                        opts = spec["input"]["required"].setdefault(k, [[]])[0]
                        if v not in self.missing_models and v not in opts:
                            opts.append(v)
                    else:
                        spec["input"]["required"].setdefault(k, ["INT" if isinstance(v, (int, float)) else "STRING"])
        return out

    def get(self, url, **kw):
        if url.startswith("http://localhost:11434/api/ps"):
            return Resp({"models": [{"name": n} for n in self.loaded_llm]})
        if not url.startswith("http://127.0.0.1:8188"):
            raise httpx.ConnectError("unexpected " + url)
        if not self.up:
            raise httpx.ConnectError("down")
        path = url.split("8188", 1)[1]
        if path == "/system_stats":
            return Resp({"system": {"comfyui_version": "9"}, "devices": [{"name": "GPU", "vram_free": 8 * 2**30}]})
        if path == "/queue":
            return Resp({"queue_running": [], "queue_pending": []})
        if path == "/object_info":
            return Resp(self.info())
        if path.startswith("/object_info/"):
            n = path.split("/")[-1]
            return Resp({n: self.info()[n]} if n in self.info() else {})
        if path.startswith("/history/"):
            outcome = self.outcomes.pop(0) if self.outcomes else "ok"
            if outcome != "ok":
                return Resp({"p1": {"status": {"status_str": "error", "messages": [
                    ["execution_error", {"node_type": "KSamplerAdvanced", "exception_message": outcome}]]}}})
            return Resp({"p1": {"status": {"status_str": "success"}, "outputs": {"15": {"images": [
                {"filename": "out_00001_.webm", "subfolder": "", "type": "output"}]}}}})
        if path.startswith("/view"):
            return Resp(content=b"WEBMDATA")
        raise AssertionError("unexpected GET " + url)

    def post(self, url, **kw):
        self.posts.append((url, kw))
        if url.startswith("http://localhost:11434/api/generate"):
            self.unloaded.append(kw["json"]["model"])
            assert kw["json"]["keep_alive"] == 0
            return Resp({})
        if not self.up:
            raise httpx.ConnectError("down")
        if url.endswith("/prompt"):
            self.jobs.append(kw["json"]["prompt"])
            if self.jobs and getattr(self, "reject", None):
                return Resp(self.reject, status=400)
            return Resp({"prompt_id": "p1"})
        if url.endswith("/upload/image"):
            return Resp({"name": "uploaded.png"})
        return Resp({})                                           # /free


@pytest.fixture
def env(tmp_path, monkeypatch):
    srv = FakeServers()
    monkeypatch.setattr(httpx, "get", srv.get)
    monkeypatch.setattr(httpx, "post", srv.post)
    cfg = copy.deepcopy(load_config(ROOT / "config.yaml"))
    cfg["sandbox"]["workspace"] = str(tmp_path / "ws")
    cfg["llm"]["base_url"] = "http://localhost:11434/v1"
    asked = []
    policy = make_policy(cfg, approver=lambda c, s: (asked.append((c, s)), "y")[1])
    policy.audit_path = tmp_path / "audit.jsonl"
    reg = build_tools(policy, cfg)
    return cfg, policy, reg, srv, asked, tmp_path


def call(env, tool, **kw):
    return env[2].call(tool, kw, env[1])


# ------------------------------------------------------------------ pre-flight
def test_every_shipped_template_validates_against_what_is_installed(env):
    out = call(env, "comfy_check")
    assert out.count("OK      ") == len(TEMPLATES) >= 3 and "BROKEN" not in out


def test_a_missing_model_or_node_is_found_before_running(env):
    env[3].missing_models = {"wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors"}
    out = call(env, "comfy_check", template="wan-text-to-video")
    assert out.startswith("BROKEN") and "wan2.2_t2v_high_noise" in out and "not installed" in out
    assert "OK      wan-image-to-video" in call(env, "comfy_check", template="wan-image-to-video")
    env[3].missing_models, env[3].missing_nodes = set(), {"EmptyHunyuanLatentVideo"}
    assert "no node type 'EmptyHunyuanLatentVideo'" in call(env, "comfy_check", template="wan-text-to-video")


def test_capabilities_say_ready_only_when_the_template_really_runs(env):
    out = call(env, "comfy_capabilities")
    srv = env[3]
    assert "ComfyUI 9 up" in out                                   # (the fake's status line)
    srv_unets = srv.info()["UNETLoader"]["input"]["required"]["unet_name"][0]
    assert any("wan2.2_t2v" in u for u in srv_unets)
    ready = out.split("INSTALLED")[0]
    assert "Text to video" in ready and "comfy_video prompt=" in ready and "Edit a picture" in ready
    srv.missing_models = {"wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors"}
    out2 = call(env, "comfy_capabilities")
    assert "BROKEN, template wan-text-to-video cannot run here" in out2.split("INSTALLED")[1]
    assert "Text to video" not in out2.split("INSTALLED")[0]


# ------------------------------------------------------------------ one-call video
def test_comfy_video_from_text_builds_the_right_workflow_and_shows_it(env):
    out = call(env, "comfy_video", prompt="A cute orange cat dancing in a living room", seed=7)
    job = env[3].jobs[-1]
    assert job["10"]["inputs"]["text"].startswith("A cute orange cat dancing")
    assert (job["9"]["inputs"]["width"], job["9"]["inputs"]["height"], job["9"]["inputs"]["length"]) == (480, 480, 33)
    assert job["12"]["inputs"]["noise_seed"] == job["13"]["inputs"]["noise_seed"] == 7
    assert "Made a 2-second 480x480 video (from text, seed 7)" in out and "[[shared:comfy/" in out


@pytest.mark.parametrize("kw,expect", [({"seconds": 5}, (480, 480, 81)), ({"seconds": 99}, (480, 480, 81)),
                                       ({"seconds": 1, "size": "landscape"}, (640, 368, 17)),
                                       ({"seconds": 3, "size": "portrait"}, (368, 640, 49)), ({"size": "weird"}, (480, 480, 33))])
def test_video_size_and_length_are_clamped_to_what_the_gpu_can_do(env, kw, expect):
    call(env, "comfy_video", prompt="a cat waves", **kw)
    n = env[3].jobs[-1]["9"]["inputs"]
    assert (n["width"], n["height"], n["length"]) == expect


def test_comfy_video_can_animate_a_picture(env):
    call(env, "write_file", path="cat.png", content="x")
    out = call(env, "comfy_video", prompt="the cat blinks and smiles", image="cat.png", seconds=2)
    job = env[3].jobs[-1]
    assert job["9"]["inputs"]["image"] == "uploaded.png" and job["10"]["inputs"]["text"] == "the cat blinks and smiles"
    assert job["12"]["inputs"]["length"] == 33 and "from your picture" in out


# ------------------------------------------------------------------ recovery
def test_out_of_memory_is_retried_once_with_a_smaller_video(env):
    env[3].outcomes = ["VRAM grow failed: 166912 bytes", "ok"]
    out = call(env, "comfy_video", prompt="a cat dancing", seconds=4, size="landscape")
    first, second = env[3].jobs
    assert first["9"]["inputs"]["length"] == 65 and second["9"]["inputs"]["length"] == 17
    assert (second["9"]["inputs"]["width"], second["9"]["inputs"]["height"]) == (384, 384)
    assert "Made a 1-second 384x384 video" in out and "retried smaller" in out


def test_if_it_still_runs_out_of_memory_the_user_gets_advice_not_a_loop(env):
    env[3].outcomes = ["out of memory", "out of memory"]
    out = call(env, "comfy_video", prompt="a cat dancing")
    assert out.startswith("ERROR") and "ran out of GPU memory" in out and len(env[3].jobs) == 2


def test_errors_tell_her_what_to_do(env):
    wrong = call(env, "comfy_run_workflow", template="wan-text-to-video", set={"12.prompt": "a dancing cat"})   # the transcript
    assert "no input '12.prompt'" in wrong and "10.text" in wrong and "comfy_video" in wrong
    noimg = call(env, "comfy_run_workflow", template="wan-image-to-video")
    assert "needs an input picture" in noimg and "9.image" in noimg and "wan-text-to-video" in noimg
    env[3].reject = {"error": {"message": "Prompt outputs failed validation"}, "node_errors": {
        "1": {"class_type": "UNETLoader", "errors": [{"message": "Value not in list", "details": "unet_name: 'x' not in [...]"}]}}}
    rej = call(env, "comfy_video", prompt="a cat")
    assert "comfy_list_models kind=all" in rej and "rejected the workflow" in rej
    env[3].reject = None
    env[3].outcomes = ["Node 'Foo' does not exist"]
    assert "does not have a node" in call(env, "comfy_video", prompt="a cat")


# ------------------------------------------------------------------ the language model's GPU memory
def test_ollama_models_are_unloaded_before_a_job_and_it_can_be_switched_off(env):
    call(env, "comfy_video", prompt="a cat")
    assert env[3].unloaded == ["qwen3:14b"] and "llm_unloaded_for_comfy" in env[1].audit_path.read_text()
    order = [u for u, _ in env[3].posts]
    assert order.index("http://localhost:11434/api/generate") < order.index("http://127.0.0.1:8188/prompt")
    env[3].unloaded.clear()
    env[0]["comfyui"]["free_llm_before"] = False
    call(env, "comfy_video", prompt="a cat")
    assert env[3].unloaded == []


def test_a_non_ollama_server_is_left_alone(env, monkeypatch):
    env[0]["llm"]["base_url"] = "http://localhost:1234/v1"            # LM Studio: no /api/ps (the fake refuses the URL)
    out = call(env, "comfy_video", prompt="a cat")
    assert "Made a" in out and env[3].unloaded == []


# ------------------------------------------------------------------ ComfyUI not running
def test_comfy_tools_say_what_to_do_when_comfyui_is_down(env):
    env[3].up = False
    assert "comfy_start" in call(env, "comfy_status")
    assert "comfy_start" in call(env, "comfy_video", prompt="a cat")


def test_comfy_start_asks_first_and_starts_a_local_only_server(env, monkeypatch, tmp_path):
    base = tmp_path / "ComfyUI"
    (base / ".venv" / "bin").mkdir(parents=True)
    (base / "main.py").write_text("")
    (base / ".venv" / "bin" / "python").write_text("")
    env[0]["comfyui"]["path"] = str(base)
    started, states = [], iter([False, False, True])
    srv = env[3]
    srv.up = False

    def popen(cmd, **kw):
        started.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 0)

    def fake_sleep(_):
        srv.up = next(states)
    monkeypatch.setattr("agent.tools.subprocess.Popen", popen)
    monkeypatch.setattr("agent.tools.time.sleep", fake_sleep)
    out = call(env, "comfy_start")
    assert "running now" in out and env[4][-1][0] == "launch" and str(base) in env[4][-1][1]
    cmd, kw = started[0]
    assert cmd[1:5] == ["main.py", "--listen", "127.0.0.1", "--port"] and "0.0.0.0" not in cmd and kw["cwd"] == base
    srv.up = True
    assert call(env, "comfy_start") == "ComfyUI is already running."


def test_comfy_start_refuses_when_denied_or_when_comfyui_is_not_found(env, tmp_path):
    env[3].up = False
    env[0]["comfyui"]["path"] = str(tmp_path / "nowhere")
    assert call(env, "comfy_start").startswith("ERROR: I cannot find ComfyUI")
    base = tmp_path / "C"
    (base / ".venv" / "bin").mkdir(parents=True)
    (base / "main.py").write_text("")
    (base / ".venv" / "bin" / "python").write_text("")
    env[0]["comfyui"]["path"] = str(base)
    env[1].approver = lambda c, s: "n"
    assert call(env, "comfy_start").startswith("DENIED")


# ------------------------------------------------------------------ her playbook
def test_the_playbook_names_only_tools_that_exist(env):
    text = (ROOT / "skills" / "comfyui-expert.md").read_text(encoding="utf-8")
    for tool in ("comfy_capabilities", "comfy_video", "comfy_txt2img", "comfy_run_workflow", "draw_myself", "comfy_start",
                 "comfy_list_models", "comfy_node_info", "comfy_check", "save_lesson"):
        assert tool in text and tool in env[2].tools, tool


# ------------------------------------------------------------------ the real ComfyUI (opt-in: MOCHI_LIVE_COMFY=1)
@pytest.mark.skipif(os.environ.get("MOCHI_LIVE_COMFY") != "1", reason="set MOCHI_LIVE_COMFY=1 to test against the real ComfyUI")
def test_live_comfyui_end_to_end(tmp_path, monkeypatch):
    monkeypatch.undo()
    cfg = copy.deepcopy(load_config(ROOT / "config.yaml"))
    cfg["sandbox"]["workspace"] = str(tmp_path / "ws")
    policy = make_policy(cfg, approver=lambda c, s: "y")
    policy.audit_path = tmp_path / "audit.jsonl"
    reg = build_tools(policy, cfg)
    assert "BROKEN" not in reg.call("comfy_check", {}, policy)
    caps = reg.call("comfy_capabilities", {}, policy)
    assert "comfy_video" in caps.split("INSTALLED")[0]
    out = reg.call("comfy_video", {"prompt": "A cute orange cat dancing on its hind legs in a living room", "seconds": 1}, policy)
    assert "Made a 1-second" in out and "[[shared:comfy/" in out
    rel = out.split("[[shared:")[1].split("|")[0]
    assert (policy.workspace / rel).stat().st_size > 5000
