"""Input event model shared by PC and Pi adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Tuple


class EventType(Enum):
    TOUCH_DOWN = auto()
    TOUCH_MOVE = auto()
    TOUCH_UP = auto()
    ENCODER_DETENT = auto()
    ENCODER_PRESS = auto()
    SHUTTER_PRESS = auto()
    SHUTDOWN = auto()
    FLASH_TOGGLE = auto()
    TOGGLE_GRID = auto()
    TOGGLE_LEVEL = auto()
    TOGGLE_LANG = auto()
    TOGGLE_DEBUG = auto()
    BACK = auto()


@dataclass(frozen=True)
class InputEvent:
    type: EventType
    pos: Tuple[int, int] = (0, 0)
    delta: int = 0
    timestamp: float = 0.0
