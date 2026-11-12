#!/usr/bin/env python3
"""Explicit, one-off live capture; tests only replay these small public responses."""

import time
from pathlib import Path

from jobspy import scrape_jobs

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "boards"


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for index, site in enumerate(("linkedin", "naukri", "indeed", "glassdoor")):
        if index:
            time.sleep(4)
        target = FIXTURES / f"{site}.json"
        if target.exists():
            print(f"{site}: already recorded; skipping")
            continue
        kwargs = {"country_indeed": "India"} if site in {"indeed", "glassdoor"} else {}
        try:
            frame = scrape_jobs(
                site_name=[site], search_term="Java Developer", location="Chennai",
                results_wanted=5, hours_old=72, linkedin_fetch_description=True,
                fetch_description=True, verbose=0, **kwargs,
            )
        except Exception as exc:  # noqa: BLE001 — capture the other sites even if one fails
            print(f"{site}: capture failed: {exc}")
            continue
        if frame.empty:
            print(f"{site}: empty response; no fixture written")
            continue
        target.write_text(frame.to_json(orient="records", date_format="iso") + "\n")
        print(f"{site}: recorded {len(frame)} rows in {target}")


if __name__ == "__main__":
    main()
