"""Write contracts/openapi.json from the app. `--check` exits 1 if the file is stale."""

from __future__ import annotations

import json
import sys

from jobhunter import paths
from jobhunter.api.app import create_app


def render() -> str:
    return json.dumps(create_app(serve_web=False).openapi(), indent=2, sort_keys=False) + "\n"


def main() -> int:
    new = render()
    if "--check" in sys.argv:
        old = paths.CONTRACT.read_text() if paths.CONTRACT.exists() else ""
        if old != new:
            print("contracts/openapi.json is stale: run `uv run python -m jobhunter.api.dump_openapi`")
            return 1
        print("contract up to date")
        return 0
    paths.CONTRACT.parent.mkdir(parents=True, exist_ok=True)
    paths.CONTRACT.write_text(new)
    print(f"wrote {paths.CONTRACT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
