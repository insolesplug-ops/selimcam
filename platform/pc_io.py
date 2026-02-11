"""PC input adapter: mouse/touch + keyboard to shared InputEvent stream."""

from __future__ import annotations

import time
from typing import List

import pygame

from core.input_events import EventType, InputEvent


class PCIOAdapter:
    def poll(self) -> List[InputEvent]:
        out: List[InputEvent] = []
        now = time.perf_counter()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                out.append(InputEvent(EventType.SHUTDOWN, timestamp=now))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                out.append(InputEvent(EventType.TOUCH_DOWN, pos=event.pos, timestamp=now))
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                out.append(InputEvent(EventType.TOUCH_UP, pos=event.pos, timestamp=now))
            elif event.type == pygame.MOUSEMOTION:
                out.append(InputEvent(EventType.TOUCH_MOVE, pos=event.pos, timestamp=now))
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
                }
                if event.key in keymap:
                    delta = -1 if event.key == pygame.K_LEFT else 1 if event.key == pygame.K_RIGHT else 0
                    out.append(InputEvent(keymap[event.key], delta=delta, timestamp=now))
        return out
