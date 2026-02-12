#!/usr/bin/env python3
"""Pi production entry point using the exact shared core renderer/controller."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pygame

from core.app_controller import AppController
from core.ui_renderer import UIRenderer
from adapters.pi_io import PIIOAdapter


def _load_config() -> dict:
    path = Path(__file__).with_name("config_defaults.json")
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def camera_or_fallback_frame(width: int, height: int, tick: float) -> pygame.Surface:
    # placeholder for real camera surface injection; keeps zero-copy-ready surface handoff contract.
    surf = pygame.Surface((width, height))
    for y in range(height):
        c = int(16 + 36 * (y / max(1, height)))
        pygame.draw.line(surf, (c, c, c + 6), (0, y), (width, y))
    pygame.draw.rect(surf, (96, 96, 128), (width // 2 - 40, height // 2 - 22, 80, 44), 2)
    return surf


def main():
    cfg = _load_config()
    width = 800
    height = 480
    fps = int(cfg.get("preview", {}).get("fps", 30))

    pygame.init()
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("SelimCam Shared UI - Pi")
    clock = pygame.time.Clock()

    controller = AppController(width, height)
    renderer = UIRenderer(screen, width, height)
    io = PIIOAdapter()
    debug_overlay = False

    running = True
    while running:
        for ev in io.poll():
            if ev.type.name == "SHUTDOWN":
                running = False
            controller.handle(ev)
            if ev.type.name == "ENCODER_PRESS":
                debug_overlay = not debug_overlay

        frame = camera_or_fallback_frame(width, height, time.perf_counter())
        _stats = renderer.render(controller.state, frame, show_debug=debug_overlay)
        rects = controller.pop_dirty()
        renderer.dirty_or_full(rects)
        clock.tick(fps)

    pygame.quit()


if __name__ == "__main__":
    main()
