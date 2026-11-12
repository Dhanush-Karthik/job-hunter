#!/usr/bin/env python3
"""Offline Node/Claude substitute. No external service or production files touched."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

scenario = os.environ.get("COPS_SCENARIO", "happy")
fixture = Path(__file__).parent
arguments = sys.argv[1:]
is_claude = arguments[0] == "-p"
payload = json.loads(arguments[1]) if is_claude else (
    json.loads(sys.stdin.read()) if arguments[0].endswith(".mjs")
    and not arguments[0].endswith("generate-pdf.mjs") else {}
)
record = {"args": arguments, "payload": payload, "cwd": os.getcwd(),
          "data": os.environ.get("CAREER_OPS_DATA_DIR"), "tracker": os.environ.get("CAREER_OPS_TRACKER")}
if capture := os.environ.get("COPS_CAPTURE"):
    with Path(capture).open("a") as stream:
        stream.write(json.dumps(record) + "\n")

if is_claude:
    if scenario.startswith("usage_limit"):
        if scenario != "usage_limit_result":
            print(json.dumps({"type": "rate_limit_event", "rate_limit_info": {
                "status": "rejected", "resetsAt": 1794499200,
            }}))
        print(json.dumps({"type": "result", "is_error": True,
                          "result": "You've hit your limit; resets at 9:30pm (Asia/Kolkata)"}))
        raise SystemExit(0 if scenario == "usage_limit_zero" else 1)
    if scenario == "sleep":
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

        def stop(_sig, _frame):
            child.wait()
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, stop)
        Path(os.environ["COPS_PIDS"]).write_text(f"{os.getpid()} {child.pid}")
        print("waiting for cancellation", flush=True)
        while True:
            time.sleep(0.05)
    if scenario == "nonzero":
        print("first diagnostic", file=sys.stderr, flush=True)
        print("Claude session unavailable", file=sys.stderr, flush=True)
        raise SystemExit(7)
    if payload["kind"] == "pdf":
        text = ('<<cv-md>>\n# Example Candidate\nJava backend engineer\n<</cv-md>>\n'
                '<<cv-html format="a4">>\n<!DOCTYPE html><html><body>'
                '<h1>Example Candidate</h1><p>Java backend engineer</p></body></html>\n<</cv-html>>')
    elif payload["kind"] == "contacts":
        contacts = [] if scenario == "no_contacts" else [
            {"name": "Alex Example", "url": "https://www.linkedin.com/in/alex-example",
             "draft": "Your backend platform work caught my eye. I build Java services. Happy to connect."}
        ]
        text = "<<contacts-json>>\n" + json.dumps(contacts) + "\n<</contacts-json>>"
    else:
        text = fixture.joinpath("spike_report.txt").read_text()
        if scenario == "malformed":
            text = "No report: posting could not be read"
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}))
    print(json.dumps({"type": "result", "result": text, "is_error": scenario == "claude_error"}))
elif arguments[0].endswith("prompt.mjs"):
    local = payload["kind"] == "pdf"
    allowed = "Read,Glob,Grep" if local else "Read,WebFetch,WebSearch,Glob,Grep"
    denied = "Write,Edit,MultiEdit,NotebookEdit,Bash,Task"
    print(json.dumps({"args": ["-p", json.dumps(payload), "--output-format", "stream-json",
                              "--strict-mcp-config", "--allowedTools", allowed, "--disallowedTools", denied],
                      "report_slug": "example-software-ltd"}))
elif arguments[0].endswith("scan.mjs"):
    if scenario == "scan_error":
        print("All portals unreachable", file=sys.stderr)
        raise SystemExit(2)
    scanned = json.loads(fixture.joinpath("scan.json").read_text())
    if scenario == "partial_scan":
        scanned["postings"] = scanned["postings"][:1]
        scanned["errors"] = ["RemoteOK: upstream timeout"]
        scanned["sources"] = {"remoteok": {"count": 0, "error": "upstream timeout"},
                              "himalayas": {"count": 0, "error": None}}
    print(json.dumps(scanned))
elif arguments[0].endswith("verify.mjs"):
    live = False if scenario == "closed" else None if scenario == "unknown" else True
    print(json.dumps({"is_live": live, "reason": "API: posting closed" if live is False else "Checked"}))
elif arguments[0].endswith("facts.mjs"):
    print(json.dumps({"ok": scenario != "facts_fail", "verdict": "block" if scenario == "facts_fail" else "pass"}))
elif arguments[0].endswith("render.mjs"):
    Path(payload["output"]).write_bytes(b"%PDF-1.7\nFake offline PDF\n")
    if scenario == "pdf_error":
        print("PDF rendering failed", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({"outputPath": payload["output"], "pageCount": 1}))
elif arguments[0].endswith("assist.mjs"):
    assert payload["submit"] is False
    assert payload["headed"] is True
    print(json.dumps({"owner_browser_ready": True, "filled": ["name", "email"], "submitted": False}))
else:
    print("Unexpected fake command", file=sys.stderr)
    raise SystemExit(3)
