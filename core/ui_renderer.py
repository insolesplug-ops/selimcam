"""Shared matte UI renderer for Pi + PC targets (pixel-identical runtime canvas)."""

from __future__ import annotations

import math
import random
import time
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Optional, Tuple

import pygame

from core.app_controller import AppState, Scene

# UI_TOKENS: HOW TO CHANGE: adjust palette and typography tokens globally for premium matte style.
C_BG = (10, 10, 12)
C_PANEL = (20, 20, 24, 234)
C_PANEL_SOFT = (26, 26, 30, 220)
C_TEXT = (236, 236, 238)
C_TEXT_SUB = (144, 144, 150)
C_ACCENT = (255, 204, 0)
C_PRESS = (40, 40, 46, 240)

# UI_LAYOUT: HOW TO CHANGE: tune 4/8/12/16/24 spacing scale and component geometry here.
SP4, SP8, SP12, SP16, SP24 = 4, 8, 12, 16, 24
TOP_H = 72
BOTTOM_H = 108
SIDEBAR_W = 228
HANDLE_W = 16
RADIUS = 12

# UI_MOTION: HOW TO CHANGE: adjust durations/easing for precise Apple-like motion.
PRESS_SCALE = 0.94
PRESS_MS = 100

# UI_TOUCH: HOW TO CHANGE: keep touch targets >= 48 px and swipe thresholds deliberate.
HIT_MIN = 48
SWIPE_THRESHOLD = 28

# UI_TEXT: HOW TO CHANGE: Intel font sizes for hierarchy; heading=Bold, HUD/body=Regular.
TYPE_H1 = 24
TYPE_H2 = 18
TYPE_BODY = 14
TYPE_CAPTION = 12


class UIRenderer:
    def __init__(self, screen: pygame.Surface, width: int, height: int, font_path: Optional[str] = None, use_webcam: bool = False):
        self.screen = screen
        self.w = width
        self.h = height
        self.ui_surface = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        self.hitboxes: Dict[str, Tuple[int, int, int, int]] = {}
        self.last_frame_stats = {"frame_ms": 0.0, "dirty": 0}
        self.preview_hold: Optional[pygame.Surface] = None
        self.noise = self._make_noise()
        self.preview_image = self._load_preview_asset()
        self.font_regular, self.font_heading = self._load_fonts(font_path)
        self.gallery_cache: OrderedDict[Path, pygame.Surface] = OrderedDict()
        self.gallery_cache_max = 24
        self.preview_mode = "DEMO_IMAGE" if self.preview_image is not None else "PROCEDURAL"
        self.webcam = None
        if use_webcam:
            self._try_init_webcam()

    def _try_init_webcam(self):
        try:
            import pygame.camera

            pygame.camera.init()
            cams = pygame.camera.list_cameras()
            if cams:
                self.webcam = pygame.camera.Camera(cams[0], (self.w, self.h))
                self.webcam.start()
                self.preview_mode = "WEBCAM"
        except Exception:
            self.webcam = None

    def _load_fonts(self, font_path: Optional[str]):
        reg = None
        bold = None
        font_dir = Path("assets/fonts")
        if font_path:
            p = Path(font_path)
            if p.exists():
                reg = p
        if reg is None:
            regs = sorted(font_dir.glob("Intel*Regular*.ttf"))
            if regs:
                reg = regs[0]
        if reg is None:
            anys = sorted(font_dir.glob("Intel*.ttf"))
            if anys:
                reg = anys[0]

        bolds = sorted(font_dir.glob("Intel*Bold*.ttf"))
        if bolds:
            bold = bolds[0]

        if reg:
            try:
                reg_font = pygame.font.Font(str(reg), TYPE_BODY)
                if bold:
                    head_font = pygame.font.Font(str(bold), TYPE_H1)
                else:
                    print("[ui] Intel bold missing; using regular for headings")
                    head_font = pygame.font.Font(str(reg), TYPE_H1)
                return reg_font, head_font
            except Exception:
                pass

        print("[ui] Intel regular missing; falling back to system sans")
        return pygame.font.SysFont("arial", TYPE_BODY), pygame.font.SysFont("arial", TYPE_H1, bold=True)

    def _load_preview_asset(self):
        p = Path("assets/demo.jpg")
        if p.exists():
            try:
                return pygame.image.load(str(p)).convert()
            except Exception:
                return None
        return None

    def _make_noise(self):
        s = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        rng = random.Random(42)
        for _ in range(2500):
            x = rng.randrange(0, self.w)
            y = rng.randrange(0, self.h)
            c = rng.randrange(6, 16)
            s.set_at((x, y), (c, c, c, 16))
        return s

    def _crop_to_fill(self, src: pygame.Surface) -> pygame.Surface:
        sw, sh = src.get_size()
        if sw <= 0 or sh <= 0:
            return pygame.Surface((self.w, self.h))
        src_aspect = sw / sh
        dst_aspect = self.w / self.h
        if src_aspect > dst_aspect:
            crop_w = int(sh * dst_aspect)
            x = (sw - crop_w) // 2
            rect = pygame.Rect(x, 0, crop_w, sh)
        else:
            crop_h = int(sw / dst_aspect)
            y = (sh - crop_h) // 2
            rect = pygame.Rect(0, y, sw, crop_h)
        cropped = src.subsurface(rect)
        return pygame.transform.smoothscale(cropped, (self.w, self.h))

    def _procedural_viewfinder(self, t: float) -> pygame.Surface:
        surf = pygame.Surface((self.w, self.h))
        for y in range(self.h):
            k = y / self.h
            surf.fill((int(28 + 30 * k), int(42 + 50 * k), int(68 + 78 * k)), rect=(0, y, self.w, 1))
        drift = int(math.sin(t * 0.5) * 12)
        bw = max(24, self.w // 13)
        for i in range(10):
            x = 20 + i * max(32, self.w // 10) + drift
            h = 120 + (i * 27 % 110)
            pygame.draw.rect(surf, (30, 34, 46), (x, self.h // 2 - h, bw, h))
            pygame.draw.rect(surf, (56, 66, 80), (x + 2, self.h // 2 - h + 8, max(4, bw - 4), h - 8), 1)
        pygame.draw.circle(surf, (245, 190, 96), (self.w - 88, 124), 42)
        vignette = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        for i in range(26):
            pygame.draw.rect(vignette, (0, 0, 0, min(200, i * 8)), (i, i, self.w - 2 * i, self.h - 2 * i), 1)
        surf.blit(vignette, (0, 0))
        surf.blit(self.noise, (0, 0))
        return surf

    # UI_ICON: HOW TO CHANGE: single stroke monoline icon set lives here.
    def _icon(self, name: str, pos: Tuple[int, int], color=C_TEXT):
        x, y = pos
        if name == "battery":
            pygame.draw.rect(self.ui_surface, color, (x, y, 24, 11), 1)
            pygame.draw.rect(self.ui_surface, color, (x + 24, y + 3, 2, 5), 1)
        elif name == "grid":
            for i in range(3):
                pygame.draw.line(self.ui_surface, color, (x, y + i * 6), (x + 14, y + i * 6), 1)
                pygame.draw.line(self.ui_surface, color, (x + i * 6, y), (x + i * 6, y + 14), 1)
        elif name == "level":
            pygame.draw.line(self.ui_surface, color, (x, y + 8), (x + 16, y + 8), 2)
            pygame.draw.circle(self.ui_surface, color, (x + 8, y + 8), 4, 1)

    def _txt(self, font, text: str, color, xy: Tuple[int, int]):
        self.ui_surface.blit(font.render(text, True, color), xy)

    def _draw_histogram(self, x: int, y: int):
        for i in range(36):
            h = int(8 + 10 * abs(math.sin(i * 0.22 + time.perf_counter())))
            pygame.draw.line(self.ui_surface, C_TEXT_SUB, (x + i * 2, y + 18), (x + i * 2, y + 18 - h), 1)

    def build_hitboxes(self, state: AppState) -> Dict[str, Tuple[int, int, int, int]]:
        sx = int(-SIDEBAR_W + SIDEBAR_W * state.sidebar_anim)
        return {
            "back": (SP12, SP12, 64, 40),
            "handle": (0, self.h // 2 - 40, HANDLE_W, 80),
            "capture": (self.w // 2 - 38, self.h - 86, 76, 76),
            "thumb": (SP16, self.h - 82, 62, 62),
            "filter_wheel": (sx + SP16, 136, SIDEBAR_W - 32, HIT_MIN),
            "grid": (sx + SP16, 206, SIDEBAR_W - 32, HIT_MIN),
            "level": (sx + SP16, 276, SIDEBAR_W - 32, HIT_MIN),
            "haptics": (sx + SP16, 346, SIDEBAR_W - 32, HIT_MIN),
            "lang": (sx + SP16, 416, SIDEBAR_W - 32, HIT_MIN),
            "gallery_prev": (SP16, self.h // 2 - 40, 54, 80),
            "gallery_next": (self.w - 70, self.h // 2 - 40, 54, 80),
        }

    def render_preview(self, state: AppState, t: float) -> pygame.Surface:
        if self.preview_hold is not None and time.perf_counter() < state.freeze_until:
            return self.preview_hold

        frame = None
        if self.webcam is not None:
            try:
                frame = self._crop_to_fill(self.webcam.get_image())
                state.preview_mode = "WEBCAM"
            except Exception:
                frame = None

        if frame is None and self.preview_image is not None:
            frame = self._crop_to_fill(self.preview_image)
            state.preview_mode = "DEMO_IMAGE"

        if frame is None:
            frame = self._procedural_viewfinder(t)
            state.preview_mode = "PROCEDURAL"

        if time.perf_counter() < state.freeze_until:
            self.preview_hold = frame.copy()
        else:
            self.preview_hold = None
        return frame

    def _gallery_image(self, idx: int) -> pygame.Surface:
        photo_dir = Path("./selimcam_photos")
        photo_dir.mkdir(exist_ok=True)
        files = sorted(photo_dir.glob("IMG_*.jpg"), reverse=True)
        if not files:
            return self._procedural_viewfinder(time.perf_counter())
        f = files[idx % len(files)]
        if f in self.gallery_cache:
            img = self.gallery_cache.pop(f)
            self.gallery_cache[f] = img
            return img
        try:
            img = self._crop_to_fill(pygame.image.load(str(f)).convert())
        except Exception:
            img = self._procedural_viewfinder(time.perf_counter())
        self.gallery_cache[f] = img
        while len(self.gallery_cache) > self.gallery_cache_max:
            self.gallery_cache.popitem(last=False)
        return img

    def _draw_btn(self, rect: Tuple[int, int, int, int], pressed: bool = False):
        col = C_PRESS if pressed else C_PANEL_SOFT
        pygame.draw.rect(self.ui_surface, col, rect, border_radius=RADIUS)

    def render_ui(self, state: AppState, mem_mb: Optional[float], queue_depth: int):
        self.ui_surface.fill((0, 0, 0, 0))
        self.hitboxes = self.build_hitboxes(state)
        pressed = time.perf_counter() < state.pressed_until

        pygame.draw.rect(self.ui_surface, C_PANEL, (0, 0, self.w, TOP_H))
        self._draw_btn(self.hitboxes["back"], pressed and state.touch_target == "back")
        self._txt(self.font_regular, state.t("back"), C_TEXT, (SP12 + 14, SP12 + 11))

        self._txt(self.font_regular, f"{state.t('iso')} {state.iso}   {state.t('shutter')} {state.shutter}   {state.t('ev')} {state.ev:+.1f}", C_TEXT, (92, 12))
        self._txt(self.font_regular, f"{state.t('filter')}: {state.filter_name.upper()}", C_ACCENT, (92, 34))
        self._icon("battery", (self.w - 108, 12), C_TEXT)
        self._txt(self.font_regular, f"{state.battery_pct}%", C_TEXT, (self.w - 76, 10))
        self._draw_histogram(self.w - 96, 34)

        self._draw_btn(self.hitboxes["handle"], pressed and state.touch_target == "handle")

        sx = int(-SIDEBAR_W + SIDEBAR_W * state.sidebar_anim)
        pygame.draw.rect(self.ui_surface, C_PANEL, (sx, 0, SIDEBAR_W, self.h))
        self._txt(self.font_heading, state.t("sidebar"), C_TEXT, (sx + SP16, 84))

        for key, y, text in [
            ("filter_wheel", 136, f"{state.t('filter')}: {state.filter_name}"),
            ("grid", 206, f"{state.t('grid')}: {state.grid_mode}"),
            ("level", 276, f"{state.t('level')}: {state.level_mode}"),
            ("haptics", 346, f"{state.t('haptics')}: {int(state.haptics_strength * 100)}%"),
            ("lang", 416, f"{state.t('lang')}: {state.lang.upper()}"),
        ]:
            self._draw_btn((sx + SP16, y, SIDEBAR_W - 32, HIT_MIN), pressed and state.touch_target == key)
            self._txt(self.font_regular, text, C_TEXT, (sx + SP16 + 12, y + 14))

        pygame.draw.line(self.ui_surface, C_TEXT_SUB, (sx + SP16, 382), (sx + SIDEBAR_W - SP16, 382), 2)
        knob_x = int(sx + SP16 + (SIDEBAR_W - 32) * state.haptics_strength)
        pygame.draw.circle(self.ui_surface, C_ACCENT, (knob_x, 382), 6)

        if state.grid_mode != "off":
            for x in range(0, self.w, 80):
                pygame.draw.line(self.ui_surface, (255, 255, 255, 55), (x, 0), (x, self.h), 1)
            for y in range(0, self.h, 80):
                pygame.draw.line(self.ui_surface, (255, 255, 255, 55), (0, y), (self.w, y), 1)
        if state.level_mode != "off":
            y = self.h // 2 + int(math.sin(time.perf_counter() * 2.2) * 2)
            pygame.draw.line(self.ui_surface, C_ACCENT, (90, y), (self.w - 22, y), 2)

        pygame.draw.rect(self.ui_surface, C_PANEL, (0, self.h - BOTTOM_H, self.w, BOTTOM_H))
        self._draw_btn(self.hitboxes["thumb"], pressed and state.touch_target == "thumb")
        self._txt(self.font_regular, "▣", C_TEXT, (SP16 + 22, self.h - 64))

        cap_scale = PRESS_SCALE if (pressed and state.touch_target == "capture") else 1.0
        cx, cy = self.w // 2, self.h - 48
        outer_r = int(33 * cap_scale)
        inner_r = int(24 * cap_scale)
        pygame.draw.circle(self.ui_surface, C_TEXT, (cx, cy), outer_r, 3)
        pygame.draw.circle(self.ui_surface, (248, 248, 248), (cx, cy), inner_r)

        if state.scene == Scene.GALLERY:
            shade = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            shade.fill((10, 10, 14, 200))
            self.ui_surface.blit(shade, (0, 0))
            self._txt(self.font_heading, state.t("gallery"), C_TEXT, (SP16, SP16 + 4))
            self._txt(self.font_regular, f"#{state.gallery_index+1}", C_TEXT, (self.w // 2 - 12, self.h // 2 - 14))
            self._txt(self.font_heading, "‹", C_TEXT, (SP24, self.h // 2 - 22))
            self._txt(self.font_heading, "›", C_TEXT, (self.w - 42, self.h // 2 - 22))

        if state.toast:
            self._txt(self.font_regular, state.toast, C_ACCENT, (self.w // 2 - 40, self.h - 132))

        if state.debug_overlay:
            dbg = pygame.Surface((272, 96), pygame.SRCALPHA)
            dbg.fill((0, 0, 0, 190))
            self.ui_surface.blit(dbg, (self.w - 280, 8))
            self._txt(self.font_regular, f"mode {state.preview_mode}", C_TEXT, (self.w - 270, 14))
            self._txt(self.font_regular, f"frame {self.last_frame_stats['frame_ms']:.2f}ms", C_TEXT, (self.w - 270, 32))
            self._txt(self.font_regular, f"input {state.last_input_latency_ms:.3f}ms", C_TEXT, (self.w - 270, 50))
            self._txt(self.font_regular, f"dirty {self.last_frame_stats['dirty']} queue {queue_depth} mem {mem_mb if mem_mb is not None else 'n/a'}", C_TEXT, (self.w - 270, 68))

    def compose(self, state: AppState, mem_mb: Optional[float], queue_depth: int, t: float) -> Tuple[pygame.Surface, Dict[str, Tuple[int, int, int, int]]]:
        start = time.perf_counter()
        if state.scene == Scene.GALLERY:
            frame = self._gallery_image(state.gallery_index)
        else:
            frame = self.render_preview(state, t)
        self.render_ui(state, mem_mb, queue_depth)
        frame.blit(self.ui_surface, (0, 0))
        self.last_frame_stats = {
            "frame_ms": (time.perf_counter() - start) * 1000.0,
            "dirty": len(state.dirty_rects),
        }
        return frame, self.hitboxes


class ViewportMapper:
    """Map window coordinates to fixed internal coordinates with letterboxing."""

    def __init__(self, internal_size=(480, 800)):
        self.iw, self.ih = internal_size
        self.view = pygame.Rect(0, 0, self.iw, self.ih)

    def update(self, out_w: int, out_h: int):
        scale = min(out_w / self.iw, out_h / self.ih)
        w = int(self.iw * scale)
        h = int(self.ih * scale)
        x = (out_w - w) // 2
        y = (out_h - h) // 2
        self.view = pygame.Rect(x, y, w, h)

    def to_internal(self, pos: Tuple[int, int]) -> Tuple[int, int]:
        x, y = pos
        if self.view.w <= 0 or self.view.h <= 0:
            return 0, 0
        nx = int((x - self.view.x) * self.iw / self.view.w)
        ny = int((y - self.view.y) * self.ih / self.view.h)
        return max(0, min(self.iw - 1, nx)), max(0, min(self.ih - 1, ny))

    def blit_scaled(self, screen: pygame.Surface, surface: pygame.Surface):
        scaled = pygame.transform.smoothscale(surface, (self.view.w, self.view.h))
        screen.fill(C_BG)
        screen.blit(scaled, self.view.topleft)
