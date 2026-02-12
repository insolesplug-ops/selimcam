"""Shared finite-state app controller for Pi and PC entry points."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

from core.i18n import I18N
from core.input_events import EventType, InputEvent

FILTERS = ["none", "vintage", "bw", "vivid", "portrait"]
GRID_MODES = ["off", "thirds", "center"]
LEVEL_MODES = ["off", "line", "bubble"]


class Scene(Enum):
    CAMERA = auto()
    GALLERY = auto()


@dataclass
class AppState:
    lang: str = "en"
    scene: Scene = Scene.CAMERA
    filter_idx: int = 0
    grid_mode_idx: int = 0
    level_mode_idx: int = 0
    flash_on: bool = False
    shutdown_requested: bool = False
    sidebar_open: bool = False
    sidebar_anim: float = 0.0
    haptics_strength: float = 0.6
    touch_down: bool = False
    touch_pos: Tuple[int, int] = (0, 0)
    touch_target: Optional[str] = None
    toast: str = ""
    toast_until: float = 0.0
    freeze_until: float = 0.0
    last_input_latency_ms: float = 0.0
    debug_overlay: bool = False
    show_ui: bool = True
    iso: int = 400
    shutter: str = "1/250"
    ev: float = 0.0
    battery_pct: int = 94
    gallery_index: int = 0
    gallery_swipe_x: float = 0.0
    gallery_velocity: float = 0.0
    dirty_rects: List[Tuple[int, int, int, int]] = field(default_factory=list)

    def t(self, key: str) -> str:
        return I18N[self.lang].get(key, key)

    @property
    def filter_name(self) -> str:
        return FILTERS[self.filter_idx]

    @property
    def grid_mode(self) -> str:
        return GRID_MODES[self.grid_mode_idx]

    @property
    def level_mode(self) -> str:
        return LEVEL_MODES[self.level_mode_idx]


class AppController:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.state = AppState()
        self.hitboxes: Dict[str, Tuple[int, int, int, int]] = {}

    def set_hitboxes(self, boxes: Dict[str, Tuple[int, int, int, int]]):
        self.hitboxes = boxes

    def mark_dirty(self, rect: Tuple[int, int, int, int]):
        self.state.dirty_rects.append(rect)

    def mark_all_dirty(self):
        self.mark_dirty((0, 0, self.width, self.height))

    def pop_dirty(self) -> List[Tuple[int, int, int, int]]:
        rects = self.state.dirty_rects[:]
        self.state.dirty_rects.clear()
        return rects

    def _hit(self, p: Tuple[int, int]) -> Optional[str]:
        x, y = p
        for key, (rx, ry, rw, rh) in self.hitboxes.items():
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return key
        return None

    def _on_press(self, key: Optional[str]):
        s = self.state
        if key is None:
            return
        if key == "handle":
            s.sidebar_open = not s.sidebar_open
            self.mark_all_dirty()
        elif key == "capture":
            s.toast = s.t("capture")
            s.toast_until = time.perf_counter() + 0.6
            s.freeze_until = time.perf_counter() + 0.6
            self.mark_all_dirty()
        elif key == "thumb":
            s.scene = Scene.GALLERY
            self.mark_all_dirty()
        elif key == "filter_next":
            s.filter_idx = (s.filter_idx + 1) % len(FILTERS)
            self.mark_all_dirty()
        elif key == "grid":
            s.grid_mode_idx = (s.grid_mode_idx + 1) % len(GRID_MODES)
            self.mark_all_dirty()
        elif key == "level":
            s.level_mode_idx = (s.level_mode_idx + 1) % len(LEVEL_MODES)
            self.mark_all_dirty()
        elif key == "lang":
            s.lang = "de" if s.lang == "en" else "en"
            self.mark_all_dirty()
        elif key == "gallery_prev":
            s.gallery_index = max(0, s.gallery_index - 1)
            self.mark_all_dirty()
        elif key == "gallery_next":
            s.gallery_index = min(9, s.gallery_index + 1)
            self.mark_all_dirty()

    def _update_sidebar_drag(self, pos: Tuple[int, int]):
        s = self.state
        if s.touch_target == "haptics":
            _, _, w, _ = self.hitboxes.get("haptics", (0, 0, 1, 1))
            x = max(self.hitboxes["haptics"][0], min(self.hitboxes["haptics"][0] + w, pos[0]))
            s.haptics_strength = (x - self.hitboxes["haptics"][0]) / max(1, w)
            self.mark_all_dirty()

    def tick(self, dt: float):
        s = self.state
        target = 1.0 if s.sidebar_open else 0.0
        s.sidebar_anim += (target - s.sidebar_anim) * min(1.0, dt * 12.0)
        if s.scene == Scene.GALLERY and abs(s.gallery_velocity) > 0.1:
            s.gallery_swipe_x += s.gallery_velocity * dt
            s.gallery_velocity *= 0.9
            self.mark_all_dirty()
        if s.toast and time.perf_counter() > s.toast_until:
            s.toast = ""
            self.mark_all_dirty()

    def handle(self, event: InputEvent):
        t0 = time.perf_counter()
        s = self.state

        if event.type == EventType.ENCODER_DETENT:
            s.filter_idx = (s.filter_idx + (1 if event.delta >= 0 else -1)) % len(FILTERS)
            self.mark_all_dirty()
        elif event.type == EventType.ENCODER_PRESS:
            s.debug_overlay = not s.debug_overlay
            self.mark_all_dirty()
        elif event.type == EventType.TOGGLE_GRID:
            s.grid_mode_idx = (s.grid_mode_idx + 1) % len(GRID_MODES)
            self.mark_all_dirty()
        elif event.type == EventType.TOGGLE_LEVEL:
            s.level_mode_idx = (s.level_mode_idx + 1) % len(LEVEL_MODES)
            self.mark_all_dirty()
        elif event.type == EventType.TOGGLE_LANG:
            s.lang = "de" if s.lang == "en" else "en"
            self.mark_all_dirty()
        elif event.type == EventType.FLASH_TOGGLE:
            s.flash_on = not s.flash_on
            self.mark_all_dirty()
        elif event.type == EventType.SHUTTER_PRESS:
            s.toast = s.t("saved")
            s.toast_until = time.perf_counter() + 0.6
            s.freeze_until = time.perf_counter() + 0.6
            self.mark_all_dirty()
        elif event.type == EventType.SHUTDOWN:
            s.shutdown_requested = True
        elif event.type == EventType.BACK:
            s.scene = Scene.CAMERA
            self.mark_all_dirty()
        elif event.type == EventType.TOUCH_DOWN:
            s.touch_down = True
            s.touch_pos = event.pos
            s.touch_target = self._hit(event.pos)
            self._on_press(s.touch_target)
        elif event.type == EventType.TOUCH_MOVE:
            s.touch_pos = event.pos
            self._update_sidebar_drag(event.pos)
            if s.scene == Scene.GALLERY:
                s.gallery_velocity = event.delta * 6.0
                s.gallery_swipe_x += event.delta
                self.mark_all_dirty()
        elif event.type == EventType.TOUCH_UP:
            s.touch_down = False
            s.touch_target = None

        s.last_input_latency_ms = (time.perf_counter() - t0) * 1000.0
