"""Make real animation clips for the pet with ComfyUI (Wan 2.2 image-to-video + lightx2v 4-step), one per state.

  python -m pet.make_anim              # all states (several minutes each; stop Ollama first: `ollama stop <model>`)
  python -m pet.make_anim walk happy   # only some

Each clip starts from her chibi picture for that pose (pet/sprites/*.png, made by pet.make_sprites) on a green background, so
she is the same girl, the same size, in all of them. The green is then removed and the frames are saved in pet/anim/<state>/.
pet/sprites.py loads them and plays them (and falls back to code-made motion for a state without a clip)."""
from __future__ import annotations

import random
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

from .make_sprites import RAW, ROOT, C, key_out_green

ANIM = ROOT / "pet" / "anim"
RAWV = ROOT / "pet" / "raw_anim"
W, H, LENGTH = 480, 640, 33                       # 3:4 like her pictures; 33 frames at 16 fps is about 2 seconds
STYLE = (" Cute chibi anime character on a completely flat bright green background that stays green and unchanged. The camera does "
         "not move or zoom, she stays in the same place and the same size, her whole body is always visible, smooth natural motion, "
         "the same character and art style.")
NEG = ("blurry, static, still image, distorted face, deformed eyes, extra fingers, bad anatomy, text, watermark, subtitles, different "
       "character, camera zoom, camera movement, background change, new objects, worst quality, low quality")
# state -> (starting picture, what she does)
CLIPS = {
    "idle":  ("base",  "She stands and breathes softly, blinks once, sways very slightly side to side, her hair moves gently, a small sweet smile."),
    "talk":  ("base",  "She talks cheerfully, her mouth moves as if speaking, small friendly nods, expressive eyes, hair bouncing a little."),
    "walk":  ("walk1", "She walks happily in place toward the right in a cute walking cycle: legs stepping, arms swinging, body bobbing, hair bouncing."),
    "sleep": ("sleep", "She sleeps peacefully standing, her chest rises and falls slowly, her head nods very slightly, her hair sways softly, eyes stay closed."),
    "wave":  ("wave",  "She waves her raised hand happily from side to side with a big smile and a small bounce."),
    "happy": ("happy", "She jumps up and down cheering joyfully with her arms up, bouncing with delight, hair flying."),
    "think": ("think", "She taps her chin thoughtfully, her eyes look up and around, her head tilts slowly side to side."),
    "bed":   ("bed",   "She sleeps deeply in her little bed, the blanket rises and falls slowly with her breathing, a tiny smile, her hair stirs softly."),
    "chair": ("chair", "She dozes in the armchair: her head slowly nods down, then lifts a little as if she almost wakes, then settles again, breathing softly."),
    "read":  ("read",  "She reads her storybook, her eyes move along the page, she smiles and turns the page, small happy movements."),
    "tea":   ("tea",   "She sips her tea happily, steam rises from the cup, she blinks and smiles, small contented movements."),
    "dragb": ("dragb", "She squirms and giggles ticklishly, shaking with laughter, body wiggling side to side, eyes squeezed shut."),
    "dragf": ("dragf", "She hops around on one foot off balance, arms flailing, wobbling left and right, then catches herself, surprised."),
    "pokeh": ("pokeh", "She blushes and smiles shyly with her eyes closed, shoulders bouncing happily, a soft contented wiggle."),
    "pokeb": ("pokeb", "She jumps a little in surprise, squeaks, then giggles and wiggles ticklishly, hands near her chest."),
    "pokef": ("pokef", "She looks down at her raised foot puzzled, tilts her head side to side, wiggles her foot, then looks up and smiles."),
    "drag":  ("drag",  "She is held up in the air and surprised, her legs dangle and swing, her body sways left and right, wide eyes."),
}


def wf(image: str, motion: str, seed: int, prefix: str) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors", "strength_model": 1.0}},
        "3": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["2", 0], "shift": 5.0}},
        "4": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors", "weight_dtype": "default"}},
        "5": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["4", 0], "lora_name": "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors", "strength_model": 1.0}},
        "6": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["5", 0], "shift": 5.0}},
        "7": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
        "8": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        "9": {"class_type": "LoadImage", "inputs": {"image": image}},
        "10": {"class_type": "CLIPTextEncode", "inputs": {"text": motion + STYLE, "clip": ["7", 0]}},
        "11": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["7", 0]}},
        "12": {"class_type": "WanImageToVideo", "inputs": {"positive": ["10", 0], "negative": ["11", 0], "vae": ["8", 0], "width": W, "height": H,
                                                          "length": LENGTH, "batch_size": 1, "start_image": ["9", 0]}},
        "13": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["3", 0], "add_noise": "enable", "noise_seed": seed, "steps": 4, "cfg": 1.0,
                                                           "sampler_name": "euler", "scheduler": "simple", "positive": ["12", 0], "negative": ["12", 1],
                                                           "latent_image": ["12", 2], "start_at_step": 0, "end_at_step": 2, "return_with_leftover_noise": "enable"}},
        "14": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["6", 0], "add_noise": "disable", "noise_seed": seed, "steps": 4, "cfg": 1.0,
                                                           "sampler_name": "euler", "scheduler": "simple", "positive": ["12", 0], "negative": ["12", 1],
                                                           "latent_image": ["13", 0], "start_at_step": 2, "end_at_step": 4, "return_with_leftover_noise": "disable"}},
        "15": {"class_type": "VAEDecode", "inputs": {"samples": ["14", 0], "vae": ["8", 0]}},
        "16": {"class_type": "SaveImage", "inputs": {"images": ["15", 0], "filename_prefix": prefix}},
    }


def make(state: str) -> int:
    pose, motion = CLIPS[state]
    src = RAW / f"{pose}.png"
    if not src.is_file():
        raise SystemExit(f"{src} is missing: run python -m pet.make_sprites first")
    with src.open("rb") as f:
        name = httpx.post(f"{C}/upload/image", files={"image": (f"pet_{pose}.png", f, "image/png")}, data={"overwrite": "true"}, timeout=60).json()["name"]
    r = httpx.post(f"{C}/prompt", json={"prompt": wf(name, motion, random.randint(1, 2**31), f"mochi_petanim_{state}")}, timeout=60)
    r.raise_for_status()
    pid, t0 = r.json()["prompt_id"], time.time()
    while True:
        h = httpx.get(f"{C}/history/{pid}", timeout=30).json()
        if pid in h:
            if h[pid]["status"].get("status_str") == "error":
                raise RuntimeError(f"ComfyUI failed on {state}: {str(h[pid]['status'])[:400]}")
            ims = next(iter(h[pid]["outputs"].values()))["images"]
            d, dr = ANIM / state, RAWV / state
            for p in (d, dr):
                p.mkdir(parents=True, exist_ok=True)
                for old in p.glob("*.png"):
                    old.unlink()
            for i, im in enumerate(ims):
                raw = dr / f"{i:03d}.png"
                raw.write_bytes(httpx.get(f"{C}/view", params=im, timeout=60).content)
                key_out_green(Image.open(raw)).save(d / f"{i:03d}.png")
            print(f"{state}: {len(ims)} frames in {time.time() - t0:.0f}s", flush=True)
            return len(ims)
        if time.time() - t0 > 1500:
            raise TimeoutError(state)
        time.sleep(3)


if __name__ == "__main__":
    for s in sys.argv[1:] or list(CLIPS):
        make(s)
