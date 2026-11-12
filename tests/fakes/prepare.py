"""Prepare synthetic inputs shared by pytest and the real-server Playwright launcher."""

from pathlib import Path


def prepare(root: Path) -> None:
    for directory in (root / "cv", root / "careerops/modes"):
        directory.mkdir(parents=True, exist_ok=True)
    cv = "# Example Candidate\n\nJava backend engineer\n"
    (root / "cv/cv_a.md").write_text(cv)
    (root / "careerops/cv.md").write_text(cv)
    (root / "careerops/profile.yml").write_text("name: Example Candidate\n")
    (root / "careerops/modes/_profile.md").write_text("Java backend engineer seeking Chennai roles.\n")
