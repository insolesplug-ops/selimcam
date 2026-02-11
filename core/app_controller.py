"""Shared finite-state app controller for Pi and PC entry points."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Tuple

from core.i18n import I18N
from core.input_events import EventType, InputEvent

FILTERS = ["none", "vintage", "bw", "vivid", "portrait"]


class Scene(Enum):
    CAMERA = auto()
    GALLERY = auto()


@dataclass
class AppState:
    lang: str = "en"
    scene: Scene = Scene.CAMERA
    filter_idx: int = 0
    grid_on: bool = False
    level_on: bool = False
    flash_on: bool = False
    shutdown_requested: bool = False
    encoder_value: int = 0
    touch_down: bool = False
    last_input_latency_ms: float = 0.0
    dirty_rects: List[Tuple[int, int, int, int]] = field(default_factory=list)
    toast: str = ""

    def t(self, key: str) -> str:
        return I18N[self.lang].get(key, key)

    @property
    def filter_name(self) -> str:
        return FILTERS[self.filter_idx]


class AppController:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.state = AppState()

    def mark_dirty(self, rect: Tuple[int, int, int, int]):
        self.state.dirty_rects.append(rect)

    def pop_dirty(self) -> List[Tuple[int, int, int, int]]:
        rects = self.state.dirty_rects[:]
        self.state.dirty_rects.clear()
        return rects

    def handle(self, event: InputEvent):
        t0 = time.perf_counter()
        s = self.state

        if event.type == EventType.ENCODER_DETENT:
            s.filter_idx = (s.filter_idx + (1 if event.delta >= 0 else -1)) % len(FILTERS)
            self.mark_dirty((0, 0, self.width, 90))
        elif event.type == EventType.ENCODER_PRESS:
            s.scene = Scene.GALLERY if s.scene == Scene.CAMERA else Scene.CAMERA
            self.mark_dirty((0, 0, self.width, self.height))
        elif event.type == EventType.TOGGLE_GRID:
            s.grid_on = not s.grid_on
            self.mark_dirty((0, 0, self.width, self.height))
        elif event.type == EventType.TOGGLE_LEVEL:
            s.level_on = not s.level_on
            self.mark_dirty((0, 0, self.width, self.height))
        elif event.type == EventType.TOGGLE_LANG:
            s.lang = "de" if s.lang == "en" else "en"
            self.mark_dirty((0, 0, self.width, 90))
        elif event.type == EventType.FLASH_TOGGLE:
            s.flash_on = not s.flash_on
            self.mark_dirty((self.width - 180, 0, 180, 90))
        elif event.type == EventType.SHUTTER_PRESS:
            s.toast = s.t("capture")
            self.mark_dirty((0, self.height - 70, self.width, 70))
        elif event.type == EventType.SHUTDOWN:
            s.shutdown_requested = True
        elif event.type == EventType.BACK:
            s.scene = Scene.CAMERA
            self.mark_dirty((0, 0, self.width, self.height))
        elif event.type == EventType.TOUCH_DOWN:
            s.touch_down = True
        elif event.type == EventType.TOUCH_UP:
            s.touch_down = False

        s.last_input_latency_ms = (time.perf_counter() - t0) * 1000.0
