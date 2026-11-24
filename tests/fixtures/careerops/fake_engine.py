#!/usr/bin/env python3
"""Offline stand-in for `codex exec` and `claude -p` in lean evaluation tests.

FAKE_CODEX / FAKE_CLAUDE = ok | fail | limit | junk choose the behaviour; argv and stdin are appended to
FAKE_CAPTURE as JSON lines so tests can assert isolation flags and that posting text never rides in argv."""

import json
import os
import sys

argv = sys.argv[1:]
engine = "codex" if argv[:1] == ["exec"] else "claude"
stdin = sys.stdin.read()
with open(os.environ["FAKE_CAPTURE"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps({"engine": engine, "argv": argv, "stdin": stdin}) + "\n")
mode = os.environ.get("FAKE_CODEX" if engine == "codex" else "FAKE_CLAUDE", "ok")
answer = {"score": 4.2 if engine == "codex" else 3.8, "call_chance": "high", "archetype": "Java Backend",
          "verdict": f"Strong Java backend match ({engine}).", "strengths": ["Spring Boot"], "gaps": [],
          "red_flags": []}
if mode == "fail":
    print("boom", file=sys.stderr)
    sys.exit(1)
if mode == "limit":
    if engine == "codex":
        print("ERROR: You've hit your usage limit. Try again later.", file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"type": "result", "is_error": True, "result": "You've hit your usage limit · resets 3am"}))
    sys.exit(1)
if engine == "codex":
    out = argv[argv.index("-o") + 1]
    with open(out, "w", encoding="utf-8") as handle:
        handle.write("not json" if mode == "junk" else json.dumps(answer))
    print("done")
else:
    print(json.dumps({"type": "result", "is_error": False, "result": json.dumps(answer), "structured_output": answer}))
