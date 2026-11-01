#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nawncher - lanzador de juegos para Linux.

Los datos de usuario viven en ~/.nawncher (o en NAWNCHER_DATA_DIR).
El programa se instala en el sistema o en ~/.local; no es portable.
"""

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

try:
    gi.require_version("PangoCairo", "1.0")
    from gi.repository import PangoCairo
except Exception:  # pragma: no cover - depende de la distribución
    PangoCairo = None

try:
    import cairo
except Exception:  # pragma: no cover - cairo es opcional para el icono
    cairo = None


APP_NAME = "Nawncher"
APP_VERSION = "2.0.0"
APP_ID = "nawncher"
WM_CLASS = "Nawncher"

HOME = os.path.expanduser("~")
DATA = os.path.join(HOME, ".nawncher")
CFG = os.path.join(DATA, "config.json")
STATS = os.path.join(DATA, "stats.json")
GAMES = os.path.join(DATA, "games")
COVERS = os.path.join(DATA, "covers")
CACHE_DIR = os.path.join(DATA, "cache")
ICON_CACHE_DIR = os.path.join(CACHE_DIR, "icons")
LOG_DIR = os.path.join(DATA, "logs")

ICON_SIZE = 512
ICON_RADIUS = 0.22
ICON_CACHE_VERSION = 2
ICON_SOURCE = None
ICON = ""


# ---------------------------------------------------------------------------
# Rutas y datos de usuario
# ---------------------------------------------------------------------------

def _project_prefix():
    """Devuelve /usr, ~/.local o la raíz del árbol fuente."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def find_icon_source():
    """Busca primero un icono personalizado del usuario y luego el instalado."""
    candidates = []
    for name in ("icon.png", "icon.jpg", "icon.jpeg", "icon.webp"):
        candidates.append(os.path.join(DATA, name))

    prefix = _project_prefix()
    for size in ("512x512", "256x256", "128x128", "64x64", "48x48", "32x32"):
        candidates.append(
            os.path.join(prefix, "share", "icons", "hicolor", size, "apps", "nawncher.png")
        )
    candidates.append(os.path.join(prefix, "share", "pixmaps", "nawncher.png"))

    here = os.path.dirname(os.path.abspath(__file__))
    candidates.extend(
        [
            os.path.join(here, "..", "data", "icons", "512x512", "apps", "nawncher.png"),
            os.path.join(here, "data", "icons", "512x512", "apps", "nawncher.png"),
            os.path.join(DATA, "Icon.jpg"),
            os.path.join(DATA, "icon.jpg"),
        ]
    )

    for path in candidates:
        if path and os.path.isfile(path):
            return os.path.abspath(path)
    return None


def _file_digest(path):
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_rounded_icon(source):
    """Genera en ~/.nawncher/cache/icons un PNG de 512 px con esquinas redondeadas."""
    if not source or cairo is None:
        return source
    try:
        digest = _file_digest(source)
    except OSError:
        return source

    key = "%s:%s:%s:%s" % (digest, ICON_SIZE, ICON_RADIUS, ICON_CACHE_VERSION)
    name = "icon-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16] + ".png"
    out = os.path.join(ICON_CACHE_DIR, name)
    if os.path.exists(out):
        return out

    try:
        os.makedirs(ICON_CACHE_DIR, mode=0o700, exist_ok=True)
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(source)
        ratio = min(ICON_SIZE / pixbuf.get_width(), ICON_SIZE / pixbuf.get_height())
        width = max(1, int(round(pixbuf.get_width() * ratio)))
        height = max(1, int(round(pixbuf.get_height() * ratio)))
        pixbuf = pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.HYPER)

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, ICON_SIZE, ICON_SIZE)
        cr = cairo.Context(surface)
        cr.set_antialias(cairo.ANTIALIAS_BEST)
        radius = ICON_SIZE * ICON_RADIUS
        cr.new_sub_path()
        cr.arc(ICON_SIZE - radius, radius, radius, -math.pi / 2, 0)
        cr.arc(ICON_SIZE - radius, ICON_SIZE - radius, radius, 0, math.pi / 2)
        cr.arc(radius, ICON_SIZE - radius, radius, math.pi / 2, math.pi)
        cr.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
        cr.close_path()
        cr.clip()
        Gdk.cairo_set_source_pixbuf(
            cr, pixbuf, (ICON_SIZE - width) / 2, (ICON_SIZE - height) / 2
        )
        cr.paint()
        surface.write_to_png(out)

        for old in os.listdir(ICON_CACHE_DIR):
            if old.startswith("icon-") and old.endswith(".png") and old != name:
                try:
                    os.remove(os.path.join(ICON_CACHE_DIR, old))
                except OSError:
                    pass
        return out
    except Exception:
        return source


def write_json(path, data):
    """Escritura atómica para no corromper config.json o stats.json."""
    folder = os.path.dirname(path)
    os.makedirs(folder, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=4, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def configure_paths(data_dir=None):
    """Fija todas las rutas y crea ~/.nawncher en el primer arranque."""
    global DATA, CFG, STATS, GAMES, COVERS, CACHE_DIR, ICON_CACHE_DIR, LOG_DIR
    global ICON_SOURCE, ICON

    if data_dir:
        DATA = os.path.abspath(os.path.expanduser(data_dir))
    else:
        DATA = os.path.abspath(
            os.path.expanduser(os.environ.get("NAWNCHER_DATA_DIR") or os.path.join(HOME, ".nawncher"))
        )

    CFG = os.path.join(DATA, "config.json")
    STATS = os.path.join(DATA, "stats.json")
    GAMES = os.path.join(DATA, "games")
    COVERS = os.path.join(DATA, "covers")
    CACHE_DIR = os.path.join(DATA, "cache")
    ICON_CACHE_DIR = os.path.join(CACHE_DIR, "icons")
    LOG_DIR = os.path.join(DATA, "logs")

    for folder in (DATA, GAMES, COVERS, CACHE_DIR, ICON_CACHE_DIR, LOG_DIR):
        os.makedirs(folder, mode=0o700, exist_ok=True)

    if not os.path.exists(CFG):
        write_json(CFG, [])
    if not os.path.exists(STATS):
        write_json(STATS, {})

    ICON_SOURCE = find_icon_source()
    ICON = make_rounded_icon(ICON_SOURCE) or ""


def resolve_path(value):
    """Convierte una ruta del config en una ruta absoluta usable."""
    if not value:
        return ""
    value = os.path.expanduser(str(value))
    if os.path.isabs(value):
        return os.path.normpath(value)

    # Formatos nuevos (games/...) y antiguos (Games/...) dentro de ~/.nawncher.
    for base in (DATA, GAMES, os.path.join(DATA, "Games")):
        candidate = os.path.normpath(os.path.join(base, value))
        if os.path.exists(candidate):
            return candidate
    return os.path.normpath(os.path.join(DATA, value))


def rel_path(path):
    """Guarda rutas relativas a ~/.nawncher cuando sea posible."""
    if not path:
        return ""
    absolute = os.path.abspath(os.path.expanduser(str(path)))
    try:
        relative = os.path.relpath(absolute, DATA)
        if not relative.startswith(".."):
            return relative.replace(os.sep, "/")
    except Exception:
        pass
    return absolute


def markup_escape(text):
    try:
        return GLib.markup_escape_text(str(text))
    except Exception:
        return str(text)


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

class RoundedCover(Gtk.DrawingArea):
    def __init__(self, radius=22):
        Gtk.DrawingArea.__init__(self)
        self.radius = radius
        self.set_size_request(460, 620)
        self.pixbuf = None
        self.game_name = ""
        self.connect("draw", self.on_draw)

    def set_pixbuf(self, pixbuf):
        self.pixbuf = pixbuf
        self.game_name = ""
        self.queue_draw()

    def set_name(self, name):
        self.pixbuf = None
        self.game_name = name or ""
        self.queue_draw()

    def clear(self):
        self.pixbuf = None
        self.game_name = ""
        self.queue_draw()

    def _clip(self, cr, width, height):
        radius = self.radius
        cr.new_sub_path()
        cr.arc(width - radius, radius, radius, -math.pi / 2, 0)
        cr.arc(width - radius, height - radius, radius, 0, math.pi / 2)
        cr.arc(radius, height - radius, radius, math.pi / 2, math.pi)
        cr.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
        cr.close_path()
        cr.clip()

    def on_draw(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        cr.save()
        self._clip(cr, width, height)
        if self.pixbuf is not None:
            try:
                pixbuf = self.pixbuf
                if pixbuf.get_width() != width or pixbuf.get_height() != height:
                    pixbuf = pixbuf.scale_simple(
                        width, height, GdkPixbuf.InterpType.BILINEAR
                    )
                Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
                cr.paint()
                cr.restore()
                return False
            except Exception:
                pass

        cr.set_source_rgba(0, 0, 0, 1)
        cr.paint()
        if self.game_name and PangoCairo is not None:
            try:
                layout = self.create_pango_layout(self.game_name)
                layout.set_width(int(width * Pango.SCALE))
                layout.set_alignment(Pango.Alignment.CENTER)
                layout.set_ellipsize(Pango.EllipsizeMode.END)
                layout.set_wrap(Pango.WrapMode.WORD_CHAR)
                layout.set_font_description(Pango.FontDescription("Cantarell 16"))
                _text_width, text_height = layout.get_pixel_size()
                cr.set_source_rgba(1, 1, 1, 1)
                cr.move_to(0, (height - text_height) / 2)
                PangoCairo.show_layout(cr, layout)
            except Exception:
                pass
        cr.restore()
        return False


class CoverAnim(Gtk.DrawingArea):
    def __init__(self, radius=22):
        Gtk.DrawingArea.__init__(self)
        self.radius = radius
        self.set_size_request(460, 620)
        self.pixbufs = []
        self.idx = 0
        self.timeout = None
        self.connect("draw", self.on_draw)
        self.connect("destroy", self.stop)

    def stop(self, *_):
        try:
            if self.timeout is not None:
                GLib.source_remove(self.timeout)
                self.timeout = None
        except Exception:
            self.timeout = None

    def clear(self):
        self.stop()
        self.pixbufs = []
        self.idx = 0
        self.queue_draw()

    def set_pixbufs(self, pixbufs):
        self.stop()
        self.pixbufs = pixbufs or []
        self.idx = 0
        if len(self.pixbufs) > 1:
            try:
                self.timeout = GLib.timeout_add(160, self.tick)
            except Exception:
                self.timeout = None
        self.queue_draw()

    def tick(self):
        if not self.pixbufs:
            return False
        try:
            self.idx = (self.idx + 1) % len(self.pixbufs)
            self.queue_draw()
            return True
        except Exception:
            return False

    def on_draw(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        radius = self.radius
        cr.save()
        cr.new_sub_path()
        cr.arc(width - radius, radius, radius, -math.pi / 2, 0)
        cr.arc(width - radius, height - radius, radius, 0, math.pi / 2)
        cr.arc(radius, height - radius, radius, math.pi / 2, math.pi)
        cr.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
        cr.close_path()
        cr.clip()
        if self.pixbufs and 0 <= self.idx < len(self.pixbufs):
            try:
                pixbuf = self.pixbufs[self.idx]
                if pixbuf.get_width() != width or pixbuf.get_height() != height:
                    pixbuf = pixbuf.scale_simple(
                        width, height, GdkPixbuf.InterpType.BILINEAR
                    )
                Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
                cr.paint()
                cr.restore()
                return False
            except Exception:
                pass
        cr.set_source_rgba(0, 0, 0, 1)
        cr.paint()
        cr.restore()
        return False


class CoverStack(Gtk.Stack):
    def __init__(self, radius=22):
        Gtk.Stack.__init__(self)
        self.radius = radius
        self.set_size_request(460, 620)
        self.set_transition_type(Gtk.StackTransitionType.NONE)
        self.static = RoundedCover(radius)
        self.anim = CoverAnim(radius)
        self.empty = Gtk.DrawingArea()
        self.empty.set_size_request(460, 620)
        self.empty.connect("draw", self.on_empty)
        self.add_named(self.static, "static")
        self.add_named(self.anim, "anim")
        self.add_named(self.empty, "empty")
        self.set_visible_child_name("empty")
        self.show_all()

    def on_empty(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        radius = self.radius
        cr.save()
        cr.new_sub_path()
        cr.arc(width - radius, radius, radius, -math.pi / 2, 0)
        cr.arc(width - radius, height - radius, radius, 0, math.pi / 2)
        cr.arc(radius, height - radius, radius, math.pi / 2, math.pi)
        cr.arc(radius, radius, radius, math.pi, 3 * math.pi / 2)
        cr.close_path()
        cr.clip()
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.restore()
        return False

    def show_empty(self):
        self.anim.stop()
        self.anim.pixbufs = []
        self.anim.idx = 0
        self.static.clear()
        self.set_visible_child_name("empty")

    def clear(self):
        self.show_empty()

    def load(self, path, name=""):
        self.anim.stop()
        self.anim.pixbufs = []
        self.anim.idx = 0
        if not path or not os.path.exists(path):
            self.show_empty()
            return

        extension = os.path.splitext(path.lower())[1]
        if extension == ".webm":
            self.set_visible_child_name("static")
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg:
                tmp = os.path.join(
                    tempfile.gettempdir(),
                    "nawncher_%s_%s.png" % (os.getpid(), int(time.time() * 1000000)),
                )
                try:
                    subprocess.call(
                        [
                            ffmpeg,
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-i",
                            path,
                            "-ss",
                            "00:00:00",
                            "-frames:v",
                            "1",
                            "-y",
                            tmp,
                        ]
                    )
                    if os.path.exists(tmp):
                        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                            tmp, 460, 620, True
                        )
                        self.static.set_pixbuf(pixbuf)
                        return
                except Exception:
                    pass
                finally:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
            self.show_empty()
            return

        if extension in (".webp", ".gif"):
            self.set_visible_child_name("anim")
            pixbufs = []
            try:
                animation = GdkPixbuf.PixbufAnimation.new_from_file(path)
                if animation.is_static_image():
                    pixbufs = [
                        GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 460, 620, True)
                    ]
                else:
                    iterator = animation.get_iter(None)
                    for _ in range(15):
                        pixbuf = iterator.get_pixbuf()
                        try:
                            if pixbuf.get_width() > 460 or pixbuf.get_height() > 620:
                                pixbuf = pixbuf.scale_simple(
                                    460, 620, GdkPixbuf.InterpType.BILINEAR
                                )
                            else:
                                pixbuf = pixbuf.copy()
                        except Exception:
                            pass
                        pixbufs.append(pixbuf)
                        if not iterator.advance():
                            break
            except Exception:
                try:
                    pixbufs = [
                        GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 460, 620, True)
                    ]
                except Exception:
                    pixbufs = []
            self.anim.set_pixbufs(pixbufs)
            return

        self.set_visible_child_name("static")
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 460, 620, True)
            self.static.set_pixbuf(pixbuf)
        except Exception:
            self.show_empty()


# ---------------------------------------------------------------------------
# Ventana principal
# ---------------------------------------------------------------------------

class App(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self)
        self.set_title(APP_NAME)
        self.set_decorated(True)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_default_size(1380, 760)
        self.set_resizable(True)

        if ICON and os.path.exists(ICON):
            try:
                self.set_icon_from_file(ICON)
                Gtk.Window.set_default_icon_from_file(ICON)
            except Exception:
                pass

        try:
            self.set_app_paintable(True)
            screen = self.get_screen()
            visual = screen.get_rgba_visual()
            if visual and screen.is_composited():
                self.set_visual(visual)
        except Exception:
            pass

        self.games = []
        self.cur = None
        self.cur_idx = -1
        self.stats = {}
        self._load_stats()

        css = b"""
        * { font-family: 'Bitcount Prop Single', 'Cantarell', 'DejaVu Sans', sans-serif; font-weight: 400; background-color: transparent; color: #ffffff; }
        window { background-color: transparent; }
        .headerbar { background-color: #151515; background-image: none; border-bottom: 1px solid #2d2d2d; border-top-left-radius: 20px; border-top-right-radius: 20px; }
        .headerbar button { background-color: #2d2d2d; background-image: none; border: 1px solid #3d3d3d; color: #cccccc; border-radius: 14px; font-size: 11pt; }
        .headerbar button:hover { background-color: #3d3d3d; color: #ffffff; }
        .list-pane { background-color: #252525; border-bottom-left-radius: 20px; }
        .right-pane { background-color: #1e1e1e; border-bottom-right-radius: 20px; }
        .game-row { background-color: #252525; padding: 14px 18px; border-radius: 16px; margin: 5px 14px; }
        .game-row:hover { background-color: #2f2f2f; }
        .game-row:selected { background-color: #4a9eff; }
        .play-btn { background-color: #3fb950; background-image: none; color: #ffffff; border: none; padding: 12px 60px; border-radius: 16px; font-size: 16pt; }
        .play-btn:hover { background-color: #4ac95a; }
        .play-btn:disabled { background-color: #2d2d2d; color: #666666; }
        .action-btn { background-color: #2d2d2d; background-image: none; color: #cccccc; border: 1px solid #3d3d3d; padding: 10px 16px; border-radius: 16px; font-size: 11pt; }
        .action-btn:hover { background-color: #3d3d3d; color: #ffffff; }
        .title-label { color: #ffffff; }
        .section-label { color: #cccccc; }
        GtkScrolledWindow { background-color: #252525; border: none; }
        GtkListBox { background-color: #252525; }
        dialog { background-color: #1e1e1e; }
        .dialog-content { background-color: #1e1e1e; border-bottom-left-radius: 20px; border-bottom-right-radius: 20px; }
        GtkDialog { background-color: #1e1e1e; border-radius: 20px; }
        GtkDialog .dialog-vbox { background-color: #1e1e1e; }
        GtkDialog .dialog-action-area { background-color: #1e1e1e; border-top: 1px solid #2d2d2d; padding: 10px 16px; border-bottom-left-radius: 20px; border-bottom-right-radius: 20px; }
        GtkDialog GtkLabel { color: #ffffff; }
        GtkDialog GtkEntry { background-color: #2d2d2d; color: #ffffff; border: 1px solid #3d3d3d; border-radius: 10px; padding: 6px 10px; }
        GtkDialog GtkEntry:focus { border-color: #4a9eff; }
        GtkDialog GtkButton { background-color: #2d2d2d; background-image: none; color: #cccccc; border: 1px solid #3d3d3d; border-radius: 12px; padding: 6px 14px; }
        GtkDialog GtkButton:hover { background-color: #3d3d3d; color: #ffffff; }
        """

        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        screen = Gdk.Screen.get_default()
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.get_style_context().add_class("headerbar")
        header.props.title = APP_NAME
        if ICON and os.path.exists(ICON):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(ICON, 22, 22, True)
                header.pack_start(Gtk.Image.new_from_pixbuf(pixbuf))
            except Exception:
                pass
        header.pack_end(self._build_menu_button())
        self.set_titlebar(header)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.get_style_context().add_class("main-vbox")
        self.add(vbox)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        vbox.pack_start(paned, True, True, 0)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        left.get_style_context().add_class("list-pane")
        left.set_size_request(340, -1)

        label_list = Gtk.Label()
        label_list.get_style_context().add_class("section-label")
        label_list.set_markup("<span size='large'><b>JUEGOS</b></span>")
        label_list.set_halign(Gtk.Align.START)
        label_list.set_margin_start(18)
        label_list.set_margin_top(18)
        label_list.set_margin_bottom(14)
        left.pack_start(label_list, False, False, 0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.get_style_context().add_class("list-pane")
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.lb = Gtk.ListBox()
        self.lb.get_style_context().add_class("list-pane")
        self.lb.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.lb.connect("row-selected", self.on_sel)
        scrolled.add(self.lb)
        left.pack_start(scrolled, True, True, 0)

        buttons = Gtk.Box(spacing=12)
        buttons.set_margin_start(16)
        buttons.set_margin_end(16)
        buttons.set_margin_bottom(16)
        buttons.set_margin_top(16)

        add_button = Gtk.Button(label="+ Añadir")
        add_button.get_style_context().add_class("action-btn")
        add_button.connect("clicked", self.add_game)

        edit_button = Gtk.Button(label="Editar")
        edit_button.get_style_context().add_class("action-btn")
        edit_button.connect("clicked", self.edit_game)

        delete_button = Gtk.Button(label="Eliminar")
        delete_button.get_style_context().add_class("action-btn")
        delete_button.connect("clicked", self.del_game)

        buttons.pack_start(add_button, True, True, 0)
        buttons.pack_start(edit_button, True, True, 0)
        buttons.pack_start(delete_button, True, True, 0)
        left.pack_end(buttons, False, False, 0)
        paned.pack1(left, False, False)

        right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        right.get_style_context().add_class("right-pane")

        middle = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        middle.set_halign(Gtk.Align.CENTER)
        middle.set_valign(Gtk.Align.CENTER)

        self.empty_label = Gtk.Label()
        self.empty_label.get_style_context().add_class("title-label")
        self.empty_label.set_justify(Gtk.Justification.CENTER)
        self.empty_label.set_markup(
            "<span size='40pt' weight='bold'>Selecciona un juego</span>"
        )
        self.empty_label.set_no_show_all(True)
        middle.pack_start(self.empty_label, True, True, 0)

        self.lbl = Gtk.Label()
        self.lbl.get_style_context().add_class("title-label")
        self.lbl.set_justify(Gtk.Justification.CENTER)
        self.lbl.set_markup("")
        self.lbl.set_margin_bottom(28)
        self.lbl.set_no_show_all(True)
        middle.pack_start(self.lbl, False, False, 0)

        self.btnp = Gtk.Button(label="JUGAR")
        self.btnp.get_style_context().add_class("play-btn")
        self.btnp.connect("clicked", self.play)
        self.btnp.set_sensitive(False)
        self.btnp.set_no_show_all(True)
        middle.pack_start(self.btnp, False, False, 0)
        right.pack_start(middle, True, True, 0)

        cover_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        cover_box.set_halign(Gtk.Align.END)
        cover_box.set_valign(Gtk.Align.CENTER)
        cover_box.set_margin_end(90)
        self.img = CoverStack(22)
        self.img.set_no_show_all(True)
        cover_box.pack_start(self.img, False, False, 0)
        self.covbox = cover_box
        self.covbox.set_no_show_all(True)
        right.pack_end(cover_box, False, False, 0)

        paned.pack2(right, True, True)

        self.load()
        self._select_first()
        self.connect("destroy", Gtk.main_quit)
        self.show_all()

    def _build_menu_button(self):
        menu_button = Gtk.MenuButton()
        menu_button.set_tooltip_text("Menú")
        menu_button.set_image(
            Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON)
        )
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_border_width(8)

        data_button = Gtk.Button(label="Abrir carpeta de datos")
        data_button.set_relief(Gtk.ReliefStyle.NONE)
        data_button.connect("clicked", self.open_data_dir)

        about_button = Gtk.Button(label="Acerca de Nawncher")
        about_button.set_relief(Gtk.ReliefStyle.NONE)
        about_button.connect("clicked", self.show_about)

        box.pack_start(data_button, False, False, 0)
        box.pack_start(about_button, False, False, 0)
        box.show_all()
        popover.add(box)
        menu_button.set_popover(popover)
        return menu_button

    def open_data_dir(self, *_):
        try:
            Gtk.show_uri_on_window(
                self, GLib.filename_to_uri(DATA, None), Gtk.get_current_event_time()
            )
            return
        except Exception:
            pass
        try:
            subprocess.Popen(["xdg-open", DATA], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            self.dark_dialog(
                self, APP_NAME, "La carpeta de datos está en:\n" + DATA,
                [("Aceptar", Gtk.ResponseType.OK)],
            )

    def show_about(self, *_):
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name(APP_NAME)
        dialog.set_version(APP_VERSION)
        dialog.set_comments("Lanzador de juegos para Linux")
        dialog.set_authors(["Nawncher"])
        if ICON and os.path.exists(ICON):
            try:
                dialog.set_logo(
                    GdkPixbuf.Pixbuf.new_from_file_at_scale(ICON, 128, 128, True)
                )
            except Exception:
                pass
        dialog.run()
        dialog.destroy()

    def _load_stats(self):
        try:
            with open(STATS, encoding="utf-8") as handle:
                stats = json.load(handle)
            self.stats = stats if isinstance(stats, dict) else {}
        except Exception:
            self.stats = {}

    def show_empty_state(self):
        self.empty_label.show()
        self.lbl.hide()
        self.btnp.hide()
        self.btnp.set_sensitive(False)
        self.img.hide()
        self.covbox.hide()
        self.cur = None
        self.cur_idx = -1
        self.img.show_empty()
        try:
            self.lb.unselect_all()
        except Exception:
            pass

    def _select_first(self):
        try:
            rows = self.lb.get_children()
            if rows:
                self.lb.select_row(rows[0])
            else:
                self.show_empty_state()
        except Exception:
            self.show_empty_state()

    def _select_index(self, index):
        for row in self.lb.get_children():
            if getattr(row, "idx", -1) == index:
                self.lb.select_row(row)
                return

    def show_selected_state(self, name):
        self.empty_label.hide()
        self.lbl.set_markup(
            "<span size='30pt' weight='bold'>%s</span>" % markup_escape(name)
        )
        self.lbl.show()
        self.btnp.set_sensitive(True)
        self.btnp.show()
        self.img.show()
        self.covbox.show()

    def dark_dialog(self, parent, title, message, buttons):
        dialog = Gtk.Dialog(title=title, parent=parent, flags=Gtk.DialogFlags.MODAL)
        dialog.set_default_size(340, 140)
        dialog.set_resizable(False)
        dialog.set_decorated(True)
        try:
            header = Gtk.HeaderBar()
            header.set_show_close_button(True)
            header.props.title = title
            header.get_style_context().add_class("headerbar")
            header.set_decoration_layout("menu:minimize,maximize,close")
            dialog.set_titlebar(header)
        except Exception:
            dialog.get_style_context().add_class("headerbar")

        for text, response in buttons:
            button = dialog.add_button(text, response)
            button.get_style_context().add_class("action-btn")

        content = dialog.get_content_area()
        content.get_style_context().add_class("dialog-content")
        content.set_border_width(22)
        label = Gtk.Label(label=message)
        label.set_line_wrap(True)
        label.set_justify(Gtk.Justification.CENTER)
        content.pack_start(label, True, True, 0)
        try:
            dialog.get_action_area().get_style_context().add_class("dialog-action-area")
        except Exception:
            pass
        dialog.show_all()
        response = dialog.run()
        dialog.destroy()
        return response

    def load(self):
        for child in self.lb.get_children():
            self.lb.remove(child)

        try:
            with open(CFG, encoding="utf-8") as handle:
                games = json.load(handle)
            self.games = games if isinstance(games, list) else []
        except Exception:
            self.games = []
        self._load_stats()

        ordered = []
        for index, game in enumerate(self.games):
            if not isinstance(game, dict):
                continue
            key = game.get("script", "") or game.get("name", "")
            ordered.append((self.stats.get(key, 0), index))
        ordered.sort(reverse=True)

        for _count, index in ordered:
            game = self.games[index]
            row = Gtk.ListBoxRow()
            row.idx = index
            row.get_style_context().add_class("game-row")
            box = Gtk.Box()
            label = Gtk.Label(label=str(game.get("name", "")))
            label.set_halign(Gtk.Align.START)
            label.set_margin_start(6)
            box.pack_start(label, True, True, 0)
            row.add(box)
            self.lb.add(row)
        self.show_all()

    def on_sel(self, _widget, row):
        try:
            if not row:
                self.show_empty_state()
                return
            index = getattr(row, "idx", -1)
            if index < 0 or index >= len(self.games):
                self.show_empty_state()
                return
            self.cur = self.games[index]
            self.cur_idx = index
            name = str(self.cur.get("name", ""))
            self.show_selected_state(name)

            cover = self.cur.get("cover", "")
            if cover:
                cover_path = resolve_path(cover)
                if os.path.exists(cover_path):
                    self.img.load(cover_path, name)
                else:
                    self.img.show_empty()
            else:
                self.img.show_empty()
        except Exception:
            try:
                self.show_empty_state()
            except Exception:
                pass

    def _dialog_folder(self, current):
        if current:
            candidate = resolve_path(current)
            if os.path.isfile(candidate):
                candidate = os.path.dirname(candidate)
            if os.path.isdir(candidate):
                return candidate
        return GAMES

    def pick_file(self, title, parent, folder, patterns):
        dialog = Gtk.FileChooserDialog(
            title=title, parent=parent, action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,
            Gtk.ResponseType.OK,
        )
        dialog.set_modal(True)
        if folder and os.path.isdir(folder):
            dialog.set_current_folder(folder)

        if patterns:
            file_filter = Gtk.FileFilter()
            file_filter.set_name("Archivos compatibles")
            for pattern in patterns:
                file_filter.add_pattern(pattern)
            dialog.add_filter(file_filter)

        all_filter = Gtk.FileFilter()
        all_filter.set_name("Todos los archivos")
        all_filter.add_pattern("*")
        dialog.add_filter(all_filter)

        response = dialog.run()
        filename = dialog.get_filename() if response == Gtk.ResponseType.OK else ""
        dialog.destroy()
        return filename or ""

    def name_dialog(self, title, parent, default_text=""):
        dialog = Gtk.Dialog(title=title, parent=parent, flags=Gtk.DialogFlags.MODAL)
        dialog.set_default_size(320, 130)
        dialog.set_resizable(False)
        dialog.set_decorated(True)
        try:
            header = Gtk.HeaderBar()
            header.set_show_close_button(True)
            header.props.title = title
            header.get_style_context().add_class("headerbar")
            header.set_decoration_layout("menu:minimize,maximize,close")
            dialog.set_titlebar(header)
        except Exception:
            dialog.set_title(title)

        ok = dialog.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
        cancel = dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        ok.get_style_context().add_class("action-btn")
        cancel.get_style_context().add_class("action-btn")

        content = dialog.get_content_area()
        content.get_style_context().add_class("dialog-content")
        content.set_border_width(18)
        entry = Gtk.Entry()
        entry.set_text(default_text)
        entry.set_hexpand(True)
        content.pack_start(entry, True, True, 0)
        try:
            dialog.get_action_area().get_style_context().add_class("dialog-action-area")
        except Exception:
            pass

        dialog.show_all()
        response = dialog.run()
        text = entry.get_text() if response == Gtk.ResponseType.OK else None
        dialog.destroy()
        return text

    def edit_game(self, *_):
        row = self.lb.get_selected_row()
        if not row:
            return
        index = getattr(row, "idx", -1)
        if index < 0 or index >= len(self.games):
            return

        game = dict(self.games[index])
        dialog = Gtk.Dialog("Editar juego", self, Gtk.DialogFlags.MODAL)
        dialog.set_default_size(460, 320)
        dialog.set_resizable(False)
        dialog.set_decorated(True)
        try:
            header = Gtk.HeaderBar()
            header.set_show_close_button(True)
            header.props.title = "Editar juego"
            header.get_style_context().add_class("headerbar")
            header.set_decoration_layout("menu:minimize,maximize,close")
            dialog.set_titlebar(header)
        except Exception:
            dialog.set_title("Editar juego")

        ok = dialog.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
        cancel = dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        ok.get_style_context().add_class("action-btn")
        cancel.get_style_context().add_class("action-btn")

        content = dialog.get_content_area()
        content.get_style_context().add_class("dialog-content")
        content.set_border_width(18)
        content.set_spacing(10)
        try:
            dialog.get_action_area().get_style_context().add_class("dialog-action-area")
        except Exception:
            pass

        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(10)
        grid.set_halign(Gtk.Align.FILL)
        content.pack_start(grid, True, True, 0)

        grid.attach(Gtk.Label(label="Nombre:"), 0, 0, 1, 1)
        entry_name = Gtk.Entry()
        entry_name.set_text(str(game.get("name", "")))
        entry_name.set_hexpand(True)
        grid.attach(entry_name, 1, 0, 2, 1)

        grid.attach(Gtk.Label(label="Script .sh:"), 0, 1, 1, 1)
        entry_script = Gtk.Entry()
        entry_script.set_text(str(game.get("script", "")))
        entry_script.set_hexpand(True)
        grid.attach(entry_script, 1, 1, 1, 1)

        button_script = Gtk.Button(label="Buscar")
        button_script.get_style_context().add_class("action-btn")

        def pick_script(_button):
            filename = self.pick_file(
                "Seleccionar .sh",
                dialog,
                self._dialog_folder(entry_script.get_text()),
                ["*.sh"],
            )
            if filename:
                entry_script.set_text(rel_path(filename))

        button_script.connect("clicked", pick_script)
        grid.attach(button_script, 2, 1, 1, 1)

        grid.attach(Gtk.Label(label="Carátula:"), 0, 2, 1, 1)
        entry_cover = Gtk.Entry()
        entry_cover.set_text(str(game.get("cover", "")))
        entry_cover.set_hexpand(True)
        grid.attach(entry_cover, 1, 2, 1, 1)

        button_cover = Gtk.Button(label="Buscar")
        button_cover.get_style_context().add_class("action-btn")

        def pick_cover(_button):
            filename = self.pick_file(
                "Seleccionar carátula",
                dialog,
                self._dialog_folder(entry_cover.get_text() or entry_script.get_text()),
                ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif", "*.webm"],
            )
            if filename:
                entry_cover.set_text(rel_path(filename))

        button_cover.connect("clicked", pick_cover)
        grid.attach(button_cover, 2, 2, 1, 1)

        dialog.show_all()
        if dialog.run() != Gtk.ResponseType.OK:
            dialog.destroy()
            return

        game["name"] = entry_name.get_text()
        game["script"] = entry_script.get_text()
        game["cover"] = entry_cover.get_text()
        dialog.destroy()

        try:
            with open(CFG, encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, list):
                data = []
            if 0 <= index < len(data):
                data[index] = game
            write_json(CFG, data)
        except Exception:
            pass

        self.load()
        self._select_index(index)

    def add_game(self, *_):
        filename = self.pick_file("Seleccionar archivo .sh", self, GAMES, ["*.sh"])
        if not filename:
            return

        default_name = os.path.basename(os.path.dirname(filename)) or os.path.basename(
            filename
        ).replace(".sh", "")
        name = self.name_dialog("Nombre del juego", self, default_name)
        if name is None or not name.strip():
            return
        name = name.strip()

        cover = self.pick_file(
            "Carátula (.png .jpg .jpeg .webp .gif .webm) (opcional)",
            self,
            GAMES,
            ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.gif", "*.webm"],
        )

        try:
            with open(CFG, encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, list):
                data = []
        except Exception:
            data = []

        new_index = len(data)
        data.append(
            {
                "name": name,
                "script": rel_path(filename),
                "cover": rel_path(cover) if cover else "",
            }
        )
        try:
            write_json(CFG, data)
        except Exception:
            pass

        self.load()
        self._select_index(new_index)

    def del_game(self, *_):
        row = self.lb.get_selected_row()
        if not row:
            return
        index = getattr(row, "idx", -1)
        response = self.dark_dialog(
            self,
            APP_NAME,
            "¿Eliminar este juego de la lista?",
            [
                ("Cancelar", Gtk.ResponseType.CANCEL),
                ("Eliminar", Gtk.ResponseType.YES),
            ],
        )
        if response == Gtk.ResponseType.YES and 0 <= index < len(self.games):
            try:
                self.img.anim.stop()
                self.img.clear()
                with open(CFG, encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, list) and 0 <= index < len(data):
                    data.pop(index)
                write_json(CFG, data)
            except Exception:
                pass
            self.load()
            self._select_first()

    def play(self, *_):
        if not isinstance(self.cur, dict):
            return

        script = self.cur.get("script", "")
        script_path = resolve_path(script)
        if not os.path.exists(script_path):
            self.dark_dialog(
                self,
                APP_NAME,
                "No se encuentra el archivo .sh:\n%s\n\n"
                "Puedes pulsar Editar y volver a seleccionarlo." % script_path,
                [("Aceptar", Gtk.ResponseType.OK)],
            )
            return

        try:
            os.chmod(script_path, 0o755)
        except Exception:
            pass

        key = script or self.cur.get("name", "")
        try:
            self.stats[key] = self.stats.get(key, 0) + 1
            write_json(STATS, self.stats)
        except Exception:
            pass

        current_index = self.cur_idx
        self.load()
        if current_index >= 0:
            self._select_index(current_index)

        name = str(self.cur.get("name", "")) if isinstance(self.cur, dict) else ""
        loading = Gtk.Dialog(title=APP_NAME, parent=self, flags=Gtk.DialogFlags.MODAL)
        loading.set_default_size(340, 110)
        loading.set_resizable(False)
        loading.set_decorated(True)
        try:
            header = Gtk.HeaderBar()
            header.set_show_close_button(False)
            header.props.title = APP_NAME
            header.get_style_context().add_class("headerbar")
            loading.set_titlebar(header)
        except Exception:
            loading.get_style_context().add_class("headerbar")

        content = loading.get_content_area()
        content.get_style_context().add_class("dialog-content")
        content.set_border_width(24)
        label = Gtk.Label(label="Lanzando %s..." % name)
        content.pack_start(label, True, True, 0)
        try:
            loading.get_action_area().get_style_context().add_class("dialog-action-area")
        except Exception:
            pass
        loading.show_all()

        def run_game():
            directory = os.path.dirname(script_path)
            try:
                subprocess.Popen(
                    ["bash", script_path],
                    cwd=directory,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except Exception:
                pass
            GLib.timeout_add_seconds(2, loading.destroy)

        threading.Thread(target=run_game, daemon=True).start()


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog=APP_ID,
        description="Lanzador de juegos para Linux. Los datos se guardan en ~/.nawncher.",
    )
    parser.add_argument(
        "--version", action="version", version="%(prog)s " + APP_VERSION
    )
    parser.add_argument(
        "--data-dir",
        metavar="DIR",
        default=None,
        help="Usa otra carpeta de datos en lugar de ~/.nawncher.",
    )
    parser.add_argument(
        "--init-data",
        action="store_true",
        help="Crea ~/.nawncher y sale (útil para instaladores y pruebas).",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        configure_paths(args.data_dir)
    except OSError as error:
        print("Nawncher: no se pudo crear %s: %s" % (DATA, error), file=sys.stderr)
        return 1

    if args.init_data:
        print(DATA)
        return 0

    try:
        GLib.set_prgname(APP_ID)
        Gdk.set_program_class(WM_CLASS)
    except Exception:
        pass

    window = App()
    window.connect("destroy", Gtk.main_quit)
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
