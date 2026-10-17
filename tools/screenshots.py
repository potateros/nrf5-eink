"""Regenerate the README screenshots from live data: docs/images/<layout>.png at 2x (pixel-exact).

  uv run python tools/screenshots.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PIL import Image  # noqa: E402

from epd.cli import SCREENS, build, load_config  # noqa: E402
from epd.image import preview  # noqa: E402

OUT = ROOT / "docs" / "images"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    for name in SCREENS:
        if name == "auto":
            continue  # shows rain or proverb, which have their own screenshots
        img = preview(build(name, cfg), red=True, dither=False)  # exactly what the panel gets
        img.resize((img.width * 2, img.height * 2), Image.NEAREST).save(OUT / f"{name}.png", optimize=True)
        print("wrote", OUT / f"{name}.png")


if __name__ == "__main__":
    main()
