#!/usr/bin/env python3
"""Windows/PC simulation entry point using shared core renderer/controller."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pygame

from core.app_controller import AppController
from core.ui_renderer import UIRenderer
from adapters.pc_io import PCIOAdapter


def _load_config() -> dict:
    path = Path(__file__).with_name("config_defaults.json")
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def make_frame_surface(width: int, height: int, tick: float) -> pygame.Surface:
    surf = pygame.Surface((width, height))
    for y in range(height):
        c = int(20 + 40 * (y / max(1, height)))
        pygame.draw.line(surf, (c, c, c + 10), (0, y), (width, y))
    pygame.draw.circle(surf, (120, 120, 160), (width // 2, height // 2), 32 + int(8 * (tick % 1.0)))
    return surf


def main():
    cfg = _load_config()
    width = 800
    height = 480
    fps = int(cfg.get("preview", {}).get("fps", 30))

    pygame.init()
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("SelimCam Shared UI - PC")
    clock = pygame.time.Clock()

    controller = AppController(width, height)
    renderer = UIRenderer(screen, width, height)
    io = PCIOAdapter()
    debug_overlay = False

    running = True
    while running:
        for ev in io.poll():
            if ev.type.name == "SHUTDOWN":
                running = False
            controller.handle(ev)
            if ev.type.name == "ENCODER_PRESS":
                debug_overlay = not debug_overlay

        frame = make_frame_surface(width, height, time.perf_counter())
        _stats = renderer.render(controller.state, frame, show_debug=debug_overlay)
        rects = controller.pop_dirty()
        renderer.dirty_or_full(rects)
        clock.tick(fps)

    pygame.quit()


if __name__ == "__main__":
    main()
