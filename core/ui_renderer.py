"""Shared matte UI renderer for Pi + PC targets (pixel-identical at 480x800 canvas)."""

from __future__ import annotations

import math
import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pygame

from core.app_controller import AppState, Scene

# UI_TOKENS: HOW TO CHANGE: adjust palette values here for the full camera UI theme.
C_PANEL = (18, 18, 22, 235)
C_LINE = (235, 235, 235)
C_SUB = (140, 140, 145)
C_ACCENT = (255, 204, 0)
C_GREEN = (52, 199, 89)
C_RED = (255, 59, 48)

# UI_LAYOUT: HOW TO CHANGE: tune these dimensions to adjust placement and control density.
W, H = 480, 800
TOP_H = 68
BOTTOM_H = 96
SIDEBAR_W = 220
HANDLE_W = 16
PAD = 14

# UI_MOTION: HOW TO CHANGE: modify animation speeds/scales for tactile feel.
PRESS_SCALE = 0.94
PRESS_MS = 110

# UI_TOUCH: HOW TO CHANGE: raise/lower hit target sizes and gesture thresholds.
HIT_MIN = 44
SWIPE_THRESHOLD = 32

# UI_TEXT: HOW TO CHANGE: change font names/sizes and translation key usage in these settings.
FONT_SMALL = 14
FONT_MED = 18
FONT_BIG = 24


class UIRenderer:
    def __init__(self, screen: pygame.Surface, font_path: Optional[str] = None):
        self.screen = screen
        self.ui_surface = pygame.Surface((W, H), pygame.SRCALPHA)
        self.ui_dirty = True
        self.hitboxes: Dict[str, Tuple[int, int, int, int]] = {}
        self.last_frame_stats = {"frame_ms": 0.0, "dirty": 0}
        self.preview_hold: Optional[pygame.Surface] = None
        self.noise = self._make_noise()
        self.preview_image = self._load_preview_asset()
        self.font_small, self.font_med, self.font_big = self._load_fonts(font_path)

    def _load_fonts(self, font_path: Optional[str]):
        fp = None
        candidates = []
        if font_path:
            candidates.append(Path(font_path))
        candidates += sorted(Path("assets/fonts").glob("Intel*.ttf"))
        for c in candidates:
            if c.exists():
                fp = str(c)
                break
        if fp:
            try:
                return (
                    pygame.font.Font(fp, FONT_SMALL),
                    pygame.font.Font(fp, FONT_MED),
                    pygame.font.Font(fp, FONT_BIG),
                )
            except Exception:
                pass
        print("[ui] Intel font missing; falling back to default sans")
        return (
            pygame.font.SysFont("arial", FONT_SMALL),
            pygame.font.SysFont("arial", FONT_MED),
            pygame.font.SysFont("arial", FONT_BIG, bold=True),
        )

    def _load_preview_asset(self):
        p = Path("assets/demo.jpg")
        if p.exists():
            try:
                img = pygame.image.load(str(p)).convert()
                return pygame.transform.smoothscale(img, (W, H))
            except Exception:
                return None
        return None

    def _make_noise(self):
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        rng = random.Random(42)
        for _ in range(3200):
            x = rng.randrange(0, W)
            y = rng.randrange(0, H)
            c = rng.randrange(8, 22)
            s.set_at((x, y), (c, c, c, 18))
        return s

    def _procedural_viewfinder(self, t: float) -> pygame.Surface:
        surf = pygame.Surface((W, H))
        for y in range(H):
            k = y / H
            r = int(40 + 35 * k)
            g = int(58 + 55 * k)
            b = int(90 + 80 * k)
            pygame.draw.line(surf, (r, g, b), (0, y), (W, y))
        # skyline/parallax
        offset = int(math.sin(t * 0.4) * 14)
        for i in range(8):
            x = 30 + i * 58 + offset
            w = 40
            h = 120 + ((i * 33) % 90)
            pygame.draw.rect(surf, (35, 42, 55), (x, H // 2 - h, w, h))
            pygame.draw.rect(surf, (60, 70, 82), (x + 2, H // 2 - h + 8, w - 4, h - 8), 1)
        pygame.draw.circle(surf, (246, 190, 90), (W - 88 + int(math.sin(t) * 2), 122), 42)
        vignette = pygame.Surface((W, H), pygame.SRCALPHA)
        pygame.draw.rect(vignette, (0, 0, 0, 0), (0, 0, W, H))
        for i in range(24):
            a = min(200, i * 8)
            pygame.draw.rect(vignette, (0, 0, 0, a), (i, i, W - 2 * i, H - 2 * i), 1)
        surf.blit(vignette, (0, 0))
        surf.blit(self.noise, (0, 0))
        return surf

    # UI_ICON: HOW TO CHANGE: edit line primitives below to redesign icon language.
    def _icon(self, name: str, pos: Tuple[int, int], color=(230, 230, 230)):
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
            h = int(8 + 10 * abs(math.sin(i * 0.23 + time.perf_counter())))
            pygame.draw.line(self.ui_surface, C_SUB, (x + i * 2, y + 18), (x + i * 2, y + 18 - h), 1)

    def build_hitboxes(self, state: AppState) -> Dict[str, Tuple[int, int, int, int]]:
        sx = int(-SIDEBAR_W + SIDEBAR_W * state.sidebar_anim)
        return {
            "handle": (0, H // 2 - 38, HANDLE_W, 76),
            "capture": (W // 2 - 34, H - 78, 68, 68),
            "thumb": (22, H - 74, 52, 52),
            "filter_next": (sx + 16, 120, SIDEBAR_W - 32, HIT_MIN),
            "grid": (sx + 16, 180, SIDEBAR_W - 32, HIT_MIN),
            "level": (sx + 16, 240, SIDEBAR_W - 32, HIT_MIN),
            "haptics": (sx + 16, 300, SIDEBAR_W - 32, HIT_MIN),
            "lang": (sx + 16, 360, SIDEBAR_W - 32, HIT_MIN),
            "gallery_prev": (20, H // 2 - 40, 44, 80),
            "gallery_next": (W - 64, H // 2 - 40, 44, 80),
        }

    def render_preview(self, state: AppState, t: float) -> pygame.Surface:
        if self.preview_hold is not None and time.perf_counter() < state.freeze_until:
            return self.preview_hold
        if self.preview_image is not None:
            frame = self.preview_image.copy()
        else:
            frame = self._procedural_viewfinder(t)
        if time.perf_counter() < state.freeze_until:
            self.preview_hold = frame.copy()
        else:
            self.preview_hold = None
        return frame

    def render_ui(self, state: AppState, mem_mb: Optional[float], queue_depth: int):
        self.ui_surface.fill((0, 0, 0, 0))
        self.hitboxes = self.build_hitboxes(state)

        # top bar
        pygame.draw.rect(self.ui_surface, C_PANEL, (0, 0, W, TOP_H), border_radius=0)
        self._txt(self.font_small, f"{state.t('iso')} {state.iso}   {state.t('shutter')} {state.shutter}   {state.t('ev')} {state.ev:+.1f}", C_LINE, (PAD, 10))
        self._txt(self.font_small, f"{state.t('filter')}: {state.filter_name.upper()}", C_ACCENT, (PAD, 32))
        self._icon("battery", (W - 108, 12), C_LINE)
        self._txt(self.font_small, f"{state.battery_pct}%", C_LINE, (W - 76, 10))
        self._draw_histogram(W - 96, 34)

        # handle
        pygame.draw.rect(self.ui_surface, (255, 255, 255, 90), self.hitboxes["handle"], border_radius=5)

        # sidebar
        sx = int(-SIDEBAR_W + SIDEBAR_W * state.sidebar_anim)
        pygame.draw.rect(self.ui_surface, C_PANEL, (sx, 0, SIDEBAR_W, H), border_radius=0)
        self._txt(self.font_med, state.t("sidebar"), C_LINE, (sx + 16, 78))
        self._txt(self.font_small, f"{state.t('filter')}: {state.filter_name}", C_LINE, (sx + 16, 132))
        self._txt(self.font_small, f"{state.t('grid')}: {state.grid_mode}", C_LINE, (sx + 16, 192))
        self._txt(self.font_small, f"{state.t('level')}: {state.level_mode}", C_LINE, (sx + 16, 252))
        self._txt(self.font_small, f"{state.t('haptics')}: {int(state.haptics_strength * 100)}%", C_LINE, (sx + 16, 312))
        self._txt(self.font_small, f"{state.t('lang')}: {state.lang.upper()}", C_LINE, (sx + 16, 372))
        # slider
        pygame.draw.line(self.ui_surface, C_SUB, (sx + 16, 340), (sx + SIDEBAR_W - 16, 340), 2)
        knob_x = int(sx + 16 + (SIDEBAR_W - 32) * state.haptics_strength)
        pygame.draw.circle(self.ui_surface, C_ACCENT, (knob_x, 340), 6)

        # overlays
        if state.grid_mode != "off":
            for x in range(0, W, 80):
                pygame.draw.line(self.ui_surface, (255, 255, 255, 65), (x, 0), (x, H), 1)
            for y in range(0, H, 80):
                pygame.draw.line(self.ui_surface, (255, 255, 255, 65), (0, y), (W, y), 1)
        if state.level_mode != "off":
            y = H // 2 + int(math.sin(time.perf_counter() * 2.2) * 3)
            pygame.draw.line(self.ui_surface, C_ACCENT, (88, y), (W - 20, y), 2)

        # bottom controls
        pygame.draw.rect(self.ui_surface, C_PANEL, (0, H - BOTTOM_H, W, BOTTOM_H), border_radius=0)
        pygame.draw.circle(self.ui_surface, (255, 255, 255), (W // 2, H - 44), 30, 3)
        pygame.draw.circle(self.ui_surface, (250, 250, 250), (W // 2, H - 44), 22)
        pygame.draw.rect(self.ui_surface, (56, 56, 62), self.hitboxes["thumb"], border_radius=8)
        self._txt(self.font_small, "▣", C_LINE, (30, H - 62))

        if state.scene == Scene.GALLERY:
            overlay = pygame.Surface((W, H), pygame.SRCALPHA)
            overlay.fill((10, 10, 14, 220))
            self.ui_surface.blit(overlay, (0, 0))
            self._txt(self.font_big, state.t("gallery"), C_LINE, (18, 20))
            self._txt(self.font_med, f"#{state.gallery_index+1}", C_LINE, (W // 2 - 12, H // 2 - 14))
            self._txt(self.font_big, "‹", C_LINE, (26, H // 2 - 16))
            self._txt(self.font_big, "›", C_LINE, (W - 42, H // 2 - 16))

        if state.toast:
            self._txt(self.font_med, state.toast, C_ACCENT, (W // 2 - 40, H - 126))

        if state.debug_overlay:
            dbg = pygame.Surface((260, 92), pygame.SRCALPHA)
            dbg.fill((0, 0, 0, 190))
            self.ui_surface.blit(dbg, (W - 266, 8))
            self._txt(self.font_small, f"frame {self.last_frame_stats['frame_ms']:.2f}ms", C_LINE, (W - 256, 14))
            self._txt(self.font_small, f"input {state.last_input_latency_ms:.3f}ms", C_LINE, (W - 256, 32))
            self._txt(self.font_small, f"dirty {self.last_frame_stats['dirty']}", C_LINE, (W - 256, 50))
            self._txt(self.font_small, f"queue {queue_depth} mem {mem_mb if mem_mb is not None else 'n/a'}", C_LINE, (W - 256, 68))

    def compose(self, state: AppState, mem_mb: Optional[float], queue_depth: int, t: float) -> Tuple[pygame.Surface, Dict[str, Tuple[int, int, int, int]]]:
        start = time.perf_counter()
        frame = self.render_preview(state, t)
        self.render_ui(state, mem_mb, queue_depth)
        frame.blit(self.ui_surface, (0, 0))
        self.last_frame_stats = {
            "frame_ms": (time.perf_counter() - start) * 1000.0,
            "dirty": len(state.dirty_rects),
        }
        return frame, self.hitboxes


class ViewportMapper:
    """Map window coordinates to fixed internal 480x800 coordinates with letterboxing."""

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
        screen.fill((0, 0, 0))
        screen.blit(scaled, self.view.topleft)
