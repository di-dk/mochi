"""A stand-in for the skillspector CLI so the safety logic can be tested offline and deterministically.
Marker words in the skill decide the verdict: EVIL -> DO_NOT_INSTALL (exit 1), CAUTIOUS -> CAUTION, INCOMPLETE -> the
scan reports incomplete coverage, CRASH -> exit 2 without a report. Anything else is SAFE."""
import json
import pathlib
import sys

args = sys.argv
folder = pathlib.Path(args[2])
out = args[args.index("--output") + 1]
text = "\n".join(p.read_text(errors="replace") for p in sorted(folder.rglob("*")) if p.is_file())
if "CRASH" in text:
    sys.exit(2)
score = 100 if "EVIL" in text else 30 if "CAUTIOUS" in text else 0
sev, rec = ("CRITICAL", "DO_NOT_INSTALL") if score >= 81 else ("MEDIUM", "CAUTION") if score >= 21 else ("LOW", "SAFE")
issues = [] if not score else [{"id": "P1", "category": "Prompt Injection", "severity": "HIGH" if score > 50 else "MEDIUM",
                                "finding": "tells the agent to hide steps from the user", "remediation": "remove it",
                                "location": "SKILL.md:3"}]
json.dump({"risk_assessment": {"score": score, "severity": sev, "recommendation": rec},
           "issues": issues, "execution_successful": True, "metadata": {"version": "fake-1"},
           "analysis_completeness": ({"is_complete": False, "coverage_percent": 50.0, "entirely_uninspected_files": 1,
                                      "ledger_exceptions": []} if "INCOMPLETE" in text else
                                     {"is_complete": True, "coverage_percent": 100.0, "entirely_uninspected_files": 0,
                                      "ledger_exceptions": []})}, open(out, "w"))
sys.exit(1 if score >= 51 else 0)
