"""Pet mode: a small animated chibi Mochi that lives on top of your screen (an extra, the chat window stays as it is).

She walks along the bottom of the screen, sleeps, waves and shows emoji. You can drag her anywhere, click her to type, right-click
for the menu (voice, microphone, auto mode, walking, full chat, quit). Her answers appear in a speech bubble; approvals show up
there too, with buttons. It runs inside the same process as the chat window server, so it is the same Mochi, the same memory.

Needs GTK4 + gtk4-layer-shell (see README, "Pet mode"). The launcher sets the environment for it.
"""
from __future__ import annotations

import json
import os
import queue
import random
import subprocess
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402
from gi.repository import Gtk4LayerShell as LS  # noqa: E402

from . import sprites  # noqa: E402

CONF = Path.home() / ".config" / "mochi-pet.json"
CSS = b"""
window.pet { background: transparent; }
.bubble { background: #ffffff; color: #2a1f33; border: 2px solid #e68ab8; border-radius: 18px; padding: 10px 14px; }
.bubble label { color: #2a1f33; font-size: 15px; }
.bubble entry { background: #fbf0f7; color: #2a1f33; border-radius: 10px; min-width: 240px; }
.bubble button { background: #d6337f; color: #ffffff; border-radius: 12px; padding: 2px 10px; border: none; }
.bubble button.quiet { background: #efe4f0; color: #5b4a68; }
.emoji { font-size: 34px; }
popover contents { background: #ffffff; border-radius: 12px; padding: 6px; }
popover button { background: transparent; color: #2a1f33; border: none; padding: 5px 12px; border-radius: 8px; }
popover button:hover { background: #f4eaf4; }
"""
SLEEPING = ("sleep", "bed", "chair")
ONESHOT = ("wave", "happy", "pokeh", "pokeb", "pokef")                 # play once, then back to idle
ACTIVITIES = ("read", "tea")                                           # what she does when left alone for a bit
QUIPS = {"pokeh": ["Hehe, headpats! 💕", "Mmm, that's nice… 🥰"], "pokeb": ["Eek! That tickles! 😆", "Hehe, stop it! 💦"],
         "pokef": ["Hey, those are my feet! 🥺", "What are you looking at? 👀"]}
EMOJI = {"bed": ["💤"], "chair": ["💤"], "read": ["📖"], "tea": ["🍵"], "pokeh": ["💖"], "pokeb": ["😆"], "pokef": ["❓"],
         "dragb": ["😆"], "dragf": ["😵"], "drag": ["😲"], "idle": ["😊", "✨", "🎵", "💖", "🌸", "😋"], "walk": ["🎵", "✨", "🚶"], "happy": ["💖", "🥰", "✨", "🎉"],
         "think": ["💭", "🤔"], "sleep": ["💤"], "wave": ["👋", "💖"], "talk": ["💬"]}
BUBBLE_W, BUBBLE_H = 360, 260


DEBUG = Path(__file__).resolve().parent.parent / "logs" / "pet-debug.log"


def dbg(msg: str) -> None:
    try:
        with DEBUG.open("a") as f:
            f.write(f"{time.strftime('%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d} {msg}\n")
    except OSError:
        pass


def load_conf() -> dict:
    try:
        return json.loads(CONF.read_text())
    except (OSError, ValueError):
        return {}


def save_conf(d: dict) -> None:
    try:
        CONF.parent.mkdir(parents=True, exist_ok=True)
        CONF.write_text(json.dumps(d))
    except OSError:
        pass


def texture(im, scale: float = 1.0) -> Gdk.Texture:
    if abs(scale - 1.0) > 0.01:
        from PIL import Image
        im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
    from gi.repository import GLib as _G
    return Gdk.MemoryTexture.new(im.width, im.height, Gdk.MemoryFormat.R8G8B8A8, _G.Bytes.new(im.tobytes()), im.width * 4)


class Pet:
    def __init__(self, gui, url: str, visible: bool = True):
        self.gui, self.url = gui, url
        self.conf = load_conf()
        self.imgs = sprites.load_images()
        self.clips = sprites.load_clips()                      # real animations, if they were generated (pet/make_anim.py)
        self.cache: dict[tuple[str, int], list[Gdk.Texture]] = {}
        self.state, self.facing, self.frame = "idle", 1, 0
        self.walk_on = self.conf.get("walk", True)
        self.show_emoji = bool(self.conf.get("emoji", False))           # the little floating emoji beside her (off by default)
        self.scale = float(self.conf.get("scale", 1.0))
        self.act_until = 0.0
        self._last_shift = 0.0
        self.sleep_after = float(self.conf.get("sleep_after", 90))      # seconds of being left alone before she naps
        self.speak_on = self.conf.get("voice", False)
        self.mic_on = False
        self.dragging = False
        self.last_active = time.time()
        self.next_event = time.time() + 6
        self.reply = ""
        self.bubble_until = 0.0
        self.want_visible = visible
        self.speaking = False
        self.tts_q: queue.Queue = queue.Queue()
        self.vbuf = ""
        self.mic_proc = None
        self.typing = False
        self.approval = None

    # ------------------------------------------------------------------ windows
    def build(self, app: Gtk.Application) -> None:
        disp = Gdk.Display.get_default()
        css = Gtk.CssProvider(); css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(disp, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        mon = disp.get_monitors().get_item(0)
        g = mon.get_geometry()
        self.sw, self.sh = g.width, g.height
        W, H = self.cw, self.ch
        self.x = min(max(0, int(self.conf.get("x", self.sw // 2))), self.sw - W)
        self.y = min(max(0, int(self.conf.get("y", self.sh - H - 4))), self.sh - H)

        self.win = Gtk.Window(application=app); self.win.add_css_class("pet")
        self._layer(self.win, "mochi-pet", Gtk.Align.START)
        self._fs = False
        self.pic = Gtk.Picture(); self.pic.set_size_request(W, H); self.pic.set_can_shrink(False)
        self.emoji = Gtk.Label(); self.emoji.add_css_class("emoji"); self.emoji.set_halign(Gtk.Align.END); self.emoji.set_valign(Gtk.Align.START)
        self.pic.set_halign(Gtk.Align.START); self.pic.set_valign(Gtk.Align.START)
        ov = Gtk.Overlay(); ov.set_child(self.pic); ov.add_overlay(self.emoji)
        self.emoji.set_visible(self.show_emoji)
        self.win.set_child(ov); self.win.set_default_size(W, H)
        self._wire_pointer(ov)
        self._menu(ov)

        self.bwin = Gtk.Window(application=app); self.bwin.add_css_class("pet")
        self._layer(self.bwin, "mochi-pet-bubble", Gtk.Align.START, bottom=True)
        self.bbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6); self.bbox.add_css_class("bubble")
        self.blabel = Gtk.Label(wrap=True, xalign=0, max_width_chars=34, selectable=False)
        self.brow = Gtk.Box(spacing=6)
        self.entry = Gtk.Entry(placeholder_text="Say something to her…"); self.entry.connect("activate", self._submit)
        self.bbox.append(self.blabel); self.bbox.append(self.brow); self.bbox.append(self.entry)
        self.entry.set_visible(False)
        wrap = Gtk.Box(); wrap.set_size_request(BUBBLE_W, BUBBLE_H); self.bbox.set_valign(Gtk.Align.END); self.bbox.set_halign(Gtk.Align.CENTER)
        wrap.append(self.bbox); self.bbox.set_hexpand(True); self.bbox.set_vexpand(True)
        self.bwin.set_child(wrap); self.bwin.set_default_size(BUBBLE_W, BUBBLE_H)
        self.place()
        self._set_frame()
        if self.want_visible:
            self.win.present()
        GLib.timeout_add(62, self.tick)      # 16 frames per second, like the clips
        threading.Thread(target=self._events, daemon=True).start()
        threading.Thread(target=self._speaker, daemon=True).start()

    def _layer(self, w: Gtk.Window, ns: str, _a, bottom: bool = False) -> None:
        LS.init_for_window(w); LS.set_layer(w, LS.Layer.OVERLAY); LS.set_namespace(w, ns)
        LS.set_anchor(w, LS.Edge.LEFT, True); LS.set_anchor(w, LS.Edge.BOTTOM if bottom else LS.Edge.TOP, True)
        LS.set_keyboard_mode(w, LS.KeyboardMode.NONE)

    @property
    def cw(self) -> int:
        return round(sprites.CANVAS_W * self.scale)

    @property
    def ch(self) -> int:
        return round(sprites.CANVAS_H * self.scale)

    def set_scale(self, k: float) -> None:
        feet = self.y + self.ch                                       # keep her feet where they are
        self.scale = k; self.conf["scale"] = k; save_conf(self.conf)
        self.cache.clear(); self.y = feet - self.ch
        self.pic.set_size_request(self.cw, self.ch); self.win.set_default_size(self.cw, self.ch)
        self.place(); self._set_frame()

    def place(self) -> None:
        bw, bh = (min(self.sw, self.win.get_width()), min(self.sh, self.win.get_height())) if self._fs else (self.sw, self.sh)
        self.x = max(0, min(self.x, bw - self.cw)); self.y = max(0, min(self.y, bh - self.ch))
        if self._fs:
            self.pic.set_margin_start(int(self.x)); self.pic.set_margin_top(int(self.y))
        else:
            LS.set_margin(self.win, LS.Edge.LEFT, int(self.x)); LS.set_margin(self.win, LS.Edge.TOP, int(self.y))
        bx = max(0, min(self.sw - BUBBLE_W, self.x + self.cw // 2 - BUBBLE_W // 2))
        LS.set_margin(self.bwin, LS.Edge.LEFT, int(bx)); LS.set_margin(self.bwin, LS.Edge.BOTTOM, int(self.sh - self.y - sprites.PAD_TOP * self.scale + 14))

    # ------------------------------------------------------------------ pointer: drag, click, right-click
    def _wire_pointer(self, w: Gtk.Widget) -> None:
        self._drag = None
        d = Gtk.GestureDrag(); d.set_button(1)
        d.connect("drag-begin", self._drag_begin); d.connect("drag-update", self._drag_update); d.connect("drag-end", self._drag_end)
        d.connect("cancel", self._drag_cancel); self._wire_drag_motion(w)
        w.add_controller(d)
        c = Gtk.GestureClick(); c.set_button(1); c.connect("pressed", lambda g, n, x, y: n >= 2 and self.toggle_typing()); w.add_controller(c)
        m = Gtk.EventControllerMotion(); m.connect("enter", lambda *_: self.wake()); w.add_controller(m)
        r = Gtk.GestureClick(); r.set_button(3); r.connect("pressed", lambda g, n, x, y: self.pop.popup()); w.add_controller(r)

    def zone(self, y: float) -> str:
        """Which part of her a point is on: head, body or feet (from the standing picture's size)."""
        h = (sprites.SIZE - 8) * self.scale
        top = self.ch - 2 * self.scale - h
        f = (y - top) / h
        return "head" if f < 0.42 else "body" if f < 0.8 else "feet"

    # Dragging. Moving her small window while the mouse is down feeds back: the pointer position GTK reports is relative to that window,
    # which keeps moving, and GTK even repeats stale positions when her picture changes. So for the duration of a drag her (transparent)
    # window is stretched over the whole screen and only her PICTURE moves inside it. The window then never moves, every pointer
    # position is a plain screen position, and she is placed at pointer minus the grab point: exactly under the mouse, no drift.
    def _wire_drag_motion(self, w: Gtk.Widget) -> None:
        m = Gtk.EventControllerMotion(); m.connect("motion", self._drag_motion); w.add_controller(m)

    def _drag_begin(self, g, x, y):
        dbg(f"drag-begin at ({x:.0f},{y:.0f}) win={self.win.get_width()}x{self.win.get_height()} pos=({self.x:.0f},{self.y:.0f})")
        self._drag = {"g": (x, y), "on": False, "ready": False, "t0": time.monotonic()}
        self.last_active = time.time()

    def _drag_update(self, g, ox, oy):
        d = self._drag
        if d and not d["on"] and abs(ox) + abs(oy) >= 5:
            dbg(f"drag starts (offset {ox:.0f},{oy:.0f}) -> fullscreen")
            d["on"] = True; self.dragging = True
            self.set_state({"head": "drag", "body": "dragb", "feet": "dragf"}[self.zone(d["g"][1])])
            self._go_fullscreen(True)

    def _drag_motion(self, c, x, y):
        d = self._drag
        if not d or not d["on"]:
            return
        d["n"] = d.get("n", 0) + 1
        if d["n"] <= 6 or d["n"] % 40 == 0:
            dbg(f"motion #{d['n']} ({x:.0f},{y:.0f}) win={self.win.get_width()}x{self.win.get_height()} ready={d['ready']}")
        if not d["ready"]:                                    # wait until the compositor has made the window screen-sized
            # the compositor may leave out a dock/panel strip (it gave 2560x1400 on a 2560x1440 screen): wait for it to settle
            if self.win.get_width() < self.sw * 0.95 or self.win.get_height() < self.sh * 0.9:
                return
            d["ready"] = True
        self.x, self.y = x - d["g"][0], y - d["g"][1]
        self.place()

    def _go_fullscreen(self, on: bool) -> None:
        if on == self._fs:
            return
        self._fs = on
        self.emoji.set_visible(self.show_emoji and not on)                          # its corner would be the screen's corner while she is dragged
        for edge in (LS.Edge.RIGHT, LS.Edge.BOTTOM):
            LS.set_anchor(self.win, edge, on)
        if on:
            LS.set_margin(self.win, LS.Edge.LEFT, 0); LS.set_margin(self.win, LS.Edge.TOP, 0)
            self.win.set_default_size(self.sw, self.sh)
            self.pic.set_margin_start(int(self.x)); self.pic.set_margin_top(int(self.y))
        else:
            self.pic.set_margin_start(0); self.pic.set_margin_top(0)
            self.win.set_default_size(self.cw, self.ch)
            self.place()

    def _drag_end(self, g, ox, oy):
        dbg(f"drag-end offset=({ox:.0f},{oy:.0f}) on={bool(self._drag and self._drag['on'])}")
        d, self._drag = self._drag, None
        if d and d["on"]:
            self._go_fullscreen(False)
            self.dragging = False; self.set_state("happy")
            self.walk_on = False                                  # dropped where you want her: she stays there
            self.conf.update(x=int(self.x), y=int(self.y), walk=False); save_conf(self.conf)
            self.show_bubble("I'll stay right here 📌", hold=2)
        elif d:
            self.poke(self.zone(d["g"][1]))                   # a single click pokes her; double-click types to her
        self.last_active = time.time()

    def _drag_cancel(self, g, seq):
        dbg("drag CANCELLED by GTK")
        if self._drag:
            self._drag_end(g, 0, 0)

    def poke(self, zone: str) -> None:
        if self.state in SLEEPING:
            self.set_state("wave"); self.show_bubble("Hm? Oh! I fell asleep 😴", hold=3); return
        st = {"head": "pokeh", "body": "pokeb", "feet": "pokef"}[zone]
        self.set_state(st)
        if not self.gui.busy and not self.typing:
            self.show_bubble(random.choice(QUIPS[st]), hold=3)

    def go_sleep(self) -> None:
        self.sleep_grace = time.time() + 4          # the pointer re-entering her window after a menu click must not wake her at once
        scenes = [n for n in ("bed", "chair") if n in self.clips]
        self.set_state(random.choice(scenes) if scenes else "sleep")

    def wake(self):
        if time.time() < getattr(self, "sleep_grace", 0):
            return
        self.last_active = time.time()
        if self.state in SLEEPING:
            self.set_state("wave")

    # ------------------------------------------------------------------ right-click menu
    def _menu(self, parent: Gtk.Widget) -> None:
        self.pop = Gtk.Popover(); self.pop.set_parent(parent); self.pop.set_has_arrow(False)
        self.menu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL); self.pop.set_child(self.menu_box)
        self.items: dict[str, Gtk.Button] = {}
        for key, cb in (("walk", self.toggle_walk), ("talk", self.toggle_typing), ("voice", self.toggle_voice), ("mic", self.toggle_mic), ("wake", self.toggle_wake),
                        ("auto", self.toggle_auto), ("chat", self.open_chat),
                        ("hide", self.hide), ("quit", self.quit)):
            b = Gtk.Button(); b.set_halign(Gtk.Align.FILL); b.get_style_context()
            b.connect("clicked", lambda _b, cb=cb: (self.pop.popdown(), cb()))
            self.menu_box.append(b); self.items[key] = b
        row = Gtk.Box(spacing=4); row.append(Gtk.Label(label="📏 Size"))
        for name, k in (("S", 0.6), ("M", 1.0), ("L", 1.4), ("XL", 1.9)):
            b = Gtk.Button(label=name); b.connect("clicked", lambda _b, k=k: (self.pop.popdown(), self.set_scale(k))); row.append(b)
        self.menu_box.insert_child_after(row, self.items["mic"])
        sl = Gtk.Button(label="😴  Take a nap now"); sl.connect("clicked", lambda _b: (self.pop.popdown(), self.go_sleep()))
        self.menu_box.insert_child_after(sl, row)
        self.pop.connect("map", lambda *_: self._labels())

    def _labels(self) -> None:
        on = lambda v: "ON" if v else "off"
        self.items["talk"].set_label("💬  Type to her")
        self.items["voice"].set_label(f"🔊  Her voice: {on(self.speak_on)}")
        self.items["mic"].set_label(f"🎙  Talk to her (microphone): {on(self.mic_on)}")
        self.items["wake"].set_label(f"👂  Only answer when I say \"Mochi\": {on(self.gui.wake_enabled())}")
        self.items["auto"].set_label(f"⚡  Auto mode: {on(self.gui.auto_mode())}")
        self.items["walk"].set_label("📌  Staying where I put her (click to let her wander)" if not self.walk_on else "🚶  Wandering around (click to make her stay where she is)")
        self.items["chat"].set_label("🗨  Open the full chat")
        self.items["hide"].set_label("🙈  Hide her (back to the chat window)")
        self.items["quit"].set_label("✖  Quit Mochi")

    # ------------------------------------------------------------------ actions
    def toggle_typing(self) -> None:
        self.typing = not self.typing
        LS.set_keyboard_mode(self.bwin, LS.KeyboardMode.ON_DEMAND if self.typing else LS.KeyboardMode.NONE)
        self.entry.set_visible(self.typing)
        if self.typing:
            self.show_bubble(self.reply or "Hi! Type something for me ✨", hold=60)
            self.entry.grab_focus()
        else:
            self.bubble_until = time.time() + 1

    def _submit(self, e: Gtk.Entry) -> None:
        text = e.get_text().strip(); e.set_text("")
        if text:
            self.send(text)
        self.typing = False; self.entry.set_visible(False); LS.set_keyboard_mode(self.bwin, LS.KeyboardMode.NONE)

    def send(self, text: str) -> None:
        self.stop_speaking(); self.reply = ""; self.vbuf = ""
        r = self.gui.send(text, [])
        if r != "ok":
            self.show_bubble({"busy": "One moment, I'm still working on something 💭", "starting": "I'm still waking up…"}.get(r, str(r)), hold=5)

    def toggle_voice(self) -> None:
        if not self.speak_on and not self.gui.voice_status().get("ok"):
            self.show_bubble("My voice isn't set up yet (see the README, Voice).", hold=6); return
        self.speak_on = not self.speak_on; self.conf["voice"] = self.speak_on; save_conf(self.conf)
        if not self.speak_on:
            self.stop_speaking()
        self.show_bubble("I'll read my answers out loud 🔊" if self.speak_on else "Okay, I'll be quiet 🤫", hold=3)

    def toggle_mic(self) -> None:
        if self.mic_on:
            self.mic_on = False
            if self.mic_proc:
                self.mic_proc.terminate()
            self.show_bubble("Microphone off.", hold=3); return
        if not self.gui.voice_status().get("ok"):
            self.show_bubble("Listening isn't set up yet (see the README, Voice).", hold=6); return
        self.mic_on = True; self.speak_on = True
        threading.Thread(target=self._listen, daemon=True).start()
        self.show_bubble('I\'m listening 🎙 Say "Mochi, ..." to talk to me!' if self.gui.wake_enabled() else "I\'m listening 🎙 Just talk to me!", hold=5)

    def toggle_wake(self) -> None:
        on = not self.gui.wake_enabled(); self.gui.set_wake(on)
        self.show_bubble('I will only answer when you say "Mochi" 👂 (then keep talking for a while)' if on else "I'll answer everything I hear 🎙", hold=4)

    def toggle_auto(self) -> None:
        on = not self.gui.auto_mode(); self.gui.set_auto_mode(on)
        self.show_bubble("Auto mode on ⚡ I'll work without asking (except deleting and sensitive things)." if on
                         else "Auto mode off. I'll ask before risky things.", hold=5)

    def toggle_walk(self) -> None:
        """Menu item 'Stay where I drop her': on = she never wanders off, she only stays, naps and reacts where you put her."""
        self.walk_on = not self.walk_on; self.conf["walk"] = self.walk_on; save_conf(self.conf)
        self.set_state("idle")
        self.show_bubble("Okay, I'll stay right here 📌" if not self.walk_on else "Yay, I can wander around again 🚶", hold=3)

    def open_chat(self) -> None:
        webbrowser.open(self.url); self.show_bubble("Opened the full chat in your browser 🗨", hold=3)

    def hide(self) -> None:
        self.win.set_visible(False); self.bwin.set_visible(False); self.want_visible = False

    def show(self) -> None:
        self.want_visible = True; self.win.present(); self.set_state("wave")

    def quit(self) -> None:
        self.stop_speaking(); self.gui.stop(); os._exit(0)

    # ------------------------------------------------------------------ bubble
    def show_bubble(self, text: str, hold: float = 8, buttons: list[tuple[str, str]] | None = None) -> None:
        def go():
            t = text if len(text) < 360 else "…" + text[-340:]
            self.blabel.set_text(t)
            while (c := self.brow.get_first_child()):
                self.brow.remove(c)
            for label, tag in (buttons or []):
                b = Gtk.Button(label=label)
                if tag in ("n", "chat"):
                    b.add_css_class("quiet")
                b.connect("clicked", lambda _b, tag=tag: self._button(tag)); self.brow.append(b)
            if len(text) > 300 and not buttons:
                b = Gtk.Button(label="⤢ Open full chat"); b.connect("clicked", lambda _b: self.open_chat()); self.brow.append(b)
            self.bwin.present(); self.bubble_until = time.time() + hold
        GLib.idle_add(go)

    def _button(self, tag: str) -> None:
        if tag == "chat":
            self.open_chat(); return
        if self.approval:
            self.gui.answer(self.approval, tag); self.approval = None
            self.show_bubble("Okay!" if tag != "n" else "Alright, I won't 💦", hold=2)

    # ------------------------------------------------------------------ animation loop
    def set_state(self, st: str) -> None:
        if st != self.state:
            self.state, self.frame = st, 0
            self._emoji_for(st)

    def _emoji_for(self, st: str) -> None:
        if not self.show_emoji:
            return
        self.emoji.set_text(random.choice(EMOJI[st]) if st in EMOJI and st not in ("talk",) else "")

    def _set_frame(self) -> None:
        key = (self.state, self.facing)
        if key not in self.cache:
            self.cache[key] = [texture(f, self.scale) for f in sprites.frames(self.imgs, self.state, self.facing, self.clips)]
        fr = self.cache[key]
        self.pic.set_paintable(fr[self.frame % len(fr)])

    def tick(self) -> bool:
        now = time.time()
        if self._fs and (self._drag is None or time.monotonic() - self._drag['t0'] > 180):
            self._drag = None; self.dragging = False; self._go_fullscreen(False)     # safety net
        busy = bool(self.gui.busy)
        if not self.dragging:
            if self.speaking or (self.reply and now < self.bubble_until and busy):
                self.set_state("talk")
            elif busy:
                self.set_state("think")
            elif self.state in ("talk", "think"):
                self.set_state("idle")
            elif self.state in SLEEPING and (busy or self.speaking):
                self.set_state("wave")
            n = len(self.cache.get((self.state, self.facing), [])) or 20
            if self.state in ONESHOT and self.frame >= n:
                self.set_state("idle")
            if self.state in ACTIVITIES and (now > self.act_until or busy or self.typing):
                self.set_state("idle")
            if self.state == "idle" and now > self.next_event:
                self.next_event = now + random.uniform(5, 12)
                if self.walk_on and not self.typing and random.random() < 0.55:
                    self.facing = random.choice((-1, 1)); self.walk_until = now + random.uniform(3, 8); self.set_state("walk")
                elif ACTIVITIES and any(a in self.clips for a in ACTIVITIES) and random.random() < 0.4:
                    self.set_state(random.choice([a for a in ACTIVITIES if a in self.clips])); self.act_until = now + random.uniform(15, 30)
                elif random.random() < 0.5:
                    self.set_state("happy")
            if self.state == "walk":
                self.x += self.facing * 5
                if self.x <= 0 or self.x >= self.sw - self.cw:
                    self.facing = -self.facing
                if now > getattr(self, "walk_until", 0) or self.speaking or busy:
                    self.set_state("idle"); self.conf.update(x=int(self.x), y=int(self.y)); save_conf(self.conf)
                self.place()
            if self.state in ("idle", "walk") + ACTIVITIES and now - self.last_active > self.sleep_after and not busy and not self.typing:
                self.go_sleep()
        if self.bwin.get_visible() and now > self.bubble_until and not self.typing and not self.approval:
            self.bwin.set_visible(False)
        if self.show_emoji and self.state in SLEEPING and self.frame % 8 == 0:                    # drifting Zzz while she sleeps
            self.emoji.set_text(("z", "zZ", "zZz", "💤")[(self.frame // 8) % 4])
        self.frame += 1
        self._set_frame()
        return True

    # ------------------------------------------------------------------ what she says (events from the chat engine)
    def _events(self) -> None:
        last = self.gui.bus.base + len(self.gui.bus.events)
        while True:
            for e in self.gui.bus.since(last, 15.0):
                last = max(last, e["id"]); k = e["kind"]
                if k == "token":
                    self.reply += e["text"]; self.last_active = time.time()
                    self.show_bubble(self.reply, hold=60)
                    if self.speak_on:
                        self.vbuf += e["text"]
                        from agent.voice import split_sentences
                        sents, self.vbuf = split_sentences(self.vbuf)
                        for s in sents:
                            self.tts_q.put(s)
                elif k == "done":
                    if self.speak_on and self.vbuf.strip():
                        self.tts_q.put(self.vbuf); self.vbuf = ""
                    self.show_bubble(self.reply or "Done ✨", hold=12 + min(20, len(self.reply) / 25))
                    GLib.idle_add(lambda: self.set_state("happy") and False)
                elif k == "approval":
                    self.approval = e["aid"]
                    self.show_bubble(f"{e['category']}: {e['summary'][:220]}\n\nMay I?", hold=300,
                                     buttons=[("Yes", "y"), ("Always", "a"), ("No", "n"), ("⤢ Chat", "chat")])
                elif k == "file":
                    self.show_bubble("I made a file for you ✨ Open the full chat to see it.", hold=10,
                                     buttons=[("⤢ Open chat", "chat")])
                elif k in ("error", "fatal"):
                    self.show_bubble(f"Oh no: {e.get('text', e.get('message', 'something went wrong'))}"[:300], hold=10)

    # ------------------------------------------------------------------ voice out (sentence by sentence, in the background)
    def _speaker(self) -> None:
        while True:
            text = self.tts_q.get()
            v = self.gui.voice()
            if v is None or not self.speak_on:
                continue
            try:
                wav = v.speak(text)
            except Exception:  # noqa: BLE001
                continue
            if not wav or not self.speak_on:
                continue
            self.speaking = True
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav); path = f.name
            try:
                self.player = subprocess.Popen(["paplay", path]); self.player.wait()
            finally:
                os.unlink(path)
                if self.tts_q.empty():
                    time.sleep(0.25); self.speaking = False

    def stop_speaking(self) -> None:
        while not self.tts_q.empty():
            try:
                self.tts_q.get_nowait()
            except queue.Empty:
                break
        p = getattr(self, "player", None)
        if p and p.poll() is None:
            p.terminate()
        self.speaking = False

    # ------------------------------------------------------------------ voice in (hands-free microphone)
    def _listen(self) -> None:
        import io
        import numpy as np
        import soundfile as sf
        rate, chunk = 16000, 1600                                    # 100 ms
        self.mic_proc = subprocess.Popen(["parecord", "--raw", "--format=s16le", f"--rate={rate}", "--channels=1",
                                          "--latency-msec=50"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        rec, pre, speech, loud, quiet, floor = [], [], False, 0.0, 0.0, 0.008
        while self.mic_on and self.mic_proc.poll() is None:
            raw = self.mic_proc.stdout.read(chunk * 2)
            if len(raw) < chunk * 2:
                break
            x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
            rms = float(np.sqrt(np.mean(x * x)))
            if self.speaking or self.gui.busy:                       # do not hear herself, do not interrupt her work
                rec, pre, speech, loud, quiet = [], [], False, 0.0, 0.0
                continue
            if not speech:
                floor = floor * 0.95 + rms * 0.05; pre.append(x); pre = pre[-4:]
                if rms > max(0.02, floor * 3):
                    loud += 0.1
                    if loud > 0.2:
                        speech, rec, quiet = True, list(pre), 0.0
                else:
                    loud = 0.0
            else:
                rec.append(x)
                quiet = 0.0 if rms > max(0.015, floor * 2) else quiet + 0.1
                if quiet > 0.9:
                    audio, rec, pre, speech, loud = np.concatenate(rec), [], [], False, 0.0
                    if len(audio) > rate * 0.4:
                        buf = io.BytesIO(); sf.write(buf, audio, rate, format="WAV", subtype="PCM_16")
                        try:
                            text = self.gui.accept_speech(self.gui.voice().listen(buf.getvalue()) or "").strip()
                        except Exception:  # noqa: BLE001
                            text = ""
                        if len(text) > 1:
                            GLib.idle_add(lambda t=text: self.send(t) and False)
        self.mic_on = False


def run(gui, url: str, show: bool) -> "Controller":
    """Start the GTK loop on this (main) thread. Returns when the pet process quits. `gui.pet_hook` lets the chat page
    switch the pet on and off."""
    app = Gtk.Application(application_id="be.mochi.pet")
    pet = Pet(gui, url, visible=show)
    gui.pet_hook = lambda cmd: GLib.idle_add(lambda: (pet.show() if cmd == "show" else pet.hide()) and False)

    def on_activate(a):
        pet.build(a); a.hold()
    app.connect("activate", on_activate)
    app.run([])
    return pet
