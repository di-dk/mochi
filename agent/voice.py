"""Mochi's voice: she speaks (Kokoro, local) and listens (faster-whisper, local). Nothing leaves this PC.

Both models run on the CPU on purpose: the GPU is full with the language model and ComfyUI. They load the first time
they are needed, so the app starts as fast as before. Her voice is a blend of Kokoro voices (config `voice.blend`,
e.g. "af_heart:0.6,jf_tebukuro:0.4"): Kokoro has no Asian-accented English voice, so the blend mixes a warm English
voice with a Japanese one to get a softer, cuter tone. It is adjustable in config.local.yaml.
"""
from __future__ import annotations

import io
import re
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "models" / "voice"

DEFAULTS = {
    "enabled": True,
    "blend": "af_bella:0.75,jf_tebukuro:0.25",     # the voice you picked: young, cute, a little Japanese softness
    "speed": 0.97,
    "pitch": 1.06,                   # 1.0 = as is; 1.05 to 1.1 sounds younger (raises pitch, keeps the pace)
    "stt_model": "small",            # faster-whisper size: tiny/base/small/medium (CPU)
    "language": "",                  # "" = detect what you speak (English, Nepali, French, ...)
}


def settings(cfg: dict) -> dict:
    s = dict(DEFAULTS)
    s.update((cfg or {}).get("voice") or {})
    return s


def available() -> tuple[bool, str]:
    """(ok, why not). The packages and the Kokoro files must be there."""
    try:
        import kokoro_onnx  # noqa: F401
        import faster_whisper  # noqa: F401
    except ImportError as e:
        return False, f"voice packages are missing ({e.name}); run ./setup.sh"
    for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        if not (MODEL_DIR / f).is_file():
            return False, f"voice model file {f} is missing in models/voice (run ./setup.sh)"
    return True, ""


_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")


def speakable(text: str) -> str:
    """Her reply as it should be read aloud: no markdown, code, links or emoji."""
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", " link ", t)
    t = re.sub(r"[*_#>~|]+", " ", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    t = _EMOJI.sub("", t)
    t = re.sub(r"€\s?(\d[\d.,]*)", r"\1 euros", t)
    t = re.sub(r"\$\s?(\d[\d.,]*)", r"\1 dollars", t)
    t = re.sub(r"(\d)\s?GB\b", r"\1 gigabytes", t)
    t = re.sub(r"(\d)\s?MB\b", r"\1 megabytes", t)
    t = re.sub(r"(\d)\s?%", r"\1 percent", t)
    t = re.sub(r"\bmochi\b", "Mohchee", t, flags=re.I)         # the phonemizer says "mah-chai"; it is MOH-chee
    t = re.sub(r"\be\.g\.", "for example", t, flags=re.I)
    t = re.sub(r"\bi\.e\.", "that is", t, flags=re.I)
    t = re.sub(r"\s*[—–]\s*", ", ", t)                     # dashes read as a natural pause
    t = re.sub(r"\.{3,}|…", ", ", t)
    return re.sub(r"\s+", " ", t).strip()


def _pcm16k(wav: bytes):
    """A WAV recording as mono float32 at 16 kHz (decoded here, so the PyAV decoder is not needed)."""
    import numpy as np
    import soundfile as sf
    x, sr = sf.read(io.BytesIO(wav), dtype="float32", always_2d=True)
    x = x.mean(axis=1)
    if sr != 16000 and len(x):
        x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * 16000 / sr)), np.arange(len(x)), x).astype("float32")
    return x


class Voice:
    def __init__(self, cfg: dict):
        self.s = settings(cfg)
        self._tts = None
        self._stt = None
        self._style = None
        self._lock = threading.Lock()          # one model run at a time keeps the CPU responsive

    # ------------------------------------------------------------------ speaking
    def _load_tts(self):
        if self._tts is None:
            from kokoro_onnx import Kokoro
            self._tts = Kokoro(str(MODEL_DIR / "kokoro-v1.0.onnx"), str(MODEL_DIR / "voices-v1.0.bin"))
            self._style = self._blend(self.s["blend"])
        return self._tts

    def _blend(self, spec: str):
        parts = []
        for chunk in str(spec).split(","):
            name, _, w = chunk.strip().partition(":")
            if name:
                parts.append((name.strip(), float(w) if w else 1.0))
        total = sum(w for _, w in parts) or 1.0
        style = None
        for name, w in parts:
            v = self._tts.get_voice_style(name) * (w / total)
            style = v if style is None else style + v
        return style

    def speak(self, text: str) -> bytes:
        """WAV bytes for one piece of text (a sentence or two). Empty bytes when there is nothing to say."""
        import soundfile as sf
        t = speakable(text)
        if not re.search(r"\w", t):
            return b""
        with self._lock:
            tts = self._load_tts()
            pitch = float(self.s.get("pitch") or 1.0)
            audio, sr = tts.create(t, voice=self._style, speed=float(self.s["speed"]) / pitch, lang="en-us", trim=True)
        import numpy as np
        if abs(pitch - 1.0) > 0.005:          # play it a little faster = higher voice; the slower speed above cancels the pace
            audio = np.interp(np.arange(0, len(audio), pitch), np.arange(len(audio)), audio).astype(np.float32)
        fade = int(sr * 0.012)
        if len(audio) > 2 * fade:
            audio = audio.copy(); audio[:fade] *= np.linspace(0, 1, fade); audio[-fade:] *= np.linspace(1, 0, fade)
        audio = np.concatenate([audio, np.zeros(int(sr * 0.12), dtype=audio.dtype)])      # natural beat between sentences
        buf = io.BytesIO()
        sf.write(buf, audio, sr, format="WAV", subtype="PCM_16")
        return buf.getvalue()

    # ------------------------------------------------------------------ listening
    def _load_stt(self):
        if self._stt is None:
            from faster_whisper import WhisperModel
            local = MODEL_DIR / f"whisper-{self.s['stt_model']}"      # files fetched by setup (no huggingface client)
            self._stt = WhisperModel(str(local) if local.is_dir() else self.s["stt_model"], device="cpu",
                                     compute_type="int8", download_root=str(MODEL_DIR / "whisper"))
        return self._stt

    def listen(self, wav: bytes) -> str:
        """Text for a recording (WAV, any rate). Quiet or empty audio gives ''."""
        with self._lock:
            stt = self._load_stt()
            segs, _info = stt.transcribe(_pcm16k(wav), language=self.s["language"] or None, vad_filter=True,
                                         beam_size=1, condition_on_previous_text=False)
            text = " ".join(s.text.strip() for s in segs).strip()
        return text

    def warm(self) -> None:
        """Load both models in the background so the first sentence is not slow."""
        def go():
            try:
                with self._lock:
                    self._load_tts()
                    self._load_stt()
            except Exception:  # noqa: BLE001 - the first real use reports the error
                pass
        threading.Thread(target=go, daemon=True).start()
