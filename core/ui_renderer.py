"""Shared matte UI renderer for Pi + PC targets (pixel-identical runtime canvas)."""

from __future__ import annotations

import math
import random
import time
from collections import OrderedDict
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
    def __init__(self, screen: pygame.Surface, width: int, height: int, font_path: Optional[str] = None):
        self.screen = screen
        self.w = width
        self.h = height
        self.ui_surface = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        self.hitboxes: Dict[str, Tuple[int, int, int, int]] = {}
        self.last_frame_stats = {"frame_ms": 0.0, "dirty": 0}
        self.preview_hold: Optional[pygame.Surface] = None
        self.noise = self._make_noise()
        self.preview_image = self._load_preview_asset()
        self.font_small, self.font_med, self.font_big = self._load_fonts(font_path)
        self.gallery_cache: OrderedDict[Path, pygame.Surface] = OrderedDict()
        self.gallery_cache_max = 24
        self._try_init_webcam()

    def _try_init_webcam(self):
        self.webcam = None
        try:
            import pygame.camera

            pygame.camera.init()
            cams = pygame.camera.list_cameras()
            if cams:
                self.webcam = pygame.camera.Camera(cams[0], (self.w, self.h))
                self.webcam.start()
        except Exception:
            self.webcam = None

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

        use_freetype = False
        try:
            import pygame.freetype  # noqa

            use_freetype = True
        except Exception:
            use_freetype = False

        if fp and use_freetype:
            try:
                import pygame.freetype

                return (
                    pygame.freetype.Font(fp, FONT_SMALL),
                    pygame.freetype.Font(fp, FONT_MED),
                    pygame.freetype.Font(fp, FONT_BIG),
                )
            except Exception:
                pass
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
                return pygame.transform.smoothscale(img, (self.w, self.h))
            except Exception:
                return None
        return None

    def _make_noise(self):
        s = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        rng = random.Random(42)
        for _ in range(3200):
            x = rng.randrange(0, self.w)
            y = rng.randrange(0, self.h)
            c = rng.randrange(8, 22)
            s.set_at((x, y), (c, c, c, 18))
        return s

    def _procedural_viewfinder(self, t: float) -> pygame.Surface:
        surf = pygame.Surface((self.w, self.h))
        for y in range(self.h):
            k = y / self.h
            r = int(40 + 35 * k)
            g = int(58 + 55 * k)
            b = int(90 + 80 * k)
            pygame.draw.line(surf, (r, g, b), (0, y), (self.w, y))
        offset = int(math.sin(t * 0.4) * 14)
        for i in range(8):
            x = 30 + i * max(40, self.w // 9) + offset
            w = max(26, self.w // 14)
            h = 120 + ((i * 33) % 90)
            pygame.draw.rect(surf, (35, 42, 55), (x, self.h // 2 - h, w, h))
            pygame.draw.rect(surf, (60, 70, 82), (x + 2, self.h // 2 - h + 8, max(2, w - 4), h - 8), 1)
        pygame.draw.circle(surf, (246, 190, 90), (self.w - 88 + int(math.sin(t) * 2), 122), 42)
        vignette = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        for i in range(24):
            a = min(200, i * 8)
            pygame.draw.rect(vignette, (0, 0, 0, a), (i, i, self.w - 2 * i, self.h - 2 * i), 1)
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
        if hasattr(font, "render_to"):
            font.render_to(self.ui_surface, xy, text, color)
        else:
            self.ui_surface.blit(font.render(text, True, color), xy)

    def _draw_histogram(self, x: int, y: int):
        for i in range(36):
            h = int(8 + 10 * abs(math.sin(i * 0.23 + time.perf_counter())))
            pygame.draw.line(self.ui_surface, C_SUB, (x + i * 2, y + 18), (x + i * 2, y + 18 - h), 1)

    def build_hitboxes(self, state: AppState) -> Dict[str, Tuple[int, int, int, int]]:
        sx = int(-SIDEBAR_W + SIDEBAR_W * state.sidebar_anim)
        return {
            "handle": (0, self.h // 2 - 38, HANDLE_W, 76),
            "capture": (self.w // 2 - 34, self.h - 78, 68, 68),
            "thumb": (22, self.h - 74, 52, 52),
            "filter_wheel": (sx + 16, 120, SIDEBAR_W - 32, HIT_MIN),
            "grid": (sx + 16, 180, SIDEBAR_W - 32, HIT_MIN),
            "level": (sx + 16, 240, SIDEBAR_W - 32, HIT_MIN),
            "haptics": (sx + 16, 300, SIDEBAR_W - 32, HIT_MIN),
            "lang": (sx + 16, 360, SIDEBAR_W - 32, HIT_MIN),
            "gallery_prev": (20, self.h // 2 - 40, 44, 80),
            "gallery_next": (self.w - 64, self.h // 2 - 40, 44, 80),
        }

    def render_preview(self, state: AppState, t: float) -> pygame.Surface:
        if self.preview_hold is not None and time.perf_counter() < state.freeze_until:
            return self.preview_hold
        frame = None
        if self.webcam is not None:
            try:
                frame = self.webcam.get_image()
                frame = pygame.transform.smoothscale(frame, (self.w, self.h))
            except Exception:
                frame = None
        if frame is None and self.preview_image is not None:
            frame = self.preview_image.copy()
        if frame is None:
            frame = self._procedural_viewfinder(t)
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
            img = pygame.image.load(str(f)).convert()
            img = pygame.transform.smoothscale(img, (self.w, self.h))
        except Exception:
            img = self._procedural_viewfinder(time.perf_counter())
        self.gallery_cache[f] = img
        while len(self.gallery_cache) > self.gallery_cache_max:
            self.gallery_cache.popitem(last=False)
        return img

    def render_ui(self, state: AppState, mem_mb: Optional[float], queue_depth: int):
        self.ui_surface.fill((0, 0, 0, 0))
        self.hitboxes = self.build_hitboxes(state)

        pygame.draw.rect(self.ui_surface, C_PANEL, (0, 0, self.w, TOP_H), border_radius=0)
        self._txt(self.font_small, f"{state.t('iso')} {state.iso}   {state.t('shutter')} {state.shutter}   {state.t('ev')} {state.ev:+.1f}", C_LINE, (PAD, 10))
        self._txt(self.font_small, f"{state.t('filter')}: {state.filter_name.upper()}", C_ACCENT, (PAD, 32))
        self._icon("battery", (self.w - 108, 12), C_LINE)
        self._txt(self.font_small, f"{state.battery_pct}%", C_LINE, (self.w - 76, 10))
        self._draw_histogram(self.w - 96, 34)

        pygame.draw.rect(self.ui_surface, (255, 255, 255, 90), self.hitboxes["handle"], border_radius=5)

        sx = int(-SIDEBAR_W + SIDEBAR_W * state.sidebar_anim)
        pygame.draw.rect(self.ui_surface, C_PANEL, (sx, 0, SIDEBAR_W, self.h), border_radius=0)
        self._txt(self.font_med, state.t("sidebar"), C_LINE, (sx + 16, 78))
        self._txt(self.font_small, f"{state.t('filter')}: {state.filter_name}", C_LINE, (sx + 16, 132))
        self._txt(self.font_small, f"{state.t('grid')}: {state.grid_mode}", C_LINE, (sx + 16, 192))
        self._txt(self.font_small, f"{state.t('level')}: {state.level_mode}", C_LINE, (sx + 16, 252))
        self._txt(self.font_small, f"{state.t('haptics')}: {int(state.haptics_strength * 100)}%", C_LINE, (sx + 16, 312))
        self._txt(self.font_small, f"{state.t('lang')}: {state.lang.upper()}", C_LINE, (sx + 16, 372))
        pygame.draw.line(self.ui_surface, C_SUB, (sx + 16, 340), (sx + SIDEBAR_W - 16, 340), 2)
        knob_x = int(sx + 16 + (SIDEBAR_W - 32) * state.haptics_strength)
        pygame.draw.circle(self.ui_surface, C_ACCENT, (knob_x, 340), 6)

        if state.grid_mode != "off":
            for x in range(0, self.w, 80):
                pygame.draw.line(self.ui_surface, (255, 255, 255, 65), (x, 0), (x, self.h), 1)
            for y in range(0, self.h, 80):
                pygame.draw.line(self.ui_surface, (255, 255, 255, 65), (0, y), (self.w, y), 1)
        if state.level_mode != "off":
            y = self.h // 2 + int(math.sin(time.perf_counter() * 2.2) * 3)
            pygame.draw.line(self.ui_surface, C_ACCENT, (88, y), (self.w - 20, y), 2)

        pygame.draw.rect(self.ui_surface, C_PANEL, (0, self.h - BOTTOM_H, self.w, BOTTOM_H), border_radius=0)
        pygame.draw.circle(self.ui_surface, (255, 255, 255), (self.w // 2, self.h - 44), 30, 3)
        pygame.draw.circle(self.ui_surface, (250, 250, 250), (self.w // 2, self.h - 44), 22)
        pygame.draw.rect(self.ui_surface, (56, 56, 62), self.hitboxes["thumb"], border_radius=8)
        self._txt(self.font_small, "▣", C_LINE, (30, self.h - 62))

        if state.scene == Scene.GALLERY:
            overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            overlay.fill((10, 10, 14, 220))
            self.ui_surface.blit(overlay, (0, 0))
            self._txt(self.font_big, state.t("gallery"), C_LINE, (18, 20))
            self._txt(self.font_med, f"#{state.gallery_index+1}", C_LINE, (self.w // 2 - 12, self.h // 2 - 14))
            self._txt(self.font_big, "‹", C_LINE, (26, self.h // 2 - 16))
            self._txt(self.font_big, "›", C_LINE, (self.w - 42, self.h // 2 - 16))

        if state.toast:
            self._txt(self.font_med, state.toast, C_ACCENT, (self.w // 2 - 40, self.h - 126))

        if state.debug_overlay:
            dbg = pygame.Surface((260, 92), pygame.SRCALPHA)
            dbg.fill((0, 0, 0, 190))
            self.ui_surface.blit(dbg, (self.w - 266, 8))
            self._txt(self.font_small, f"frame {self.last_frame_stats['frame_ms']:.2f}ms", C_LINE, (self.w - 256, 14))
            self._txt(self.font_small, f"input {state.last_input_latency_ms:.3f}ms", C_LINE, (self.w - 256, 32))
            self._txt(self.font_small, f"dirty {self.last_frame_stats['dirty']}", C_LINE, (self.w - 256, 50))
            self._txt(self.font_small, f"queue {queue_depth} mem {mem_mb if mem_mb is not None else 'n/a'}", C_LINE, (self.w - 256, 68))

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
        screen.fill((0, 0, 0))
        screen.blit(scaled, self.view.topleft)
