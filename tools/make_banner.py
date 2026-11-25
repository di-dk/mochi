"""Make a release banner (1280x640) in Mochi's usual style: framed illustration on the left, title, tagline, pills for
what is new (filled) and the standing features (outlined), version in the footer.

  python tools/make_banner.py --version v0.10.0 --art path/to/illustration.png --skills 45 \
      --new "Teaches herself new skills" --new "ComfyUI edit + animate" --out assets/banner-v0.10.0.png

Needs Pillow and the Open Sans fonts (or pass --font-dir)."""
from __future__ import annotations

import argparse
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H, S = 1280, 640, 2                      # drawn at 2x and scaled down for smooth edges
PINK, PINK_LINE, MAGENTA, PURPLE, FOOT = "#d6337f", "#e68ab8", "#9a1c5e", "#8e60a8", "#b3a0c6"
STANDING = ["Local LLM", "Vision", "Headless browser", "App control", "{n} skills", "Makes videos", "ComfyUI art",
            "PDF · Word · Excel", "Learns skills", "Asks before risky stuff"]


def font(dirs: list[Path], names: list[str], size: int) -> ImageFont.FreeTypeFont:
    for d in dirs:
        for n in names:
            if (d / n).is_file():
                return ImageFont.truetype(str(d / n), size * S)
    raise SystemExit(f"font not found: {names}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--art", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--skills", type=int, default=41)
    ap.add_argument("--new", action="append", default=[], help="a highlight pill (repeat for several)")
    ap.add_argument("--tagline", default="that runs entirely on your PC")
    ap.add_argument("--font-dir", action="append", default=[])
    a = ap.parse_args()
    dirs = [Path(d) for d in a.font_dir] + [Path("/usr/share/fonts/truetype/open-sans"), Path("/usr/share/fonts/truetype/noto")]
    bold = font(dirs, ["OpenSans-Bold.ttf", "NotoSans-Bold.ttf"], 150)
    pill_f = font(dirs, ["OpenSans-Semibold.ttf", "OpenSans-SemiBold.ttf", "OpenSans-Bold.ttf"], 21)
    tag_f = font(dirs, ["OpenSans-Regular.ttf", "NotoSans-Regular.ttf"], 40)
    foot_f = font(dirs, ["OpenSans-Regular.ttf", "NotoSans-Regular.ttf"], 25)

    # background: soft lavender-pink gradient with a few sparkles
    bg = Image.new("RGB", (W * S, H * S))
    px = bg.load()
    c1, c2 = (248, 230, 245), (232, 221, 243)
    for y in range(0, H * S, 4):
        for x in range(0, W * S, 4):
            t = (x / (W * S) * 0.6 + y / (H * S) * 0.4)
            col = tuple(round(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
            for dy in range(4):
                for dx in range(4):
                    if x + dx < W * S and y + dy < H * S:
                        px[x + dx, y + dy] = col
    d = ImageDraw.Draw(bg, "RGBA")
    rnd = random.Random(a.version)
    for _ in range(26):
        x, y, r = rnd.randint(520, W - 20) * S, rnd.randint(10, H - 10) * S, rnd.randint(2, 7) * S
        d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, rnd.randint(110, 200)))

    # framed illustration
    box = (40 * S, 28 * S, 498 * S, 612 * S)
    shadow = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((box[0], box[1] + 10 * S, box[2], box[3] + 10 * S), 46 * S, fill=(150, 60, 120, 70))
    bg = Image.alpha_composite(bg.convert("RGBA"), shadow.filter(ImageFilter.GaussianBlur(14 * S)))
    d = ImageDraw.Draw(bg, "RGBA")
    d.rounded_rectangle(box, 46 * S, fill="white")
    inner = (box[0] + 8 * S, box[1] + 8 * S, box[2] - 8 * S, box[3] - 8 * S)
    iw, ih = inner[2] - inner[0], inner[3] - inner[1]
    art = ImageOps.fit(Image.open(a.art).convert("RGB"), (iw, ih), Image.LANCZOS, centering=(0.5, 0.0))
    mask = Image.new("L", (iw, ih), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, iw, ih), 38 * S, fill=255)
    bg.paste(art, inner[:2], mask)
    d = ImageDraw.Draw(bg, "RGBA")

    # text
    x0 = 548 * S
    d.text((x0, 215 * S), "Mochi", font=bold, fill=PINK, anchor="ls")
    d.text((x0, 273 * S), "a cute, careful AI agent", font=tag_f, fill=PURPLE, anchor="ls")
    d.text((x0, 318 * S), a.tagline, font=tag_f, fill=PURPLE, anchor="ls")

    def pills(items: list[str], top: int, filled: bool) -> int:
        x, y, h = x0, top * S, 42 * S
        for text in items:
            tw = int(pill_f.getlength(text))
            w = tw + 32 * S
            if x + w > 1240 * S:
                x, y = x0, y + h + 9 * S
            if filled:
                d.rounded_rectangle((x, y, x + w, y + h), h // 2, fill=PINK)
                d.text((x + w // 2, y + h // 2 + 1 * S), text, font=pill_f, fill="white", anchor="mm")
            else:
                d.rounded_rectangle((x, y, x + w, y + h), h // 2, fill=(255, 255, 255, 235), outline=PINK_LINE, width=2 * S)
                d.text((x + w // 2, y + h // 2 + 1 * S), text, font=pill_f, fill=MAGENTA, anchor="mm")
            x += w + 9 * S
        return (y + h) // S

    bottom = pills(a.new, 338, True)
    pills([s.format(n=a.skills) for s in STANDING], bottom + 9, False)
    d.text((x0, 610 * S), f"github.com/di-dk/mochi  ·  {a.version}", font=foot_f, fill=FOOT, anchor="ls")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    bg.convert("RGB").resize((W, H), Image.LANCZOS).save(a.out, optimize=True)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
