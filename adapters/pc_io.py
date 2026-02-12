"""PC input adapter: mouse/touch + keyboard to shared InputEvent stream."""

from __future__ import annotations

import time
from typing import Callable, List, Tuple

import pygame

from core.input_events import EventType, InputEvent


class PCIOAdapter:
    def __init__(self, map_pos: Callable[[Tuple[int, int]], Tuple[int, int]]):
        self.map_pos = map_pos
        self._last_touch = (0, 0)

    def poll(self) -> List[InputEvent]:
        out: List[InputEvent] = []
        now = time.perf_counter()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                out.append(InputEvent(EventType.SHUTDOWN, timestamp=now))
            elif event.type == pygame.VIDEORESIZE:
                # handled by entrypoint
                continue
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                p = self.map_pos(event.pos)
                self._last_touch = p
                out.append(InputEvent(EventType.TOUCH_DOWN, pos=p, timestamp=now))
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                p = self.map_pos(event.pos)
                out.append(InputEvent(EventType.TOUCH_UP, pos=p, timestamp=now))
            elif event.type == pygame.MOUSEMOTION and any(event.buttons):
                p = self.map_pos(event.pos)
                delta = p[0] - self._last_touch[0]
                self._last_touch = p
                out.append(InputEvent(EventType.TOUCH_MOVE, pos=p, delta=delta, timestamp=now))
            elif event.type == pygame.KEYDOWN:
                keymap = {
                    pygame.K_SPACE: EventType.SHUTTER_PRESS,
                    pygame.K_LEFT: EventType.ENCODER_DETENT,
                    pygame.K_RIGHT: EventType.ENCODER_DETENT,
                    pygame.K_RETURN: EventType.ENCODER_PRESS,
                    pygame.K_ESCAPE: EventType.BACK,
                    pygame.K_g: EventType.TOGGLE_GRID,
                    pygame.K_l: EventType.TOGGLE_LEVEL,
                    pygame.K_t: EventType.TOGGLE_LANG,
                    pygame.K_s: EventType.SHUTDOWN,
                    pygame.K_f: EventType.FLASH_TOGGLE,
                    pygame.K_F1: EventType.ENCODER_PRESS,
                }
                if event.key in keymap:
                    delta = -1 if event.key == pygame.K_LEFT else 1 if event.key == pygame.K_RIGHT else 0
                    out.append(InputEvent(keymap[event.key], delta=delta, timestamp=now))
        return out
