"""Validate data/proverbs.json: 366 unique MM-DD dates (incl. 02-29), unique texts, and every
entry fits the proverb layout's 2/6 panel with its attribution.

  uv run python tools/check_proverbs.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image, ImageDraw  # noqa: E402

from screens import note, proverb  # noqa: E402


def main():
    entries = json.loads(proverb.PROVERBS.read_text())
    d = ImageDraw.Draw(Image.new("1", (1, 1)))
    split = note.split_x(proverb.MAIN_COLS)
    problems = []
    if len({e["date"] for e in entries}) != 366 or len(entries) != 366:
        problems.append(f"expected 366 unique dates, got {len(entries)} entries")
    if len({e["text"].lower() for e in entries}) != len(entries):
        problems.append("duplicate texts")
    small = 0
    for e in entries:
        *_, font_lines, fits = note.panel_lines(d, e["text"], e["by"], split, keep_breaks=False)
        lines, font, *_ = note.panel_lines(d, e["text"], e["by"], split, keep_breaks=False)
        small += font.size == 12
        if not fits:
            problems.append(f'{e["date"]}: does not fit: {e["text"]}')
    print(f"{len(entries)} entries, {small} drop to 12 px")
    if problems:
        sys.exit("\n".join(problems))
    print("ok")


if __name__ == "__main__":
    main()
