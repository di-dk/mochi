"""Working in many languages: documents in any script, speech, her language rule, and the Nepali toolkit."""
import copy
import datetime as dt
import subprocess
import sys
from pathlib import Path

import pytest
from pypdf import PdfReader

from agent import fonts, nepali, pdf
from agent import platform_compat as pc
from agent.core import ROOT, Agent, load_config, make_policy
from agent.tools import build_tools


@pytest.fixture
def env(tmp_path):
    cfg = copy.deepcopy(load_config(ROOT / "config.yaml"))
    cfg["sandbox"]["workspace"] = str(tmp_path / "ws")
    policy = make_policy(cfg, approver=lambda c, s: "y")
    policy.audit_path = tmp_path / "audit.jsonl"
    return cfg, policy, build_tools(policy, cfg), tmp_path


def call(env, tool, **kw):
    return env[2].call(tool, kw, env[1])


# ------------------------------------------------------------------ scripts and fonts
def test_script_detection():
    assert fonts.scripts_in("hello") == set() and not fonts.needs_unicode_font("Résumé — 12 € “quotes”")
    assert fonts.needs_unicode_font("zażółć") and fonts.needs_unicode_font("Привет")
    assert {"kana", "han"} <= fonts.scripts_in("日本語のテキスト") and "hangul" in fonts.scripts_in("한국어")
    assert "arabic" in fonts.scripts_in("مرحبا") and "hebrew" in fonts.scripts_in("שלום")
    assert fonts.scripts_in("नेपाली") == {"complex"} and fonts.scripts_in("สวัสดี") == {"complex"}
    assert fonts.is_rtl("مرحبا hello") and not fonts.is_rtl("hello مرحبا") and not fonts.is_rtl("123")


def test_right_to_left_text_is_shaped_and_reordered():
    s = "مرحبا"
    shaped = fonts.rtl_display(s)
    assert shaped != s and len(shaped) == len(s)                      # joined letter forms, reversed for a left-to-right canvas
    assert fonts.rtl_display("plain English") == "plain English"


# ------------------------------------------------------------------ PDF in every script
def text_of(path: Path) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)


def test_western_pdf_keeps_helvetica_and_other_alphabets_get_a_real_font(tmp_path):
    west = tmp_path / "w.pdf"
    pdf.markdown_to_pdf("# Résumé\n\nÇa va très bien, señor Müller. 12 €", west)
    assert b"Helvetica" in west.read_bytes() and pdf.NOTES == []
    cyr = tmp_path / "c.pdf"
    pdf.markdown_to_pdf("# Привет, мир! Γειά σου\n\nPolski: zażółć gęślą jaźń. Română: țară.", cyr)
    txt = text_of(cyr)
    assert "Привет" in txt and "Γειά" in txt and "zażółć" in txt and "țară" in txt
    assert b"MochiSans" in cyr.read_bytes() or b"DejaVu" in cyr.read_bytes()


def test_cjk_mixed_with_other_scripts_and_right_to_left(tmp_path):
    out = tmp_path / "m.pdf"
    pdf.markdown_to_pdf("# Mixed: English, Русский, 日本語, 中文, 한국어\n\nHello мир! 日本語とEnglish. 한국어와 English.", out)
    assert out.stat().st_size > 1000 and any("viewer" in n for n in pdf.NOTES)
    rtl = tmp_path / "r.pdf"
    pdf.markdown_to_pdf("# مرحبا بالعالم\n\nهذا نص تجريبي.\n\n## עברית\n\nשלום עולם!\n\n- نقطة", rtl)
    assert rtl.stat().st_size > 1000 and pdf.NOTES == []


def has_chromium() -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not has_chromium(), reason="Chromium is not installed (playwright install chromium)")
def test_nepali_pdf_is_printed_by_the_browser_engine(tmp_path):
    out = tmp_path / "ne.pdf"
    pages = pdf.markdown_to_pdf("# नमस्ते\n\nम मोचि हुँ। क्ष, त्र, ज्ञ।\n\n| वस्तु | मूल्य |\n|---|---|\n| चामल | रु. २,५०० |", out)
    assert pages == 1 and any("browser engine" in n for n in pdf.NOTES)
    assert len(text_of(out).strip()) > 10


def test_complex_script_falls_back_with_a_clear_note_when_the_browser_is_missing(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no chromium")
    monkeypatch.setattr(pdf, "markdown_to_pdf_browser", boom)
    out = tmp_path / "ne.pdf"
    pdf.markdown_to_pdf("# नमस्ते\n\nम मोचि हुँ।", out)
    assert out.exists() and any("could not be shaped" in n and "Chromium" in n for n in pdf.NOTES)


def test_create_pdf_tool_reports_the_notes(env):
    out = call(env, "create_pdf", path="j.pdf", markdown="# 日本語\n\nこんにちは")
    assert "Created" in out and "Note:" in out and "viewer" in out


def test_word_documents_mark_right_to_left_paragraphs(env):
    from docx import Document
    call(env, "create_docx", path="a.docx", markdown="# مرحبا\n\nهذا نص عربي.\n\nPlain English.")
    doc = Document(str(env[1].workspace / "a.docx"))
    bidi = {p.text: p._p.pPr is not None and p._p.pPr.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}bidi") is not None for p in doc.paragraphs}
    assert bidi["هذا نص عربي."] is True and bidi["Plain English."] is False


# ------------------------------------------------------------------ speech
def test_speech_language_is_validated_and_passed_on(monkeypatch):
    seen = []
    monkeypatch.setattr(pc, "IS_WINDOWS", False)
    monkeypatch.setattr(pc.shutil, "which", lambda n: "/usr/bin/" + n if n == "spd-say" else None)
    monkeypatch.setattr(pc.subprocess, "run", lambda cmd, **kw: (seen.append(cmd), subprocess.CompletedProcess(cmd, 0, "", ""))[1])
    assert pc.speak("नमस्ते", "ne") == (True, "")
    assert seen[-1][:4] == ["spd-say", "--wait", "-l", "ne"] and seen[-1][-1] == "नमस्ते"
    assert pc.speak("hello")[0] and "-l" not in seen[-1]
    n = len(seen)
    ok, err = pc.speak("x", "ne; rm -rf ~")                                        # never reaches a command line
    assert not ok and "language code" in err and len(seen) == n


# ------------------------------------------------------------------ her language rule
def test_she_answers_in_the_users_language_by_default_or_a_fixed_one(env):
    cfg, policy, reg, tmp = env
    agent = Agent.__new__(Agent)
    agent.cfg, agent.policy, agent.registry, agent.vision, agent.messages = cfg, policy, reg, False, []
    rule = agent._language_rule()
    assert "ALWAYS answer in the language the user writes in" in rule and "tu/vous" in rule and "name stays" in rule
    cfg["agent"]["language"] = "Dutch"
    assert "ALWAYS answer in Dutch" in agent._language_rule()
    assert "Language:" in agent.system_message()["content"]


def test_chat_window_handles_right_to_left_and_any_script():
    html = (ROOT / "agent" / "web" / "index.html").read_text(encoding="utf-8")
    assert "unicode-bidi:plaintext" in html


# ------------------------------------------------------------------ Nepali
def test_nepali_digits_grouping_and_money():
    assert nepali.to_nepali_digits("2083-08-10") == "२०८३-०८-१०" and nepali.to_ascii_digits("१२३४") == "1234"
    assert [nepali.group_lakh(n) for n in (999, 1000, 12345, 100000, 1234567, 123456789)] == [
        "999", "1,000", "12,345", "1,00,000", "12,34,567", "12,34,56,789"]
    assert nepali.group_lakh("१२३४५६७") == "12,34,567" and nepali.group_lakh(-1234567) == "-12,34,567"
    assert nepali.group_lakh(12345.5, 2) == "12,345.50"
    assert nepali.money(1234567) == "रु. १२,३४,५६७" and nepali.money(25000, False) == "Rs. 25,000"


@pytest.mark.parametrize("bs,ad", [
    ("2081-01-01", "2024-04-13"), ("2082-01-01", "2025-04-14"), ("2083-01-01", "2026-04-14"),   # Nepali New Year
    ("2082-06-15", "2025-10-01"), ("2082-06-16", "2025-10-02"),                                 # Bijaya Dashami = 16 Ashwin 2082
])
def test_calendar_matches_known_dates(bs, ad):
    r = nepali.convert(f"{bs} BS")
    assert r["ad"] == ad
    assert nepali.convert(ad)["bs"] == bs                                                      # and back again


def test_calendar_names_and_input_forms():
    r = nepali.convert("2026-11-26")
    assert r["bs_ne"] == "२०८३ मंसिर १०, बिहीबार" and r["weekday_en"] == "Thursday" and r["month_en"] == "Mangsir"
    assert nepali.convert("२०८३-०८-१० BS")["ad"] == "2026-11-26" and nepali.convert("2083/8/10 बि.सं.")["ad"] == "2026-11-26"
    assert nepali.convert()["ad"] == dt.date.today().isoformat()
    assert nepali.DAYS_NE[6] == "आइतबार" and len(nepali.MONTHS_NE) == 12
    for bad in ("hello", "2083-13-40 BS", "1800-01-01"):
        with pytest.raises(ValueError):
            nepali.convert(bad)


def test_nepali_tools(env):
    out = call(env, "nepali_date", date="2026-11-26")
    assert "२०८३ मंसिर १०, बिहीबार" in out and "2083-08-10" in out and "Thursday" in out
    assert "ERROR" in call(env, "nepali_date", date="not a date")
    assert call(env, "nepali_format", value="1234567", mode="money") == "रु. १२,३४,५६७"
    assert call(env, "nepali_format", value="1234567") == "१२,३४,५६७"
    assert call(env, "nepali_format", value="1234567", devanagari=False) == "12,34,567"
    assert call(env, "nepali_format", value="2083", mode="digits") == "२०८३"
    assert call(env, "nepali_format", value="१२३", mode="ascii") == "123"
    assert call(env, "nepali_format", value="abc").startswith("ERROR")


def test_language_skills_exist_and_name_real_tools(env):
    reg = env[2]
    for name in ("translate-text", "work-in-language", "nepali", "nepal-info"):
        text = (ROOT / "skills" / f"{name}.md").read_text(encoding="utf-8")
        assert text.startswith(f"name: {name}\n")
    for tool in ("nepali_date", "nepali_format", "speak", "create_pdf", "create_docx", "fetch_url", "web_search"):
        assert tool in reg.tools


# ------------------------------------------------------------------ translate_text
class FakeOpenAI:
    calls = []
    reply = "TRANSLATED"

    def __init__(self, **kw):
        FakeOpenAI.init = kw
        self.chat = type("C", (), {"completions": self})()

    def create(self, **kw):
        FakeOpenAI.calls.append(kw)
        content = FakeOpenAI.reply(kw) if callable(FakeOpenAI.reply) else FakeOpenAI.reply
        msg = type("M", (), {"content": content})()
        return type("R", (), {"choices": [type("Ch", (), {"message": msg})()]})()


@pytest.fixture
def fake_llm(monkeypatch):
    import openai
    FakeOpenAI.calls, FakeOpenAI.reply = [], "TRANSLATED"
    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    return FakeOpenAI


def test_translate_text_uses_a_dedicated_pass_and_the_nepali_glossary(env, fake_llm):
    out = call(env, "translate_text", text="Please send me the invoice by Friday.", to="Nepali")
    assert out == "TRANSLATED"
    sent = fake_llm.calls[-1]
    system, user = sent["messages"][0]["content"], sent["messages"][1]["content"]
    assert "into Nepali" in system and "बिजक" in system and "शुक्रबारसम्म" in system and "never use Hindi" in system
    assert user == "Please send me the invoice by Friday." and "tools" not in sent and sent["temperature"] == 0.2
    call(env, "translate_text", text="Good morning", to="French", source="English", tone="casual")
    sys_fr = fake_llm.calls[-1]["messages"][0]["content"]
    assert "from English into French" in sys_fr and "casual" in sys_fr and "बिजक" not in sys_fr


def test_translate_text_can_use_a_separate_translator_model_and_handles_failures(env, fake_llm):
    env[0]["llm"]["translator_model"] = "gemma3:12b"
    call(env, "translate_text", text="Hi", to="Dutch")
    assert fake_llm.calls[-1]["model"] == "gemma3:12b"
    fake_llm.reply = ""
    assert call(env, "translate_text", text="Hi", to="Dutch").startswith("ERROR: the translation model")
    assert call(env, "translate_text", text="   ", to="Dutch") == "Nothing to translate."
    assert call(env, "translate_text", text="x" * 20001, to="Dutch").startswith("ERROR")


def test_long_text_is_translated_in_chunks_and_joined(env, fake_llm):
    fake_llm.reply = lambda kw: "T:" + kw["messages"][1]["content"][:3]
    text = "\n".join(f"{i:03d} " + "word " * 60 for i in range(20))            # about 6,000 characters
    out = call(env, "translate_text", text=text, to="German")
    assert len(fake_llm.calls) >= 3 and out.count("T:") == len(fake_llm.calls) and out.startswith("T:000")


def test_the_nepali_recipe_brings_the_glossary_with_it(env):
    from tests.test_smart import make_agent
    agent, seen = make_agent((env[0], env[1], env[2]), [("ok", [])])
    agent.run("नमस्ते मोचि, कृपया नेपाली मा मलाई मद्दत गर्नुहोस्")
    user = seen[0]["messages"][-1]["content"]
    assert "your skill 'nepali' matches" in user and "--- nepali-glossary ---" in user and "बिजक" in user


def test_no_recipe_contains_a_date_she_could_copy_instead_of_calling_the_tool():
    import re
    for name in ("nepali", "nepal-info", "nepali-glossary", "translate-text", "work-in-language"):
        text = (ROOT / "skills" / f"{name}.md").read_text(encoding="utf-8")
        assert not re.search(r"\b(20[89]\d)[-/ ]\d{1,2}[-/ ]\d{1,2}\b|[२][०][८९][०-९]\s*(बैशाख|जेठ|असार|साउन|भदौ|असोज|कात्तिक|मंसिर|पुष|माघ|फागुन|चैत)", text), \
            f"{name} has a concrete date: a small model copies it instead of asking the tool"


def test_the_nepali_recipe_carries_todays_date_computed_fresh(env):
    from tests.test_smart import make_agent
    agent, seen = make_agent((env[0], env[1], env[2]), [("ok", [])])
    agent.run("आजको मिति नेपालीमा भन्नुहोस्")
    user = seen[0]["messages"][-1]["content"]
    today = nepali.convert("")
    assert today["bs_ne"] in user and today["ad_en"] in user and "Use exactly this for 'today'" in user


def test_a_stray_latin_letter_inside_a_word_triggers_one_retry(env, fake_llm):
    replies = ["हाm्रो कार्यालय बन्द छ।", "हाम्रो कार्यालय बन्द छ।"]
    fake_llm.reply = lambda kw: replies.pop(0)
    out = call(env, "translate_text", text="Our office is closed.", to="Nepali")
    assert out == "हाम्रो कार्यालय बन्द छ।" and len(fake_llm.calls) == 2 and fake_llm.calls[1]["temperature"] == 0.0
    fake_llm.calls.clear()
    fake_llm.reply = "हाm्रो कार्यालय"                                   # it slips again: keep it, but warn
    out = call(env, "translate_text", text="Our office", to="Nepali")
    assert out.startswith("हाm्रो") and "⚠ check the spelling" in out and len(fake_llm.calls) == 2
    fake_llm.calls.clear()
    fake_llm.reply = "Hello, Anna! Version 2.0"                        # normal Latin text is never touched
    assert call(env, "translate_text", text="x", to="English") == "Hello, Anna! Version 2.0" and len(fake_llm.calls) == 1


def test_browser_pdf_does_not_print_the_title_twice():
    body = lambda h: h.split("<body>")[1]
    same = pdf._html_page("तपाईंको बारेमा\n\nम मोचि हुँ।", "तपाईंको बारेमा", None)
    assert "<h1>" not in body(same) and "<title>तपाईंको बारेमा</title>" in same        # no extra heading, metadata kept
    other = pdf._html_page("# Intro\n\ntext", "A different title", None)
    assert "<h1>A different title</h1>" in body(other)
