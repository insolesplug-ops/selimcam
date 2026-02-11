#!/usr/bin/env python3
"""
SelimCam v7.0 — PC Simulator
==============================

Desktop simulator with full touch/mouse emulation.

UI: Apple Glassmorphism — dark glass surfaces, Inter font, gold accents.
Sidebar: Slide-over panel from left edge (hover/click to reveal).
Animations: Bounce-scale on touch (no white flashes).
Viewfinder: Ghost mode — clean screen, battery top-right.
Gallery: Swipe gestures, circular thumbnail preview.
Double-tap: 2× digital zoom on viewfinder.

Controls (Keyboard simulates hardware encoder):
  Mouse       Touch interaction (sidebar, buttons, gallery swipe)
  Scroll      Rotary encoder (filter/value change)
  SPACE       Shutter release
  F           Cycle filter
  D           Display mode (PURE / ESSENTIAL / PRO)
  G           Grid toggle
  L           Level toggle
  T           Language (DE/EN)
  TAB         Gallery
  ESC         Settings / Back
  +/-         Zoom in/out
  Double-click  2× zoom toggle

Author: SelimCam Team · License: MIT
"""

import pygame
import pygame.gfxdraw
import time
import math
import gc
import numpy as np
from pathlib import Path
from datetime import datetime
import threading
import queue
from typing import Optional, Tuple, List, Dict
from enum import Enum, auto
import sys
import os

# ---------------------------------------------------------------------------
# Filter system (inline-safe import)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
try:
    from filters import FilterManager
except ImportError:
    # Minimal stub so the file is self-contained
    class _Stub:
        def apply_filter(self, img, name, strength=1.0): return img
        def apply_preset(self, img, name): return img
        def get_available_filters(self): return []
        def get_available_presets(self): return ['none']
    class FilterManager(_Stub):
        def __init__(self): pass

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

SCREEN_W, SCREEN_H = 800, 480          # Landscape like the DSI display
FPS_ACTIVE    = 60
FPS_IDLE      = 8
IDLE_DIM_S    = 30.0                    # Seconds to dim
IDLE_OFF_S    = 90.0                    # Seconds to screen-off

# Colours — Apple-style dark glass
C_GOLD        = (255, 204, 0)
C_WHITE       = (255, 255, 255)
C_GRAY        = (160, 160, 160)
C_DARK_GRAY   = (80, 80, 80)
C_BG_DARK     = (18, 18, 20)
C_GLASS       = (30, 30, 34, 190)      # RGBA
C_GLASS_HOVER = (50, 50, 56, 210)
C_GLASS_LIGHT = (60, 60, 66, 180)
C_SUCCESS     = (52, 199, 89)
C_ERROR       = (255, 59, 48)
C_ORANGE      = (255, 149, 0)
C_OVERLAY     = (0, 0, 0, 200)

SIDEBAR_W     = 260
SIDEBAR_HANDLE_W = 24
PILL_R        = 14
PAD           = 16

PREVIEW_W, PREVIEW_H = 640, 480        # Camera preview
PROXY_SCALE   = 0.25                    # Proxy filter scale factor

SHUTTER_SPEEDS = ["AUTO","1/30","1/60","1/125","1/250","1/500","1/1000","1/2000","1/4000"]
ISO_VALUES     = [100, 200, 400, 800, 1600, 3200, 6400]
FILTER_PRESETS = ["none","vintage","bw","vivid","portrait"]

# ═══════════════════════════════════════════════════════════════════════════
# LOCALISATION
# ═══════════════════════════════════════════════════════════════════════════

I18N: Dict[str, Dict[str, str]] = {
    'en': {
        'settings':      'Settings',
        'filter':        'Filter',
        'grid':          'Grid',
        'level':         'Level',
        'haptics':       'Haptics',
        'date_stamp':    'Date Stamp',
        'language':      'Language',
        'battery':       'Battery',
        'photos':        'photos',
        'gallery':       'Gallery',
        'no_photos':     'No photos yet',
        'back':          'Back',
        'zoom':          'Zoom',
        'shutter':       'Shutter',
        'iso':           'ISO',
        'format_card':   'Format Card',
        'set_time':      'Set Time/Date',
        'close':         'Press ESC to close',
        'pure':          'PURE',
        'essential':     'ESSENTIAL',
        'pro':           'PRO',
        'saving':        'Saving…',
        'saved':         'Saved!',
        'buffer_busy':   'Buffer busy',
    },
    'de': {
        'settings':      'Einstellungen',
        'filter':        'Filter',
        'grid':          'Raster',
        'level':         'Wasserwaage',
        'haptics':       'Haptik',
        'date_stamp':    'Datumsstempel',
        'language':      'Sprache',
        'battery':       'Batterie',
        'photos':        'Fotos',
        'gallery':       'Galerie',
        'no_photos':     'Noch keine Fotos',
        'back':          'Zurück',
        'zoom':          'Zoom',
        'shutter':       'Verschluss',
        'iso':           'ISO',
        'format_card':   'Karte formatieren',
        'set_time':      'Zeit/Datum',
        'close':         'ESC zum Schließen',
        'pure':          'PUR',
        'essential':     'ESSENTIAL',
        'pro':           'PRO',
        'saving':        'Speichert…',
        'saved':         'Gespeichert!',
        'buffer_busy':   'Puffer belegt',
    },
}

# ═══════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════

class Scene(Enum):
    CAMERA   = auto()
    GALLERY  = auto()
    SETTINGS = auto()

class DisplayMode(Enum):
    PURE      = auto()      # 100 % image, nothing else
    ESSENTIAL = auto()      # Battery + photo count
    PRO       = auto()      # + ISO, filter name, histogram

class HapticLevel(Enum):
    OFF  = "OFF"
    LOW  = "LOW"
    HIGH = "HIGH"

# ═══════════════════════════════════════════════════════════════════════════
# UTILITY DRAWING
# ═══════════════════════════════════════════════════════════════════════════

def make_glass(w: int, h: int, rgba=(30, 30, 34, 190), radius=14) -> pygame.Surface:
    """Create a rounded-rect glass surface."""
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(s, rgba, s.get_rect(), border_radius=radius)
    return s

def draw_rounded_rect(surf, rect, color, radius=14):
    s = pygame.Surface((rect[2], rect[3]), pygame.SRCALPHA)
    pygame.draw.rect(s, color, s.get_rect(), border_radius=radius)
    surf.blit(s, (rect[0], rect[1]))

def lerp(a, b, t):
    return a + (b - a) * max(0.0, min(1.0, t))

def ease_out_back(t):
    c1 = 1.70158; c3 = c1 + 1
    return 1 + c3 * pow(t - 1, 3) + c1 * pow(t - 1, 2)

# ═══════════════════════════════════════════════════════════════════════════
# APP STATE
# ═══════════════════════════════════════════════════════════════════════════

class AppState:
    def __init__(self):
        # Scene
        self.scene = Scene.CAMERA

        # Camera params
        self.shutter_idx   = 4          # 1/250
        self.iso_idx       = 2          # 400
        self.filter_idx    = 0
        self.zoom_level    = 1.0        # 1.0 – 4.0

        # Display
        self.display_mode  = DisplayMode.ESSENTIAL

        # Overlays
        self.grid_on       = False
        self.level_on      = False
        self.date_stamp_on = True

        # Settings
        self.lang          = 'en'
        self.haptic_level  = HapticLevel.HIGH

        # Power / idle
        self.last_input    = time.perf_counter()
        self.screen_on     = True
        self.target_fps    = FPS_ACTIVE

        # Sidebar
        self.sidebar_open  = False
        self.sidebar_anim  = 0.0       # 0=closed, 1=fully open

        # Gallery
        self.photo_dir     = Path("./selimcam_photos")
        self.photo_dir.mkdir(exist_ok=True)
        self.gallery_imgs: List[Path] = []
        self.gallery_idx   = 0
        self.gallery_offset_x = 0.0     # For swipe
        self.refresh_gallery()

        # Animations
        self.shutter_flash  = 0.0
        self.freeze_until   = 0.0       # Freeze-frame timestamp
        self.bounce_targets: Dict[str, float] = {}   # key → start time

        # Toast
        self.toast_text     = ""
        self.toast_time     = 0.0

        # Buffer busy indicator
        self.buffer_busy    = False

        # Gyro mock
        self.gyro_angle     = 0.0

        # Settings menu
        self.settings_sel   = 0
        self.settings_scroll = 0.0

        # Filter manager
        self.filter_manager = FilterManager()

    def t(self, key: str) -> str:
        return I18N.get(self.lang, I18N['en']).get(key, key)

    def toggle_lang(self):
        self.lang = 'de' if self.lang == 'en' else 'en'

    def current_filter(self) -> str:
        return FILTER_PRESETS[self.filter_idx]

    def refresh_gallery(self):
        self.gallery_imgs = sorted(self.photo_dir.glob("IMG_*.jpg"), reverse=True)

    def wake(self):
        self.last_input = time.perf_counter()
        self.screen_on  = True
        self.target_fps = FPS_ACTIVE

    def start_bounce(self, key: str):
        self.bounce_targets[key] = time.perf_counter()

    def get_bounce_scale(self, key: str) -> float:
        t0 = self.bounce_targets.get(key)
        if t0 is None:
            return 1.0
        elapsed = time.perf_counter() - t0
        if elapsed > 0.15:
            del self.bounce_targets[key]
            return 1.0
        # Quick scale-down then back
        progress = elapsed / 0.15
        if progress < 0.4:
            return lerp(1.0, 0.93, progress / 0.4)
        else:
            return lerp(0.93, 1.0, (progress - 0.4) / 0.6)

# ═══════════════════════════════════════════════════════════════════════════
# DATE STAMP ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class DateStamper:
    def __init__(self, font):
        self.font = font

    def stamp(self, surface: pygame.Surface) -> pygame.Surface:
        out = surface.copy()
        text = datetime.now().strftime("%d.%m.%Y  %H:%M")
        shadow = self.font.render(text, True, (0, 0, 0))
        main   = self.font.render(text, True, (255, 255, 255))
        w, h   = out.get_size()
        sr = shadow.get_rect(bottomright=(w - 14, h - 12))
        mr = main.get_rect(bottomright=(w - 16, h - 14))
        out.blit(shadow, sr)
        out.blit(main, mr)
        return out

# ═══════════════════════════════════════════════════════════════════════════
# PROXY FILTER RENDERER
# ═══════════════════════════════════════════════════════════════════════════

class ProxyFilterRenderer:
    """Apply filter on a downscaled proxy frame, then upscale — saves 75 %+ CPU."""
    def __init__(self, fm: FilterManager, target_w: int, target_h: int):
        self.fm = fm
        self.tw = target_w
        self.th = target_h
        self.pw = max(80, int(target_w * PROXY_SCALE))
        self.ph = max(60, int(target_h * PROXY_SCALE))

    def apply(self, surf: pygame.Surface, preset: str) -> pygame.Surface:
        if preset == "none":
            return surf
        proxy = pygame.transform.scale(surf, (self.pw, self.ph))
        arr = pygame.surfarray.array3d(proxy)          # (w, h, 3)
        arr = np.transpose(arr, (1, 0, 2))             # (h, w, 3)
        filtered = self.fm.apply_preset(arr, preset)
        filtered = np.transpose(filtered, (1, 0, 2))   # (w, h, 3)
        fs = pygame.surfarray.make_surface(filtered)
        return pygame.transform.smoothscale(fs, (self.tw, self.th))

# ═══════════════════════════════════════════════════════════════════════════
# ASYNC PHOTO SAVER
# ═══════════════════════════════════════════════════════════════════════════

class AsyncPhotoSaver:
    """Background thread to save photos without blocking the UI."""
    def __init__(self, state: AppState, font):
        self.state = state
        self.fm    = state.filter_manager
        self.stamper = DateStamper(font)
        self.q     = queue.Queue(maxsize=8)
        self.worker = threading.Thread(target=self._loop, daemon=True)
        self.worker.start()

    def enqueue(self, surface: pygame.Surface):
        try:
            self.state.buffer_busy = True
            self.q.put_nowait({
                'surface':    surface.copy(),
                'filter':     self.state.current_filter(),
                'stamp':      self.state.date_stamp_on,
                'dir':        self.state.photo_dir,
            })
        except queue.Full:
            pass

    def _loop(self):
        while True:
            task = self.q.get()
            try:
                self._save(task)
            except Exception as e:
                print(f"[SaveErr] {e}")
            finally:
                self.q.task_done()
                if self.q.empty():
                    self.state.buffer_busy = False

    def _save(self, task):
        surf = task['surface']
        fn   = task['filter']
        if fn != 'none':
            arr = np.transpose(pygame.surfarray.array3d(surf), (1,0,2))
            arr = self.fm.apply_preset(arr, fn)
            surf = pygame.surfarray.make_surface(np.transpose(arr, (1,0,2)))
        if task['stamp']:
            surf = self.stamper.stamp(surf)
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
        name = f"IMG_{ts}_{fn}.jpg"
        path = task['dir'] / name
        pygame.image.save(surf, str(path))
        self.state.refresh_gallery()
        self.state.toast_text = self.state.t('saved')
        self.state.toast_time = time.perf_counter()

# ═══════════════════════════════════════════════════════════════════════════
# GESTURE DETECTOR
# ═══════════════════════════════════════════════════════════════════════════

class GestureDetector:
    """Detect double-tap, long-press, and horizontal swipe from mouse events."""
    def __init__(self):
        self.last_click_time = 0.0
        self.last_click_pos  = (0, 0)
        self.drag_start      = None
        self.dragging        = False
        self.drag_dx         = 0

    def on_down(self, pos):
        self.drag_start = pos
        self.dragging   = False
        self.drag_dx    = 0

    def on_motion(self, pos):
        if self.drag_start:
            dx = pos[0] - self.drag_start[0]
            if abs(dx) > 15:
                self.dragging = True
                self.drag_dx  = dx

    def on_up(self, pos) -> dict:
        result = {'type': 'none'}
        now = time.perf_counter()
        if self.dragging and abs(self.drag_dx) > 60:
            result = {'type': 'swipe', 'dx': self.drag_dx}
        elif not self.dragging:
            # Check double-tap
            dt  = now - self.last_click_time
            dist = math.hypot(pos[0]-self.last_click_pos[0], pos[1]-self.last_click_pos[1])
            if dt < 0.35 and dist < 30:
                result = {'type': 'double_tap', 'pos': pos}
                self.last_click_time = 0
            else:
                result = {'type': 'tap', 'pos': pos}
                self.last_click_time = now
                self.last_click_pos  = pos
        self.drag_start = None
        self.dragging   = False
        self.drag_dx    = 0
        return result

# ═══════════════════════════════════════════════════════════════════════════
# SIDEBAR ICON DRAWING  (simple geometric icons, no font dependency)
# ═══════════════════════════════════════════════════════════════════════════

def _icon_grid(surf, cx, cy, sz, color):
    """3×3 grid dots."""
    r = max(2, sz // 8)
    gap = sz // 3
    for dx in (-gap, 0, gap):
        for dy in (-gap, 0, gap):
            pygame.draw.circle(surf, color, (cx+dx, cy+dy), r)

def _icon_level(surf, cx, cy, sz, color):
    """Horizontal bar with bubble."""
    hw = sz // 2
    pygame.draw.line(surf, color, (cx-hw, cy), (cx+hw, cy), 2)
    pygame.draw.circle(surf, color, (cx, cy), max(3, sz//6))

def _icon_haptic(surf, cx, cy, sz, color):
    """Vibration arcs."""
    r = sz // 3
    for i, off in enumerate((-6, 0, 6)):
        pygame.draw.arc(surf, color, (cx-r+off, cy-r, r*2, r*2),
                        -0.6, 0.6, 2)

def _icon_settings(surf, cx, cy, sz, color):
    """Gear-like circle with notches."""
    r = sz // 3
    pygame.draw.circle(surf, color, (cx, cy), r, 2)
    for a in range(0, 360, 45):
        rad = math.radians(a)
        x1 = cx + int(math.cos(rad) * (r-1))
        y1 = cy + int(math.sin(rad) * (r-1))
        x2 = cx + int(math.cos(rad) * (r+4))
        y2 = cy + int(math.sin(rad) * (r+4))
        pygame.draw.line(surf, color, (x1,y1), (x2,y2), 2)

def _icon_filter(surf, cx, cy, sz, color):
    """Overlapping circles."""
    r = sz // 4
    pygame.draw.circle(surf, color, (cx-r//2, cy), r, 2)
    pygame.draw.circle(surf, color, (cx+r//2, cy), r, 2)

SIDEBAR_ICONS = [
    ('grid',     _icon_grid),
    ('level',    _icon_level),
    ('filter',   _icon_filter),
    ('haptics',  _icon_haptic),
    ('settings', _icon_settings),
]

# ═══════════════════════════════════════════════════════════════════════════
# RENDERER
# ═══════════════════════════════════════════════════════════════════════════

class Renderer:
    def __init__(self, screen: pygame.Surface, fonts: dict, state: AppState):
        self.scr   = screen
        self.fonts = fonts
        self.state = state
        self.proxy = ProxyFilterRenderer(state.filter_manager, SCREEN_W, SCREEN_H)
        self.hist_cache      = None
        self.hist_cache_time = 0.0
        # Pre-render sidebar glass
        self._sidebar_bg = make_glass(SIDEBAR_W, SCREEN_H, (20, 20, 24, 220), radius=0)
        # Thumbnail cache
        self._thumb_cache: Optional[pygame.Surface] = None
        self._thumb_path:  Optional[Path] = None

    # ── text helpers ──
    def _txt(self, font_key, text, color, pos, anchor='topleft'):
        f = self.fonts[font_key]
        s = f.render(str(text), True, color)
        r = s.get_rect(**{anchor: pos})
        self.scr.blit(s, r)
        return r

    # ── viewfinder ──
    def render_camera(self, bg: pygame.Surface):
        st = self.state
        now = time.perf_counter()

        # Freeze-frame during shutter
        if now < st.freeze_until:
            return  # Keep last frame on screen

        # Apply proxy filter
        filtered = self.proxy.apply(bg, st.current_filter())

        # Digital zoom crop
        if st.zoom_level > 1.01:
            fw, fh = filtered.get_size()
            zw = int(fw / st.zoom_level)
            zh = int(fh / st.zoom_level)
            cx, cy = fw // 2, fh // 2
            crop = filtered.subsurface((cx - zw//2, cy - zh//2, zw, zh))
            filtered = pygame.transform.smoothscale(crop, (SCREEN_W, SCREEN_H))

        self.scr.blit(filtered, (0, 0))

        # Grid overlay
        if st.grid_on:
            self._draw_grid()

        # Level overlay
        if st.level_on:
            self._draw_level()

        # Ghost UI layers
        if st.display_mode in (DisplayMode.ESSENTIAL, DisplayMode.PRO):
            self._txt('xs', "94 %", C_WHITE, (SCREEN_W - 12, 8), 'topright')
            n = max(0, 9999 - len(st.gallery_imgs))
            self._txt('xs', f"{n} {st.t('photos')}", C_GRAY, (12, 8))

        if st.display_mode == DisplayMode.PRO:
            iso = ISO_VALUES[st.iso_idx]
            self._txt('xs', f"ISO {iso}", C_GOLD, (12, 26))
            fn = st.current_filter().upper()
            if fn != "NONE":
                self._txt('xs', fn, C_GOLD, (SCREEN_W // 2, 8), 'midtop')
            # Mini histogram
            hsurf = self._histogram(filtered)
            if hsurf:
                self.scr.blit(hsurf, (SCREEN_W - 78, 28))

        # Buffer busy dot
        if st.buffer_busy:
            pygame.draw.circle(self.scr, C_ORANGE, (SCREEN_W - 16, SCREEN_H - 16), 5)
        else:
            pygame.draw.circle(self.scr, C_SUCCESS, (SCREEN_W - 16, SCREEN_H - 16), 4)

        # Quick-review thumbnail (bottom-left circle)
        self._draw_thumbnail()

        # Shutter flash (dark → normal, NOT white)
        if st.shutter_flash > 0:
            alpha = int(120 * st.shutter_flash)
            ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, alpha))
            self.scr.blit(ov, (0, 0))
            st.shutter_flash = max(0, st.shutter_flash - 0.08)

        # Toast
        if now - st.toast_time < 1.5:
            alpha = min(255, int(255 * (1.0 - (now - st.toast_time) / 1.5)))
            ts = self.fonts['s'].render(st.toast_text, True, C_WHITE)
            tw, th = ts.get_size()
            pill = make_glass(tw + 24, th + 12, (40, 40, 44, alpha), radius=10)
            px = (SCREEN_W - pill.get_width()) // 2
            py = SCREEN_H - 60
            self.scr.blit(pill, (px, py))
            ts.set_alpha(alpha)
            self.scr.blit(ts, (px + 12, py + 6))

        # Sidebar handle (thin gold line on left edge)
        if not st.sidebar_open:
            pygame.draw.line(self.scr, (*C_GOLD, 100),
                             (2, SCREEN_H//2 - 30), (2, SCREEN_H//2 + 30), 3)

    def _draw_grid(self):
        col = (*C_WHITE, 60)
        x1, x2 = SCREEN_W // 3, 2 * SCREEN_W // 3
        y1, y2 = SCREEN_H // 3, 2 * SCREEN_H // 3
        for x in (x1, x2):
            pygame.draw.line(self.scr, col, (x, 0), (x, SCREEN_H), 1)
        for y in (y1, y2):
            pygame.draw.line(self.scr, col, (0, y), (SCREEN_W, y), 1)

    def _draw_level(self):
        x = SCREEN_W - 24
        cy = SCREEN_H // 2
        ang = self.state.gyro_angle
        col = C_SUCCESS if abs(ang) < 2 else C_WHITE
        pygame.draw.line(self.scr, (*C_WHITE, 80), (x, cy-40), (x, cy+40), 1)
        off = int(ang * 2.5)
        pygame.draw.circle(self.scr, col, (x, cy + off), 5)

    def _draw_thumbnail(self):
        """Circular quick-review button, bottom-left."""
        st = self.state
        r = 26
        cx, cy = 36, SCREEN_H - 36
        pygame.draw.circle(self.scr, (*C_DARK_GRAY, 180), (cx, cy), r + 2)
        if st.gallery_imgs:
            p = st.gallery_imgs[0]
            if p != self._thumb_path:
                try:
                    img = pygame.image.load(str(p))
                    img = pygame.transform.smoothscale(img, (r*2, r*2))
                    self._thumb_cache = img
                    self._thumb_path  = p
                except:
                    self._thumb_cache = None
            if self._thumb_cache:
                # Circular mask via blit
                self.scr.blit(self._thumb_cache, (cx - r, cy - r))
                # Draw circle border
                pygame.draw.circle(self.scr, C_GOLD, (cx, cy), r, 2)
        else:
            pygame.draw.circle(self.scr, C_DARK_GRAY, (cx, cy), r)

    def _histogram(self, surf: pygame.Surface) -> Optional[pygame.Surface]:
        now = time.perf_counter()
        if self.hist_cache and now - self.hist_cache_time < 0.5:
            return self.hist_cache
        try:
            small = pygame.transform.scale(surf, (64, 48))
            arr = pygame.surfarray.array3d(small)
            gray = np.mean(arr, axis=2).astype(np.uint8)
            hist, _ = np.histogram(gray, bins=32, range=(0, 256))
            mx = hist.max()
            if mx == 0: return None
            hist = hist / mx
            hw, hh = 64, 28
            hs = pygame.Surface((hw, hh), pygame.SRCALPHA)
            hs.fill((0, 0, 0, 140))
            bw = hw / 32
            for i, v in enumerate(hist):
                bh = int(v * hh)
                if bh > 0:
                    pygame.draw.rect(hs, (*C_WHITE, 180),
                                     (int(i * bw), hh - bh, max(1, int(bw) - 1), bh))
            self.hist_cache = hs
            self.hist_cache_time = now
            return hs
        except:
            return None

    # ── sidebar ──
    def render_sidebar(self):
        st = self.state
        # Animate
        target = 1.0 if st.sidebar_open else 0.0
        st.sidebar_anim = lerp(st.sidebar_anim, target, 0.18)
        if st.sidebar_anim < 0.01 and not st.sidebar_open:
            return  # Fully hidden

        off_x = int(-SIDEBAR_W * (1.0 - st.sidebar_anim))

        # Dim background
        if st.sidebar_anim > 0.05:
            dim = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            dim.fill((0, 0, 0, int(140 * st.sidebar_anim)))
            self.scr.blit(dim, (0, 0))

        # Glass panel
        self.scr.blit(self._sidebar_bg, (off_x, 0))

        # Gold accent line on right edge
        lx = off_x + SIDEBAR_W - 1
        pygame.draw.line(self.scr, (*C_GOLD, 80), (lx, 0), (lx, SCREEN_H), 1)

        # Header
        self._txt('m', "SelimCam", C_GOLD, (off_x + 20, 16))
        self._txt('xs', f"v7.0 — {st.display_mode.name}", C_GRAY, (off_x + 20, 40))

        # Icon buttons
        y = 80
        icon_sz = 32
        for idx, (key, draw_fn) in enumerate(SIDEBAR_ICONS):
            btn_y = y + idx * 62
            # Determine value text
            val = self._sidebar_value(key)
            # Highlight
            is_active = self._sidebar_active(key)
            bg_col = C_GLASS_HOVER if is_active else C_GLASS
            # Bounce scale
            scale = st.get_bounce_scale(f"sb_{key}")
            bw = int((SIDEBAR_W - 32) * scale)
            bh = int(50 * scale)
            bx = off_x + 16 + ((SIDEBAR_W - 32) - bw) // 2
            by = btn_y + (50 - bh) // 2
            draw_rounded_rect(self.scr, (bx, by, bw, bh), bg_col, 12)
            # Icon
            draw_fn(self.scr, off_x + 40, btn_y + 25, icon_sz,
                     C_GOLD if is_active else C_WHITE)
            # Label
            self._txt('s', st.t(key), C_WHITE, (off_x + 64, btn_y + 10))
            # Value
            if val:
                self._txt('s', val, C_GOLD if is_active else C_GRAY,
                          (off_x + SIDEBAR_W - 24, btn_y + 10), 'topright')

        # Filter carousel (below icons)
        fy = y + len(SIDEBAR_ICONS) * 62 + 10
        self._txt('xs', st.t('filter').upper(), C_GRAY, (off_x + 20, fy))
        fy += 22
        for i, preset in enumerate(FILTER_PRESETS):
            is_cur = (i == st.filter_idx)
            col = C_GOLD if is_cur else C_GRAY
            bg  = (*C_GOLD, 40) if is_cur else (0,0,0,0)
            pw = (SIDEBAR_W - 40) // len(FILTER_PRESETS)
            px = off_x + 16 + i * pw
            draw_rounded_rect(self.scr, (px, fy, pw - 4, 28), bg, 8)
            name = preset[:3].upper() if preset != 'none' else '—'
            self._txt('xs', name, col, (px + pw//2 - 2, fy + 6), 'midtop')

    def _sidebar_value(self, key):
        st = self.state
        if key == 'grid':    return 'ON' if st.grid_on else 'OFF'
        if key == 'level':   return 'ON' if st.level_on else 'OFF'
        if key == 'haptics': return st.haptic_level.value
        if key == 'filter':  return st.current_filter().upper()
        return ''

    def _sidebar_active(self, key):
        st = self.state
        if key == 'grid':   return st.grid_on
        if key == 'level':  return st.level_on
        if key == 'filter': return st.filter_idx != 0
        return False

    # ── gallery ──
    def render_gallery(self):
        st = self.state
        self.scr.fill(C_BG_DARK)

        # Header
        self._txt('l', st.t('gallery'), C_WHITE, (PAD, PAD))
        n = len(st.gallery_imgs)
        self._txt('xs', f"{n} {st.t('photos')}", C_GRAY, (PAD, PAD + 34))

        if not st.gallery_imgs:
            self._txt('m', st.t('no_photos'), C_GRAY,
                      (SCREEN_W // 2, SCREEN_H // 2), 'center')
            return

        # Current image
        idx = st.gallery_idx % n
        try:
            img = pygame.image.load(str(st.gallery_imgs[idx]))
            # Fit to screen
            iw, ih = img.get_size()
            scale = min((SCREEN_W - 40) / iw, (SCREEN_H - 100) / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            img = pygame.transform.smoothscale(img, (nw, nh))
            ix = (SCREEN_W - nw) // 2 + int(st.gallery_offset_x)
            iy = 70 + (SCREEN_H - 100 - nh) // 2
            self.scr.blit(img, (ix, iy))
        except:
            self._txt('s', "Error loading image", C_ERROR,
                      (SCREEN_W//2, SCREEN_H//2), 'center')

        # Index indicator
        self._txt('xs', f"{idx+1}/{n}", C_GRAY,
                  (SCREEN_W // 2, SCREEN_H - 20), 'midbottom')

        # Swipe hint arrows
        if n > 1:
            self._txt('m', "‹", C_GRAY, (8, SCREEN_H // 2), 'midleft')
            self._txt('m', "›", C_GRAY, (SCREEN_W - 8, SCREEN_H // 2), 'midright')

        # Animate swipe offset back to zero
        st.gallery_offset_x *= 0.8
        if abs(st.gallery_offset_x) < 1:
            st.gallery_offset_x = 0

    # ── settings ──
    def render_settings(self):
        st = self.state
        # Dim overlay
        ov = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        ov.fill(C_OVERLAY)
        self.scr.blit(ov, (0, 0))

        # Panel
        pw, ph = 420, 400
        px = (SCREEN_W - pw) // 2
        py = (SCREEN_H - ph) // 2
        draw_rounded_rect(self.scr, (px, py, pw, ph), (25, 25, 30, 240), 18)

        # Title
        self._txt('l', st.t('settings'), C_WHITE, (SCREEN_W // 2, py + 20), 'midtop')

        items = [
            ('filter',      st.current_filter().upper()),
            ('grid',        'ON' if st.grid_on else 'OFF'),
            ('level',       'ON' if st.level_on else 'OFF'),
            ('haptics',     st.haptic_level.value),
            ('date_stamp',  'ON' if st.date_stamp_on else 'OFF'),
            ('language',    st.lang.upper()),
            ('format_card', ''),
        ]

        row_h = 44
        sy = py + 64
        for i, (key, val) in enumerate(items):
            ry = sy + i * row_h
            is_sel = (i == st.settings_sel)
            bg = C_GLASS_HOVER if is_sel else (0, 0, 0, 0)
            draw_rounded_rect(self.scr, (px + 12, ry, pw - 24, row_h - 4), bg, 10)
            self._txt('s', st.t(key), C_WHITE, (px + 24, ry + 12))
            if val:
                self._txt('s', val, C_GOLD if is_sel else C_GRAY,
                          (px + pw - 24, ry + 12), 'topright')

        # Footer
        self._txt('xs', st.t('close'), C_GRAY,
                  (SCREEN_W // 2, py + ph - 16), 'midbottom')

# ═══════════════════════════════════════════════════════════════════════════
# INPUT HANDLER
# ═══════════════════════════════════════════════════════════════════════════

class InputHandler:
    def __init__(self, state: AppState, saver: AsyncPhotoSaver):
        self.state   = state
        self.saver   = saver
        self.gesture = GestureDetector()

    def handle(self, event, bg_surf: pygame.Surface):
        st = self.state
        st.wake()

        # ── Mouse / touch ──
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.gesture.on_down(event.pos)
            # Sidebar handle click
            if not st.sidebar_open and event.pos[0] < SIDEBAR_HANDLE_W:
                st.sidebar_open = True
                return
            # Close sidebar by clicking outside
            if st.sidebar_open and event.pos[0] > SIDEBAR_W:
                st.sidebar_open = False
                return
            # Sidebar item clicks
            if st.sidebar_open and event.pos[0] < SIDEBAR_W:
                self._sidebar_click(event.pos)
                return
            # Thumbnail click
            if st.scene == Scene.CAMERA:
                dx = event.pos[0] - 36
                dy = event.pos[1] - (SCREEN_H - 36)
                if math.hypot(dx, dy) < 30:
                    st.scene = Scene.GALLERY
                    return

        if event.type == pygame.MOUSEMOTION:
            self.gesture.on_motion(event.pos)

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            g = self.gesture.on_up(event.pos)
            if g['type'] == 'double_tap' and st.scene == Scene.CAMERA:
                # Toggle 2× zoom
                st.zoom_level = 1.0 if st.zoom_level > 1.5 else 2.0
            if g['type'] == 'swipe' and st.scene == Scene.GALLERY:
                n = len(st.gallery_imgs)
                if n > 0:
                    if g['dx'] < -60:
                        st.gallery_idx = (st.gallery_idx + 1) % n
                        st.gallery_offset_x = g['dx']
                    elif g['dx'] > 60:
                        st.gallery_idx = (st.gallery_idx - 1) % n
                        st.gallery_offset_x = g['dx']

        # ── Scroll = encoder ──
        if event.type == pygame.MOUSEWHEEL:
            if st.sidebar_open:
                st.filter_idx = (st.filter_idx + event.y) % len(FILTER_PRESETS)
            elif st.scene == Scene.CAMERA:
                st.iso_idx = max(0, min(len(ISO_VALUES)-1, st.iso_idx - event.y))
            elif st.scene == Scene.SETTINGS:
                st.settings_sel = max(0, min(6, st.settings_sel - event.y))

        # ── Keyboard ──
        if event.type != pygame.KEYDOWN:
            return

        key = event.key

        # Global
        if key == pygame.K_ESCAPE:
            if st.scene == Scene.SETTINGS:
                st.scene = Scene.CAMERA
            elif st.scene == Scene.GALLERY:
                st.scene = Scene.CAMERA
            elif st.sidebar_open:
                st.sidebar_open = False
            else:
                st.scene = Scene.SETTINGS
            return

        if key == pygame.K_TAB:
            st.scene = Scene.GALLERY if st.scene == Scene.CAMERA else Scene.CAMERA
            return

        if key == pygame.K_d:
            modes = list(DisplayMode)
            idx = modes.index(st.display_mode)
            st.display_mode = modes[(idx + 1) % len(modes)]
            return

        if key == pygame.K_g:
            st.grid_on = not st.grid_on
            st.start_bounce('sb_grid')

        if key == pygame.K_l:
            st.level_on = not st.level_on
            st.start_bounce('sb_level')

        if key == pygame.K_t:
            st.toggle_lang()

        if key == pygame.K_f:
            st.filter_idx = (st.filter_idx + 1) % len(FILTER_PRESETS)
            st.start_bounce('sb_filter')

        # Camera-specific
        if st.scene == Scene.CAMERA:
            if key == pygame.K_SPACE:
                self._capture(bg_surf)
            elif key == pygame.K_UP:
                st.shutter_idx = (st.shutter_idx + 1) % len(SHUTTER_SPEEDS)
            elif key == pygame.K_DOWN:
                st.shutter_idx = (st.shutter_idx - 1) % len(SHUTTER_SPEEDS)
            elif key == pygame.K_LEFT:
                st.iso_idx = max(0, st.iso_idx - 1)
            elif key == pygame.K_RIGHT:
                st.iso_idx = min(len(ISO_VALUES)-1, st.iso_idx + 1)
            elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                st.zoom_level = min(4.0, st.zoom_level + 0.5)
            elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                st.zoom_level = max(1.0, st.zoom_level - 0.5)

        # Settings navigation
        if st.scene == Scene.SETTINGS:
            if key == pygame.K_UP:
                st.settings_sel = max(0, st.settings_sel - 1)
            elif key == pygame.K_DOWN:
                st.settings_sel = min(6, st.settings_sel + 1)
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                self._toggle_setting()

        # Gallery navigation
        if st.scene == Scene.GALLERY:
            n = len(st.gallery_imgs)
            if n:
                if key == pygame.K_RIGHT:
                    st.gallery_idx = (st.gallery_idx + 1) % n
                    st.gallery_offset_x = -80
                elif key == pygame.K_LEFT:
                    st.gallery_idx = (st.gallery_idx - 1) % n
                    st.gallery_offset_x = 80

    def _sidebar_click(self, pos):
        st = self.state
        y = 80
        for idx, (key, _) in enumerate(SIDEBAR_ICONS):
            btn_y = y + idx * 62
            if btn_y <= pos[1] <= btn_y + 50:
                st.start_bounce(f"sb_{key}")
                if key == 'grid':
                    st.grid_on = not st.grid_on
                elif key == 'level':
                    st.level_on = not st.level_on
                elif key == 'haptics':
                    levels = list(HapticLevel)
                    ci = levels.index(st.haptic_level)
                    st.haptic_level = levels[(ci+1) % len(levels)]
                elif key == 'settings':
                    st.sidebar_open = False
                    st.scene = Scene.SETTINGS
                elif key == 'filter':
                    st.filter_idx = (st.filter_idx + 1) % len(FILTER_PRESETS)
                return
        # Filter carousel click
        fy = y + len(SIDEBAR_ICONS) * 62 + 32
        if fy <= pos[1] <= fy + 28:
            pw = (SIDEBAR_W - 40) // len(FILTER_PRESETS)
            ci = max(0, min(len(FILTER_PRESETS)-1, (pos[0] - 16) // pw))
            st.filter_idx = ci

    def _capture(self, bg_surf):
        st = self.state
        st.shutter_flash = 1.0
        st.freeze_until  = time.perf_counter() + 0.5
        self.saver.enqueue(bg_surf)

    def _toggle_setting(self):
        st = self.state
        keys = ['filter','grid','level','haptics','date_stamp','language','format_card']
        key  = keys[st.settings_sel]
        if key == 'grid':
            st.grid_on = not st.grid_on
        elif key == 'level':
            st.level_on = not st.level_on
        elif key == 'date_stamp':
            st.date_stamp_on = not st.date_stamp_on
        elif key == 'haptics':
            levels = list(HapticLevel)
            ci = levels.index(st.haptic_level)
            st.haptic_level = levels[(ci+1) % len(levels)]
        elif key == 'language':
            st.toggle_lang()
        elif key == 'filter':
            st.filter_idx = (st.filter_idx + 1) % len(FILTER_PRESETS)

# ═══════════════════════════════════════════════════════════════════════════
# POWER MANAGER
# ═══════════════════════════════════════════════════════════════════════════

class PowerManager:
    def __init__(self, state: AppState):
        self.state = state

    def update(self):
        idle = time.perf_counter() - self.state.last_input
        if idle > IDLE_OFF_S:
            self.state.screen_on  = False
            self.state.target_fps = FPS_IDLE
        elif idle > IDLE_DIM_S:
            self.state.target_fps = FPS_IDLE
        else:
            self.state.target_fps = FPS_ACTIVE

# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("SelimCam v7.0 — PC Simulator")
    clock = pygame.time.Clock()

    # Fonts
    font_paths = [
        "static/inter_bold.ttf", "static/inter_regular.ttf",
        "static/Inter-Bold.ttf", "static/Inter-Regular.ttf",
    ]
    bold_path = reg_path = None
    for p in font_paths:
        if os.path.exists(p):
            if 'bold' in p.lower():
                bold_path = p
            else:
                reg_path = p
    try:
        fonts = {
            'xl': pygame.font.Font(bold_path, 36),
            'l':  pygame.font.Font(bold_path, 22),
            'm':  pygame.font.Font(reg_path or bold_path, 16),
            's':  pygame.font.Font(reg_path or bold_path, 13),
            'xs': pygame.font.Font(reg_path or bold_path, 11),
        }
    except:
        fb = pygame.font.SysFont("Arial", 14)
        fonts = {k: fb for k in ('xl', 'l', 'm', 's', 'xs')}

    # State & subsystems
    state   = AppState()
    saver   = AsyncPhotoSaver(state, fonts['s'])
    rend    = Renderer(screen, fonts, state)
    inp     = InputHandler(state, saver)
    power   = PowerManager(state)

    # Background image (test photo or gradient)
    try:
        bg_img = pygame.image.load("test.jpg").convert()
        bg_img = pygame.transform.smoothscale(bg_img, (SCREEN_W, SCREEN_H))
    except:
        bg_img = pygame.Surface((SCREEN_W, SCREEN_H))
        for y in range(SCREEN_H):
            r = int(25 + 35 * (y / SCREEN_H))
            g = int(20 + 25 * (y / SCREEN_H))
            b = int(40 + 50 * (y / SCREEN_H))
            pygame.draw.line(bg_img, (r, g, b), (0, y), (SCREEN_W, y))
        # Add some visual interest
        for _ in range(60):
            x = np.random.randint(0, SCREEN_W)
            y = np.random.randint(0, SCREEN_H)
            r = np.random.randint(1, 4)
            c = np.random.randint(100, 200)
            pygame.draw.circle(bg_img, (c, c, c+30), (x, y), r)

    # Gyro mock timer
    gyro_t = 0.0

    print("═" * 56)
    print("  SelimCam v7.0 — PC Simulator")
    print("═" * 56)
    print("  Mouse/Touch  Sidebar, gallery swipe, double-tap zoom")
    print("  Scroll       Encoder (filter / ISO)")
    print("  SPACE        Capture photo")
    print("  F / D / G / L / T   Filter / Display / Grid / Level / Lang")
    print("  TAB          Gallery  |  ESC  Settings / Back")
    print("  +/-          Zoom     |  ←→↑↓  Navigate")
    print("═" * 56)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            else:
                inp.handle(event, bg_img)

        power.update()

        # Gyro mock
        gyro_t += 0.025
        state.gyro_angle = math.sin(gyro_t) * 6

        if state.screen_on:
            if state.scene == Scene.CAMERA:
                rend.render_camera(bg_img)
            elif state.scene == Scene.GALLERY:
                rend.render_gallery()
            elif state.scene == Scene.SETTINGS:
                rend.render_camera(bg_img)
                rend.render_settings()

            # Sidebar is on top of everything
            rend.render_sidebar()
        else:
            screen.fill((0, 0, 0))

        pygame.display.flip()
        clock.tick(state.target_fps)

    pygame.quit()

if __name__ == "__main__":
    main()
