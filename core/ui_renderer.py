"""Shared matte UI renderer for Pi + PC targets (pixel-identical at 800x480)."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import List, Tuple

import pygame

from core.app_controller import AppState, Scene

# UI_TOKENS: HOW TO CHANGE -> adjust color tuple constants below to reskin matte theme globally.
C_BG = (18, 18, 22)
C_PANEL = (28, 28, 34)
C_TEXT = (235, 235, 235)
C_MUTED = (140, 140, 145)
C_ACCENT = (255, 204, 0)
C_OK = (52, 199, 89)

# UI_LAYOUT: HOW TO CHANGE -> change spacing/hitbox constants here to tune ergonomics.
PAD = 16
TOP_H = 56
BOTTOM_H = 64
SIDEBAR_W = 220
ICON_SIZE = 20

# UI_MOTION: HOW TO CHANGE -> tweak timings/easing to make interaction snappier/slower.
TOAST_SEC = 0.6

# UI_TOUCH: HOW TO CHANGE -> increase touch box for gloves or smaller screens.
TOUCH_HITBOX = 48

# UI_TEXT: HOW TO CHANGE -> adjust label sizes/faces via font table in build_fonts().
FONT_SIZES = {"s": 14, "m": 18, "l": 24}


@dataclass
class RenderStats:
    frame_ms: float = 0.0
    dirty_count: int = 0


class UIRenderer:
    def __init__(self, screen: pygame.Surface, width: int, height: int):
        self.screen = screen
        self.width = width
        self.height = height
        self.fonts = self.build_fonts()
        self.last_toast_time = 0.0

    def build_fonts(self):
        return {
            "s": pygame.font.SysFont("Arial", FONT_SIZES["s"]),
            "m": pygame.font.SysFont("Arial", FONT_SIZES["m"]),
            "l": pygame.font.SysFont("Arial", FONT_SIZES["l"], bold=True),
        }

    # UI_ICON: HOW TO CHANGE -> edit primitive geometry for icons; no external assets needed.
    def draw_icon(self, name: str, center: Tuple[int, int], color):
        x, y = center
        if name == "grid":
            for i in (-6, 0, 6):
                pygame.draw.line(self.screen, color, (x - 8, y + i), (x + 8, y + i), 1)
                pygame.draw.line(self.screen, color, (x + i, y - 8), (x + i, y + 8), 1)
        elif name == "level":
            pygame.draw.line(self.screen, color, (x - 10, y), (x + 10, y), 2)
            pygame.draw.circle(self.screen, color, (x, y), 3, 1)
        elif name == "flash":
            pts = [(x - 4, y - 9), (x + 2, y - 2), (x - 1, y - 2), (x + 4, y + 9), (x - 2, y + 2), (x + 1, y + 2)]
            pygame.draw.lines(self.screen, color, False, pts, 2)

    def _text(self, key: str, text: str, color, pos):
        surf = self.fonts[key].render(text, True, color)
        self.screen.blit(surf, pos)

    def render(self, state: AppState, frame: pygame.Surface, show_debug: bool = False) -> RenderStats:
        t0 = time.perf_counter()

        # viewfinder fast path (already prepared frame surface)
        self.screen.blit(frame, (0, 0))

        # top matte bar
        pygame.draw.rect(self.screen, C_PANEL, (0, 0, self.width, TOP_H))
        self._text("m", f"{state.t('mode')}  {state.t('filter')}: {state.filter_name.upper()}", C_TEXT, (PAD, 16))
        flash_color = C_ACCENT if state.flash_on else C_MUTED
        self.draw_icon("flash", (self.width - 30, 28), flash_color)

        # left matte sidebar
        pygame.draw.rect(self.screen, C_PANEL, (0, TOP_H, SIDEBAR_W, self.height - TOP_H - BOTTOM_H))
        self.draw_icon("grid", (30, TOP_H + 28), C_OK if state.grid_on else C_MUTED)
        self._text("s", state.t("grid"), C_TEXT, (52, TOP_H + 20))
        self.draw_icon("level", (30, TOP_H + 70), C_OK if state.level_on else C_MUTED)
        self._text("s", state.t("level"), C_TEXT, (52, TOP_H + 62))
        self._text("s", f"{state.t('lang')}: {state.lang.upper()}", C_TEXT, (22, TOP_H + 104))
        self._text("s", f"{state.t('status')}: {state.t('ready')}", C_MUTED, (22, TOP_H + 134))

        # overlay helpers
        if state.grid_on:
            for x in range(0, self.width, 80):
                pygame.draw.line(self.screen, (70, 70, 75), (x, 0), (x, self.height), 1)
            for y in range(0, self.height, 80):
                pygame.draw.line(self.screen, (70, 70, 75), (0, y), (self.width, y), 1)

        if state.level_on:
            y = int(self.height * 0.5 + math.sin(time.perf_counter() * 2.0) * 2.0)
            pygame.draw.line(self.screen, C_ACCENT, (SIDEBAR_W + 20, y), (self.width - 20, y), 2)

        # bottom bar
        pygame.draw.rect(self.screen, C_PANEL, (0, self.height - BOTTOM_H, self.width, BOTTOM_H))
        scene_label = state.t("gallery") if state.scene == Scene.GALLERY else state.t("capture")
        self._text("m", scene_label, C_TEXT, (PAD, self.height - 42))
        if state.toast:
            self._text("m", state.toast, C_ACCENT, (self.width // 2 - 50, self.height - 42))
            if self.last_toast_time == 0.0:
                self.last_toast_time = time.perf_counter()
            if time.perf_counter() - self.last_toast_time > TOAST_SEC:
                state.toast = ""
                self.last_toast_time = 0.0

        if show_debug:
            pygame.draw.rect(self.screen, (0, 0, 0), (self.width - 260, 8, 252, 72))
            self._text("s", f"input {state.last_input_latency_ms:.3f} ms", C_TEXT, (self.width - 250, 14))
            self._text("s", f"dirty {len(state.dirty_rects)}", C_TEXT, (self.width - 250, 30))

        return RenderStats(frame_ms=(time.perf_counter() - t0) * 1000.0, dirty_count=len(state.dirty_rects))

    def dirty_or_full(self, rects: List[Tuple[int, int, int, int]]):
        if rects:
            pygame.display.update(rects)
        else:
            pygame.display.flip()
