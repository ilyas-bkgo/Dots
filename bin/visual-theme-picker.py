#!/usr/bin/python3
"""Visual, keyboard-driven theme and wallpaper carousel for Hyprland."""
from __future__ import annotations

import os
import math
import time
import hashlib
import cairo
import subprocess
import sys
from pathlib import Path

# Layer shell must load before GTK/Wayland initializes.
from ctypes import CDLL
layer_lib = Path.home() / ".local/lib/desktop-layer-shell"
if layer_lib.is_dir() and str(layer_lib) not in os.environ.get("LD_LIBRARY_PATH", "").split(":"):
    os.environ["LD_LIBRARY_PATH"] = str(layer_lib) + ":" + os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["GI_TYPELIB_PATH"] = str(layer_lib / "girepository-1.0") + ":" + os.environ.get("GI_TYPELIB_PATH", "")
    os.execv(sys.executable, [sys.executable, *sys.argv])
CDLL(str(layer_lib / "libgtk4-layer-shell.so.0") if layer_lib.is_dir() else "libgtk4-layer-shell.so.0")
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, Gio, Gtk, GLib, Gtk4LayerShell as LayerShell
from PIL import Image, ImageOps

HOME = Path.home()
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))
CACHE = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "visual-theme-picker"
THEME_ROOT = CONFIG / "hypr" / "themes"
WALLPAPER_ROOT = HOME / ".local" / "share" / "wallpapers"
THEMES = ("everforest", "lawson-night", "black-arch", "cyberpunk", "jojo", "jjk", "gruvbox")
PALETTES = {
    "gruvbox": ("#282828", "#d79921", "#ebdbb2"),
    "everforest": ("#323d43", "#a7c080", "#d8caac"),
    "lawson-night": ("#1e1e2e", "#89b4fa", "#cdd6f4"),
    "black-arch": ("#000000", "#989898", "#ffffff"),
    "cyberpunk": ("#10131b", "#ff3b81", "#00e5ff"),
    "jojo": ("#17151b", "#d0a753", "#8196c2"),
    "jjk": ("#11121d", "#b58cff", "#78dce8"),
}
EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".avif"}

CSS = b"""
window.desktop-coverflow, window.desktop-coverflow > * {
    background: transparent;
    box-shadow: none;
}
"""


def thumb_for(path: Path) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / f"{int(hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16], 16):x}.jpg"
    try:
        if target.exists() and target.stat().st_mtime >= path.stat().st_mtime:
            return target
        with Image.open(path) as source:
            source = ImageOps.exif_transpose(source).convert("RGB")
            width, height = source.size
            ratio = 16 / 9
            if width / height > ratio:
                crop_width = int(height * ratio)
                left = (width - crop_width) // 2
                source = source.crop((left, 0, left + crop_width, height))
            else:
                crop_height = int(width / ratio)
                top = (height - crop_height) // 2
                source = source.crop((0, top, width, top + crop_height))
            source.thumbnail((960, 540), Image.Resampling.LANCZOS)
            source.save(target, "JPEG", quality=84, optimize=True)
        return target
    except Exception:
        return path


def theme_preview(theme: str) -> Path | None:
    folder = THEME_ROOT / theme
    candidates = [folder / "wallpaper.jpg", folder / "wallpaper.png", folder / "wallpaper.webp"]
    candidates += sorted(p for p in folder.glob("preview*") if p.suffix.lower() in EXTENSIONS)
    candidates += sorted(p for p in (WALLPAPER_ROOT / theme).iterdir() if p.suffix.lower() in EXTENSIONS) if (WALLPAPER_ROOT / theme).is_dir() else []
    return next((p for p in candidates if p.is_file()), None)


def current_theme() -> str:
    try:
        value = (CONFIG / "hypr" / "theme-current").read_text().strip()
        return value if value in THEMES else THEMES[0]
    except OSError:
        return THEMES[0]


class Carousel(Gtk.Application):
    def __init__(self, mode: str):
        super().__init__(application_id="local.hypr.visual-theme-picker", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.mode = mode
        self.theme = current_theme()
        self.items: list[tuple[str, Path, str]] = []
        if mode == "themes":
            for theme in THEMES:
                preview = theme_preview(theme)
                if preview:
                    self.items.append((theme, preview, "Yuta" if theme == "jjk" else theme))
            try:
                self.index = next(i for i, item in enumerate(self.items) if item[0] == self.theme)
            except StopIteration:
                self.index = 0
        else:
            folder = WALLPAPER_ROOT / self.theme
            active = None
            for link in (CONFIG / "hypr" / "wallpaper-active", CONFIG / "hypr" / "current-wallpaper"):
                try:
                    candidate = Path(link.read_text().strip()) if link.name == "current-wallpaper" else link.resolve()
                    if candidate.is_file():
                        active = candidate.resolve()
                        break
                except (OSError, RuntimeError):
                    pass
            if folder.is_dir():
                for path in sorted(folder.iterdir(), key=lambda p: p.name.lower()):
                    if path.is_file() and path.suffix.lower() in EXTENSIONS:
                        label = path.stem.replace("_", " ").replace("-", " ")
                        self.items.append((str(path), path, label))
            self.index = next((i for i, item in enumerate(self.items) if active and item[1].resolve() == active), 0)

    def do_activate(self):
        if not self.items:
            self.quit(); return
        self.position = float(self.index)
        self.start_position = self.position
        self.target = self.position
        self.started = 0
        self.surfaces = {}
        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_title("Desktop Coverflow")
        self.window.set_decorated(False)
        LayerShell.init_for_window(self.window)
        LayerShell.set_namespace(self.window, "desktop-coverflow")
        LayerShell.set_layer(self.window, LayerShell.Layer.OVERLAY)
        LayerShell.set_keyboard_mode(self.window, LayerShell.KeyboardMode.EXCLUSIVE)
        LayerShell.set_exclusive_zone(self.window, 0)
        for edge in (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT):
            LayerShell.set_anchor(self.window, edge, True)
        self.window.add_css_class("desktop-coverflow")
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.opened = time.monotonic()
        self.closing = None
        self.pending_command = None
        self.reveal = 0.0
        self.window.set_opacity(0.0)
        self.canvas = Gtk.DrawingArea()
        self.canvas.set_draw_func(self.draw)
        self.window.set_child(self.canvas)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key)
        self.window.add_controller(keys)
        click = Gtk.GestureClick()
        click.connect("released", self.clicked)
        self.canvas.add_controller(click)
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.HORIZONTAL)
        scroll.connect("scroll", self.scrolled)
        self.canvas.add_controller(scroll)
        self.canvas.add_tick_callback(self.tick)
        self.window.present()

    def surface(self, path):
        key = str(path)
        if key not in self.surfaces:
            target = thumb_for(path).with_suffix(".png")
            if not target.exists() or target.stat().st_mtime < path.stat().st_mtime:
                with Image.open(thumb_for(path)) as img:
                    img.convert("RGB").save(target)
            self.surfaces[key] = cairo.ImageSurface.create_from_png(str(target))
        return self.surfaces[key]

    def paint_image(self, cr, path, x, y, w, h, alpha=1):
        surface = self.surface(path)
        sw, sh = surface.get_width(), surface.get_height()
        scale = max(w/sw, h/sh)
        cr.save(); cr.rectangle(x,y,w,h); cr.clip()
        cr.translate(x+(w-sw*scale)/2, y+(h-sh*scale)/2)
        cr.scale(scale,scale); cr.set_source_surface(surface,0,0); cr.paint_with_alpha(alpha); cr.restore()

    def draw(self, area, cr, width, height):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0); cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_source_rgba(.02, .02, .04, .22); cr.paint()
        scale = .96 + .04 * self.reveal
        cr.translate(width/2, height/2)
        cr.scale(scale, scale)
        cr.translate(-width/2, -height/2)
        cw, ch = width*.50, height*.52
        cy = height*.47
        # Paint distant cards first, with compressed sides and overlapping edges.
        visible = min(9, len(self.items))
        for offset in sorted(range(-(visible//2), visible-visible//2), key=lambda n: -abs(n+self.target-self.position)):
            relative = offset+self.target-self.position
            index = (int(self.target)+offset) % len(self.items)
            if abs(relative)>4: continue
            distance=abs(relative)
            scale=max(.65,1-distance*.12)
            w=cw*(1 if distance<.05 else max(.28,1-distance*.48))*scale
            h=ch*scale
            x=width/2 + relative*width*.19-w/2; y=cy-h/2
            # Dim opaque previews so desktop windows cannot bleed through them.
            cr.set_source_rgb(.06, .06, .08)
            cr.rectangle(x, y, w, h); cr.fill()
            self.paint_image(cr, self.items[index][1], x, y, w, h)
            cr.set_source_rgba(0, 0, 0, min(.65, distance*.16))
            cr.rectangle(x, y, w, h); cr.fill()
            if distance<.5:
                color=PALETTES.get(self.items[index][0], PALETTES.get(self.theme, ("", "#d79921")))[1]
                rgb=tuple(int(color[i:i+2],16)/255 for i in (1,3,5))
                cr.set_source_rgb(*rgb); cr.set_line_width(3); cr.rectangle(x,y,w,h); cr.stroke()
        cr.select_font_face("Noto Sans",cairo.FONT_SLANT_NORMAL,cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(30); cr.set_source_rgb(.93,.91,.86)
        label=self.items[self.index][2].replace('-', ' ').title()
        ext=cr.text_extents(label); cr.move_to((width-ext.width)/2,cy+ch/2+55); cr.show_text(label)

    def tick(self, widget, clock):
        now = time.monotonic()
        progress = min(1, max(0, (now-self.started)/.32))
        self.position = self.start_position+(self.target-self.start_position)*(1-(1-progress)**3)
        if self.closing is not None:
            phase = min(1, (now-self.closing)/.18)
            self.reveal = (1-phase)**2
            if phase >= 1:
                if self.pending_command:
                    subprocess.Popen(self.pending_command, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.quit()
                return False
        else:
            phase = min(1, (now-self.opened)/.25)
            self.reveal = 1-(1-phase)**3
        self.window.set_opacity(self.reveal)
        if phase < 1 or progress < 1:
            self.canvas.queue_draw()
        return True

    def dismiss(self, command=None):
        if self.closing is None:
            self.pending_command = command
            self.closing = time.monotonic()
            self.canvas.queue_draw()

    def move(self, delta):
        if len(self.items)<2: return
        self.start_position=self.position
        self.target+=delta
        self.index=int(self.target)%len(self.items)
        self.started=time.monotonic(); self.canvas.queue_draw()

    def clicked(self, gesture, count, x, y):
        width=self.canvas.get_width()
        if width*.32<x<width*.68: self.apply()
        else: self.move(-1 if x<width/2 else 1)

    def scrolled(self, controller, dx, dy):
        self.move(1 if (dy or dx)>0 else -1); return True

    def on_key(self, _controller, keyval, _keycode, _state):
        if keyval in (Gdk.KEY_Left, Gdk.KEY_a): self.move(-1); return True
        if keyval in (Gdk.KEY_Right, Gdk.KEY_d): self.move(1); return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space): self.apply(); return True
        if keyval == Gdk.KEY_Escape: self.dismiss(); return True
        return False

    def apply(self):
        name, path, _label = self.items[self.index]
        if self.mode == "themes":
            command = [str(HOME / ".local/bin/switch-theme.sh"), name]
        else:
            command = [str(HOME / ".local/bin/everforest-wallpaper"), "--apply", str(path)]
        self.dismiss(command)


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"themes", "wallpapers"}:
        raise SystemExit("Usage: visual-theme-picker.py themes|wallpapers")
    app = Carousel(sys.argv[1])
    raise SystemExit(app.run(None))


if __name__ == "__main__":
    main()
