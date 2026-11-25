"""How Mochi looks: one canonical description, used by her persona check, the draw_myself tool and her skills.

Her real portrait is assets/mochi.png (full) and assets/expressions/<mood>.webp (close-ups). Pictures of her are made
by EDITING that portrait (Qwen-Image-Edit), never by describing her to a text-to-image model, because only the
portrait pins down her exact face, colors and style.
"""
from __future__ import annotations

MOODS = ("neutral", "happy", "excited", "thinking", "working", "asking", "worried", "sad", "sleepy")

# What stays identical in every picture of her (appended to every edit instruction).
LOCK = (
    "Keep the exact same girl, drawn the same way: identical face with large round rose-pink eyes with white sparkle "
    "highlights, small nose, light blush and peach skin; the same short chin-length rose-pink bob with raspberry-red "
    "tips and straight bangs; the same pink maid dress with white collar and aqua trim and puffed sleeves, the white "
    "frilly apron with two pink-bow pockets and aqua sash; the same clean bold-outline cel-shaded anime style with "
    "flat pastel colors. Change ONLY what is described."
)

# For the rare case an edit model is not available: tags for a normal anime checkpoint (less exact).
TAGS = (
    "1girl, solo, short bob haircut, rose pink hair, raspberry red hair tips, straight bangs, large pink eyes, "
    "eye sparkles, blush, gentle smile, pink maid dress, puffy sleeves, white collar, aqua trim, white frilly apron, "
    "pink bow pockets, aqua sash, aqua ruffled hem, anime, cel shading, bold outlines, flat colors, masterpiece, best quality"
)

SHEET = """\
MOCHI'S LOOK (canonical; never change these details)
Face: young anime girl; soft round face; large round eyes with rose-pink irises, dark pupils, big white sparkle
  highlights, thin dark lashes; thin soft brows; tiny nose; small gentle closed-mouth smile; light blush on both
  cheeks; light peach skin.
Hair: short chin-length bob, rose pink (about #F49AB5) with deeper raspberry-red (about #E32A58) on the outer strands
  and tips; straight full bangs across the forehead; the ends curve gently inward; no hair accessories.
Dress: pink (about #FC84B4) bodice with a pleated front panel and small white buttons; white Peter Pan collar with aqua
  (about #18D8D8) piping; short puffed pale-pink sleeves with aqua cuffs; full hot-pink skirt with a white lace line
  and an aqua ruffled hem.
Apron: white, frilly scalloped edges with aqua shading, a wide aqua sash at the waist, two big pockets each with a
  small pink bow.
Legs: warm coral-orange tone in this art style.
Style: clean bold-outline cel-shaded anime illustration, flat bright pastel colors, sparkles; background soft pink
  (about #FCCCE4) inside an ornate white scroll frame.
Full portrait props: a slice of strawberry shortcake on an aqua plate in her left hand (viewer's left) and a white and
  aqua teacup with steam in her right.
Moods (close-up faces): relaxed, happy (big open smile), excited (star eyes), thinking (looking up and aside),
  working (determined brows), asking (raised brows, small "oh?"), worried (sweat drop), sad (tears), sleepy (eyes closed, yawn).
Never: realistic or 3D style, glasses, a beret, other hair colors or lengths, other eye colors, dark or gritty looks."""
