"""Make the pet's chibi pictures with ComfyUI (Qwen-Image-Edit-2511 + Lightning 4-step), from her canonical picture.

  python -m pet.make_sprites            # everything (about 10 pictures, a few minutes; stop Ollama first: `ollama stop <model>`)
  python -m pet.make_sprites base talk  # only some

Step 1 draws the chibi (green background), every other picture is an edit of that chibi, so she is the same girl in all of them.
Then the green is removed and the pictures are saved in pet/sprites/. The pet animates them (pet/sprites.py)."""
from __future__ import annotations

import random
import sys
import time
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "pet" / "raw"
OUT = ROOT / "pet" / "sprites"
C = "http://127.0.0.1:8188"
SRC = ROOT / "assets" / "mochi.png"
GREEN = " Plain flat pure bright green (#00FF00) background, no frame, no border, no shadow, no text, no extra objects."
BASE = ("Redraw this girl as an adorable chibi character: super-deformed proportions, a very large head and a tiny body "
        "(about 2.5 heads tall), the whole body visible from the top of her hair to her tiny shoes, standing and facing the viewer "
        "with a sweet smile, hands relaxed at her sides. Keep her pink bob hair with fringe, her pink maid dress with white apron "
        "and aqua trim, her face style and the same anime art style." + GREEN)
KEEP = (" Keep the exact same chibi character, same size, same position in the picture, same outfit, hair, colors, line style and "
        "plain bright green background. Change ONLY the following: ")
EDITS = {
    "talk":  "her mouth is open as if she is happily talking, everything else stays the same.",
    "blink": "her eyes are gently closed, everything else stays the same.",
    "happy": "she cheers with both arms raised up high, eyes closed in a big happy curve, wide open smiling mouth.",
    "sleep": "she is sleeping peacefully: eyes closed, a tiny smile, head tilted a little to the side, arms relaxed.",
    "wave":  "she raises her right hand high and waves hello, with a big friendly smile.",
    "think": "she rests one finger on her chin, eyes looking up and to the side, a thoughtful little pout.",
    "drag":  "she looks surprised: wide eyes, small open mouth, arms stretched up above her head, legs dangling as if lifted.",
    "walk1": "she is walking toward the right side of the picture, seen from a three-quarter side view, left leg stepping forward, arms swinging gently, cheerful smile.",
    "walk2": "she is walking toward the right side of the picture, seen from a three-quarter side view, right leg stepping forward, arms swinging the opposite way, cheerful smile.",
}
SCENE = (" Keep the exact same chibi character: same big head and tiny-body proportions, same pink bob hair, same pink maid dress with white "
         "apron, same line style and colors, and the plain bright green background. The whole scene (her and the furniture) fits fully "
         "inside the picture with some space around it. Change ONLY the following: ")
SCENES = {
    "bed":   "she is sleeping curled up peacefully on a small cute pastel-pink futon bed laid on the floor, her head on a fluffy white pillow, "
             "a soft blanket with little hearts covering her up to the shoulders, eyes closed, a tiny smile, seen from the front.",
    "chair": "she is sitting in a cozy small pink armchair with her hands resting in her lap, dozing with her eyes closed and her head tilted a little "
             "to one side, a sleepy little smile.",
    "read":  "she is sitting in a cozy small pink armchair reading a big open storybook held in both hands, looking down at the book with a happy "
             "interested smile.",
    "tea":   "she is sitting on a round pink floor cushion holding a small teacup with both hands, a little steam rising from it, smiling happily.",
}
EDITS.update({k: SCENE + v for k, v in SCENES.items()})
EDITS.update({
    "dragb":  "she is squirming and giggling as if ticklish: eyes squeezed shut in laughter, wide laughing mouth, arms pulled in against her sides, one leg lifted.",
    "dragf":  "she hops on one foot, off balance, the other foot lifted up, arms flailing out for balance, surprised wide eyes, a small sweat drop.",
    "pokeh":  "she closes her eyes happily with very pink blushing cheeks and a shy happy smile, shoulders scrunched up like she is being gently patted on the head, hands clasped in front.",
    "pokeb":  "she flinches in ticklish surprise: wide eyes, a small 'eek' open mouth, both hands pulled up near her chest, body slightly jumping back.",
    "pokef":  "she lifts one foot and looks down at it, head tilted in puzzlement, one finger on her cheek, hands otherwise relaxed.",
})
ORDER = ["base", "talk", "blink", "happy", "sleep", "wave", "think", "drag", "walk1", "walk2"]


def wf(image: str, prompt: str, seed: int, prefix: str) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "qwen_image_edit_2511_fp8mixed.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors", "strength_model": 1.0}},
        "3": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["2", 0], "shift": 3.0}},
        "4": {"class_type": "CFGNorm", "inputs": {"model": ["3", 0], "strength": 1.0}},
        "5": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors", "type": "qwen_image", "device": "default"}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "7": {"class_type": "LoadImage", "inputs": {"image": image}},
        "8": {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["7", 0], "upscale_method": "lanczos", "megapixels": 1.0, "resolution_steps": 1}},
        "9": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["5", 0], "prompt": prompt, "vae": ["6", 0], "image1": ["8", 0]}},
        "10": {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["5", 0], "prompt": "", "vae": ["6", 0], "image1": ["8", 0]}},
        "11": {"class_type": "VAEEncode", "inputs": {"pixels": ["8", 0], "vae": ["6", 0]}},
        "12": {"class_type": "KSampler", "inputs": {"model": ["4", 0], "seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "euler",
                                                    "scheduler": "simple", "positive": ["9", 0], "negative": ["10", 0], "latent_image": ["11", 0], "denoise": 1.0}},
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["6", 0]}},
        "14": {"class_type": "SaveImage", "inputs": {"images": ["13", 0], "filename_prefix": prefix}},
    }


def key_out_green(im: Image.Image) -> Image.Image:
    """Make the green background transparent, with soft edges and the green fringe removed."""
    a = np.asarray(im.convert("RGB")).astype(np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    dom = g - np.maximum(r, b)                                      # how much greener than the rest
    alpha = np.clip(1.0 - (dom - 25.0) / 70.0, 0.0, 1.0)            # 0 on pure green, 1 on her
    spill = np.clip(dom, 0, None) * (alpha > 0)                     # tone the green down where it bleeds onto her edge
    g2 = g - np.where(dom > 0, np.minimum(dom, 60) * 0.85, 0)
    out = np.dstack([r, np.minimum(g, np.maximum(g2, np.maximum(r, b))), b, alpha * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def generate(name: str, src: Path, prompt: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as f:
        up = httpx.post(f"{C}/upload/image", files={"image": (f"pet_{src.stem}.png", f, "image/png")}, data={"overwrite": "true"}, timeout=60).json()["name"]
    seed = random.randint(1, 2**31)
    r = httpx.post(f"{C}/prompt", json={"prompt": wf(up, prompt, seed, f"mochi_pet_{name}")}, timeout=60)
    r.raise_for_status()
    pid = r.json()["prompt_id"]
    t0 = time.time()
    while True:
        h = httpx.get(f"{C}/history/{pid}", timeout=30).json()
        if pid in h:
            if h[pid]["status"].get("status_str") == "error":
                raise RuntimeError(f"ComfyUI failed on {name}: {str(h[pid]['status'])[:300]}")
            im = next(iter(h[pid]["outputs"].values()))["images"][0]
            path = RAW / f"{name}.png"
            path.write_bytes(httpx.get(f"{C}/view", params=im, timeout=60).content)
            print(f"{name}: ok in {time.time() - t0:.0f}s", flush=True)
            return path
        if time.time() - t0 > 400:
            raise TimeoutError(name)
        time.sleep(2)


def main(names: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for n in names:
        if n == "base":
            raw = generate("base", SRC, BASE)
        else:
            base_raw = RAW / "base.png"
            if not base_raw.is_file():
                raise SystemExit("make 'base' first")
            raw = generate(n, base_raw, EDITS[n] if n in SCENES else KEEP + EDITS[n])
        key_out_green(Image.open(raw)).save(OUT / f"{n}.png")


if __name__ == "__main__":
    main(sys.argv[1:] or ORDER)
