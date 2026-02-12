#!/usr/bin/env python3
"""PC simulator using shared core UI/controller with portrait default (480x800)."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pygame

from benchmark import _rss_fallback_mb
from camera_service import CameraConfig, CameraService
from core.app_controller import AppController
from core.ui_renderer import UIRenderer, ViewportMapper
from adapters.pc_io import PCIOAdapter


def _load_config() -> dict:
    path = Path(__file__).with_name("config_defaults.json")
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--landscape", action="store_true")
    args = parser.parse_args()

    cfg = _load_config()
    internal = (800, 480) if args.landscape else (480, 800)
    fps = int(cfg.get("preview", {}).get("fps", 30))

    pygame.init()
    screen = pygame.display.set_mode(internal, pygame.RESIZABLE)
    pygame.display.set_caption("SelimCam PC Simulator")
    clock = pygame.time.Clock()

    mapper = ViewportMapper(internal)
    mapper.update(*screen.get_size())
    renderer = UIRenderer(screen, internal[0], internal[1], cfg.get("ui", {}).get("font_path"))
    controller = AppController(*internal)
    io = PCIOAdapter(mapper.to_internal)

    cam = CameraService(CameraConfig(preview_width=640, preview_height=480, preview_fps=fps))
    cam.start()

    last = time.perf_counter()
    running = True
    while running:
        for ev in io.poll():
            if ev.type.name == "SHUTDOWN":
                running = False
            controller.handle(ev)

        if pygame.display.get_surface().get_size() != mapper.view.size:
            mapper.update(*pygame.display.get_surface().get_size())

        now = time.perf_counter()
        dt = now - last
        last = now
        controller.tick(dt)

        cam.pump_preview()
        queue_depth = cam.get_stats().queue_depth

        frame, hitboxes = renderer.compose(controller.state, _rss_fallback_mb(), queue_depth, now)
        controller.set_hitboxes(hitboxes)

        mapper.blit_scaled(screen, frame)
        rects = controller.pop_dirty()
        if mapper.view.size == internal and rects:
            pygame.display.update(rects)
        else:
            pygame.display.flip()
        clock.tick(fps)

    cam.stop()
    pygame.quit()


if __name__ == "__main__":
    main()
