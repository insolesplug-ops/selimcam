"""Integration tests with mandatory smoke checks and optional accelerated checks."""

from __future__ import annotations

import time

import pytest

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None

from benchmark import run_benchmark
from camera_service import CameraConfig, CameraService
from core.app_controller import AppController
from core.input_events import EventType, InputEvent


def test_smoke_core_controller_and_camera_service():
    controller = AppController(480, 800)
    controller.handle(InputEvent(EventType.TOGGLE_GRID, timestamp=time.perf_counter()))
    assert controller.state.grid_mode != "off"

    svc = CameraService(CameraConfig(preview_width=320, preview_height=240, preview_fps=24))
    svc.start()
    for _ in range(3):
        svc.pump_preview()
    assert svc.get_stats().queue_depth >= 0
    svc.stop()


def test_touch_hitbox_dispatch():
    controller = AppController(480, 800)
    controller.set_hitboxes({"capture": (200, 700, 80, 80), "handle": (0, 320, 16, 76)})
    controller.handle(InputEvent(EventType.TOUCH_DOWN, pos=(220, 720)))
    assert controller.state.toast != ""


def test_benchmark_json_safe_path():
    report = run_benchmark(seconds=0.1, fps=10)
    assert report.avg_frame_ms >= 0.0
    assert report.max_input_latency_ms >= 0.0


@pytest.mark.skipif(np is None, reason="numpy unavailable for ndarray-specific checks")
def test_optional_numpy_path():
    arr = np.zeros((4, 4, 3), dtype=np.uint8)
    assert int(arr.sum()) == 0
