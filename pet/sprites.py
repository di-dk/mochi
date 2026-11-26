"""Her chibi sprites for pet mode, with no window code (so it can be tested).

One consistent picture of her is the base (pet/sprites/base.png, transparent). The animations are made from it in code
(bob, hop, tilt, stretch, flip), so every frame is exactly the same girl. Optional variants make her face change:
  talk.png  mouth open        blink.png  eyes closed        happy.png  big smile        sleep.png  asleep
  wave.png  hand up           think.png  thinking face      drag.png   being picked up
Any variant that is missing falls back to the base. Without base.png a simple placeholder is drawn.
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

DIR = Path(__file__).resolve().parent / "sprites"
ANIM = Path(__file__).resolve().parent / "anim"           # real clips made by pet/make_anim.py, one folder per state
FPS = 16
SIZE = 192                                   # the character fits in a SIZE x SIZE box
PAD_X, PAD_TOP = 64, 56                      # room around her for hops, tilts and stretches, so nothing is clipped
CANVAS_W, CANVAS_H = SIZE + 2 * PAD_X, SIZE + PAD_TOP
VARIANTS = ("talk", "blink", "happy", "sleep", "wave", "think", "drag", "walk1", "walk2")
STATES = ("idle", "walk", "talk", "sleep", "wave", "happy", "think", "drag")
# clip-only states: without a generated clip they borrow the motion of a similar state
FALLBACK = {"dragb": "drag", "dragf": "drag", "pokeh": "happy", "pokeb": "wave", "pokef": "think",
            "bed": "sleep", "chair": "sleep", "read": "think", "tea": "idle"}
SCENES = {"bed": 1.8, "chair": 1.0, "read": 1.0, "tea": 1.0}   # states where she sits/lies on furniture -> extra scale so her head matches


def placeholder() -> Image.Image:
    """A simple chibi (pink bob, maid dress) used until the real art is generated."""
    S = 4
    im = Image.new("RGBA", (SIZE * S, SIZE * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    p = lambda v: int(v * S)
    d.ellipse([p(52), p(150), p(94), p(184)], fill="#f7c9a8")           # feet
    d.ellipse([p(98), p(150), p(140), p(184)], fill="#f7c9a8")
    d.polygon([(p(60), p(112)), (p(132), p(112)), (p(150), p(166)), (p(42), p(166))], fill="#ee6fa4")   # dress
    d.polygon([(p(76), p(116)), (p(116), p(116)), (p(124), p(166)), (p(68), p(166))], fill="#ffffff")    # apron
    d.ellipse([p(40), p(112), p(62), p(140)], fill="#f7c9a8")                                              # hands
    d.ellipse([p(130), p(112), p(152), p(140)], fill="#f7c9a8")
    d.ellipse([p(34), p(20), p(158), p(124)], fill="#f09abd")                                              # hair back
    d.ellipse([p(42), p(34), p(150), p(120)], fill="#fde0cc")                                              # face
    d.pieslice([p(36), p(14), p(156), p(96)], 180, 360, fill="#f27aa9")                                    # fringe
    for x in (72, 120):
        d.ellipse([p(x - 7), p(76), p(x + 7), p(96)], fill="#3b2742")
        d.ellipse([p(x - 3), p(79), p(x + 1), p(84)], fill="#ffffff")
    d.ellipse([p(56), p(94), p(74), p(104)], fill="#ff9db8")                                                # blush
    d.ellipse([p(118), p(94), p(136), p(104)], fill="#ff9db8")
    d.arc([p(86), p(94), p(106), p(108)], 20, 160, fill="#b0405f", width=p(2))
    return im.resize((SIZE, SIZE), Image.LANCZOS)


def _base_transform(base: Image.Image) -> tuple[float, float, float]:
    """(scale, feet_x, feet_y): one mapping for every picture and clip frame, taken from the base picture, so her proportions are
    identical in every pose and every animation (base bbox height becomes SIZE-8 pixels)."""
    box = base.convert("RGBA").getbbox() or (0, 0, base.width, base.height)
    k = (SIZE - 8) / (box[3] - box[1])
    return k, (box[0] + box[2]) / 2, float(box[3])


def _place(im: Image.Image, k: float, fx: float, fy: float, ref_w: int) -> Image.Image:
    """Scale a whole picture/frame by k (adjusted if it has a different resolution than the reference) and put it on the pet
    canvas so the base's feet land at the bottom centre."""
    r = im.width / ref_w
    sc = k / r
    big = im.convert("RGBA").resize((max(1, round(im.width * sc)), max(1, round(im.height * sc))), Image.LANCZOS)
    out = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    out.paste(big, (round(CANVAS_W / 2 - fx * k), round(CANVAS_H - 2 - fy * k)), big)
    return out


_REF: dict = {}


def load_images(folder: Path | None = None) -> dict[str, Image.Image]:
    """base plus whichever pose pictures exist, all placed with the same mapping (canvas-sized)."""
    folder = folder or DIR
    base = next((folder / f"base{e}" for e in (".png", ".webp") if (folder / f"base{e}").is_file()), folder / "base.png")
    if not base.is_file():
        _REF.clear()
        p = placeholder()
        return {"base": _place(p, *_base_transform(p), p.width)}
    b = Image.open(base)
    k, fx, fy = _base_transform(b)
    _REF.update(k=k, fx=fx, fy=fy, w=b.width)
    out = {"base": _place(b, k, fx, fy, b.width)}
    for v in VARIANTS:
        f = next((folder / f"{v}{e}" for e in (".png", ".webp") if (folder / f"{v}{e}").is_file()), None)
        if f:
            out[v] = _place(Image.open(f), k, fx, fy, b.width)
    return out


def _best_loop(frames_: list[Image.Image], min_len: int = 16) -> tuple[list[Image.Image], int]:
    """Pick the stretch of a clip that loops best: the pair of frames (i, j), at least min_len apart, that look most alike.
    Returns the frames i..j-1 and how many frames of dissolve to add at the seam (fewer when the match is very good)."""
    import numpy as np
    small = []
    for f in frames_:
        g = f.resize((60, 80), Image.BILINEAR)
        a_ = np.asarray(g).astype(np.float32)
        a_[..., :3] *= a_[..., 3:4] / 255.0
        small.append(a_.ravel())
    best, pair = None, (0, len(frames_) - 1)
    for i in range(len(frames_) - min_len):
        for j in range(i + min_len, len(frames_)):
            d = float(np.mean(np.abs(small[i] - small[j]))) - 0.06 * (j - i)      # prefer similar AND longer
            if best is None or d < best:
                best, pair = d, (i, j)
    i, j = pair
    seam = float(np.mean(np.abs(small[i] - small[j])))
    return frames_[i:j], (2 if seam < 4.0 else 4)


def load_clips(folder: Path | None = None) -> dict[str, list[Image.Image]]:
    """Real animation clips (pet/anim/<state>/NNN.png), placed with the same mapping as the pictures and made seamless by
    dissolving the end into the start. Scenes with furniture get a scale that makes her head match the standing size and are
    set down on the ground line. Empty when none were generated."""
    import numpy as np
    folder = folder or ANIM
    if not folder.is_dir() or not _REF:
        return {}
    out: dict[str, list[Image.Image]] = {}
    for d in sorted(p for p in folder.iterdir() if p.is_dir()):
        files = sorted([*d.glob("*.png"), *d.glob("*.webp")])
        if len(files) < 8:
            continue
        extra = SCENES.get(d.name, 1.0)
        fr = [_place(Image.open(f), _REF["k"] * extra, _REF["fx"], _REF["fy"], _REF["w"]) for f in files]
        if d.name in SCENES:                                              # sit the whole scene on the ground line, centred
            boxes = [b for b in (f.getbbox() for f in fr) if b]
            if boxes:
                x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
                x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
                dx, dy = round(CANVAS_W / 2 - (x0 + x1) / 2), round(CANVAS_H - 2 - y1)
                moved = []
                for f in fr:
                    g = Image.new("RGBA", f.size, (0, 0, 0, 0)); g.paste(f, (dx, dy), f); moved.append(g)
                fr = moved
        fr, n = _best_loop(fr)                                          # loop between the two frames that look most alike
        arr = []
        for f in fr:                                                    # premultiplied, so transparent pixels cannot tint the blend
            a_ = np.asarray(f).astype(np.float32); a_[..., :3] *= a_[..., 3:4] / 255.0; arr.append(a_)
        for i in range(n):                                              # a short dissolve hides what difference is left
            w = (i + 1) / (n + 1)
            arr[len(fr) - n + i] = arr[len(fr) - n + i] * (1 - w) + arr[i] * w
        res = []
        for a_ in arr:
            al = a_[..., 3:4]
            rgb = np.where(al > 0.5, a_[..., :3] * 255.0 / np.maximum(al, 1.0), 0)
            res.append(Image.fromarray(np.concatenate([rgb, al], axis=2).clip(0, 255).astype(np.uint8), "RGBA"))
        out[d.name] = res
    return out


def _xform(im: Image.Image, dy: float = 0, sy: float = 1.0, sx: float = 1.0, rot: float = 0) -> Image.Image:
    """Squash/stretch around the feet, tilt around the feet, and lift, on a canvas with room around her."""
    w, h = im.size
    if sx != 1.0 or sy != 1.0:
        im = im.resize((max(1, round(w * sx)), max(1, round(h * sy))), Image.BICUBIC)
    out = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    out.paste(im, (PAD_X + (w - im.width) // 2, round(CANVAS_H - im.height - 2 - dy)), im)
    if rot:
        out = out.rotate(rot, resample=Image.BICUBIC, center=(CANVAS_W / 2, CANVAS_H - 2))
    return out


def frames(imgs: dict[str, Image.Image], state: str, facing: int = 1, clips: dict | None = None) -> list[Image.Image]:
    """The frames of one animation: the real clip when there is one, otherwise motion made in code from the pictures.
    facing +1 = looks right, -1 = looks left (the pictures look right / front)."""
    if clips and state in clips:
        out = list(clips[state])
        return [f.transpose(Image.FLIP_LEFT_RIGHT) for f in out] if facing < 0 else out
    if state in FALLBACK:
        state = FALLBACK[state]
    b = imgs["base"]
    v = lambda n: imgs.get(n, b)
    out: list[Image.Image] = []
    if state == "idle":
        for i in range(12):
            t = math.sin(i / 12 * 2 * math.pi)
            f = _xform(b, sy=1 - 0.025 * t, sx=1 + 0.012 * t)
            out.append(_xform(imgs["blink"], sy=1 - 0.025 * t, sx=1 + 0.012 * t) if i in (9, 10) and "blink" in imgs else f)
    elif state == "walk":
        for i in range(10):                                  # step left, step right (real walking poses when she has them)
            t = math.sin(i / 10 * 2 * math.pi)
            pose = imgs.get("walk1" if i < 5 else "walk2", b)
            out.append(_xform(pose, dy=4 * abs(t), rot=2 * t if "walk1" in imgs else 5 * t))
    elif state == "talk":
        for i in range(8):
            t = math.sin(i / 8 * 2 * math.pi)
            out.append(_xform(v("talk") if i % 4 in (0, 1) else b, dy=2 * abs(t), sy=1 + 0.012 * t))
    elif state == "sleep":
        for i in range(16):
            t = math.sin(i / 16 * 2 * math.pi)
            out.append(_xform(v("sleep"), sy=1 - 0.03 * t, rot=-8 if "sleep" not in imgs else 0))
    elif state == "wave":
        for i in range(8):
            t = math.sin(i / 8 * 2 * math.pi)
            out.append(_xform(v("wave"), dy=2 * abs(t), rot=6 * t))
    elif state == "happy":
        for i in range(10):
            t = abs(math.sin(i / 10 * math.pi))
            out.append(_xform(v("happy"), dy=16 * t, sy=1 + 0.05 * t, sx=1 - 0.03 * t))
    elif state == "think":
        for i in range(12):
            t = math.sin(i / 12 * 2 * math.pi)
            out.append(_xform(v("think"), rot=3 * t, sy=1 - 0.015 * t))
    elif state == "drag":
        for i in range(8):
            t = math.sin(i / 8 * 2 * math.pi)
            out.append(_xform(v("drag"), sy=1.06, sx=0.97, rot=7 * t, dy=-4))
    else:
        raise ValueError(f"unknown state {state!r}")
    if facing < 0:
        out = [f.transpose(Image.FLIP_LEFT_RIGHT) for f in out]
    return out
