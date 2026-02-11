"""Camera service with bounded async save pipeline for Pi 3A+ (512MB-safe)."""

from __future__ import annotations

import logging
import json
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    from picamera2 import Picamera2
    from libcamera import Transform
    HAS_CAMERA = True
except ImportError:  # pragma: no cover - CI usually has no camera stack
    HAS_CAMERA = False

    class Picamera2:  # type: ignore[override]
        def __init__(self):
            self._started = False

        def create_preview_configuration(self, **kwargs):
            return kwargs

        def configure(self, _config):
            return None

        def start(self):
            self._started = True

        def stop(self):
            self._started = False

        def capture_array(self, name: str = "main"):
            _ = name
            if np is None:
                return None
            return np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        def capture_file(self, path: str):
            Path(path).write_bytes(b"mock-image")

        def set_controls(self, _controls):
            return None

    class Transform:  # type: ignore[override]
        def __init__(self, **kwargs):
            self.kwargs = kwargs

def _load_runtime_config() -> dict:
    cfg_path = Path(__file__).with_name("config_defaults.json")
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text())
        except Exception:
            return {}
    return {}


RUNTIME_CFG = _load_runtime_config()

logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    preview_width: int = 640
    preview_height: int = 480
    preview_fps: int = 30
    capture_width: int = 3280
    capture_height: int = 2464
    capture_quality: int = 95
    hflip: bool = False
    vflip: bool = False


@dataclass
class CameraStats:
    preview_fps: float = 0.0
    capture_count: int = 0
    dropped_frames: int = 0
    queue_depth: int = 0


class CameraProcess:
    """Capture loop abstraction retained for API compatibility."""

    def __init__(self, config: CameraConfig, ipc_manager):
        self.config = config
        self.ipc = ipc_manager
        self.camera: Optional[Picamera2] = None
        self.running = False
        self.preview_active = False
        self.stats = CameraStats()
        self.frame_count = 0
        self.last_stats_time = time.perf_counter()
        self._init_camera()

    def _init_camera(self):
        try:
            self.camera = Picamera2()
            preview_config = self.camera.create_preview_configuration(
                main={
                    "size": (self.config.preview_width, self.config.preview_height),
                    "format": "RGB888",
                },
                transform=Transform(hflip=self.config.hflip, vflip=self.config.vflip),
                buffer_count=3,
                queue=False,
            )
            self.camera.configure(preview_config)
        except Exception as exc:
            logger.warning("camera init fallback active: %s", exc)
            self.camera = Picamera2()

    def start_preview(self):
        if self.camera and not self.preview_active:
            self.camera.start()
            self.preview_active = True

    def stop_preview(self):
        if self.camera and self.preview_active:
            self.camera.stop()
            self.preview_active = False

    def capture_preview_frame(self) -> Optional[np.ndarray]:
        if not self.camera:
            return None
        frame = self.camera.capture_array("main")
        if frame is None:
            self.stats.dropped_frames += 1
            return None
        return frame

    def capture_photo(self, filepath: Path) -> bool:
        if not self.camera:
            return False
        try:
            self.camera.capture_file(str(filepath))
            self.stats.capture_count += 1
            return True
        except Exception as exc:
            logger.error("capture failed: %s", exc)
            return False

    def set_zoom(self, zoom: float):
        zoom = max(1.0, min(4.0, zoom))
        if self.camera:
            self.camera.set_controls({"ScalerCrop": zoom})

    def set_exposure_compensation(self, ev: float):
        if self.camera:
            self.camera.set_controls({"ExposureValue": float(max(-2.0, min(2.0, ev)))})

    def update_stats(self):
        now = time.perf_counter()
        dt = now - self.last_stats_time
        if dt >= 1.0:
            self.stats.preview_fps = self.frame_count / dt
            self.frame_count = 0
            self.last_stats_time = now

    def shutdown(self):
        self.running = False
        self.stop_preview()


class CameraService:
    """High-level camera service with bounded queues and async saving."""

    def __init__(self, config: CameraConfig):
        self.config = config
        self.ipc = None
        self._proc = CameraProcess(config, ipc_manager=type("I", (), {"frame_buffer": None})())
        self._save_queue: "queue.Queue[tuple[Path, Optional[np.ndarray], Optional[Callable]]]" = queue.Queue(maxsize=int(RUNTIME_CFG.get("memory", {}).get("save_queue_max", 4)))
        self._save_thread = threading.Thread(target=self._save_worker, daemon=True)
        self._running = False
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()

    def start(self):
        if self._running:
            return
        self._running = True
        self._proc.start_preview()
        if not self._save_thread.is_alive():
            self._save_thread = threading.Thread(target=self._save_worker, daemon=True)
            self._save_thread.start()

    def stop(self):
        self._running = False
        self._proc.shutdown()
        self._save_queue.put((Path(""), None, None))
        if self._save_thread.is_alive():
            self._save_thread.join(timeout=1.5)

    def pump_preview(self):
        frame = self._proc.capture_preview_frame()
        if frame is not None:
            with self._frame_lock:
                self._latest_frame = frame
            self._proc.frame_count += 1
        self._proc.stats.queue_depth = self._save_queue.qsize()
        self._proc.update_stats()

    def get_preview_frame(self) -> Optional[np.ndarray]:
        with self._frame_lock:
            return self._latest_frame

    def capture_photo(self, filepath: Path, callback: Optional[Callable] = None):
        frame_ref = self.get_preview_frame()
        try:
            self._save_queue.put_nowait((filepath, frame_ref, callback))
        except queue.Full:
            if callback:
                callback(False, filepath)

    def _save_worker(self):
        while True:
            filepath, frame_ref, callback = self._save_queue.get()
            if not self._running and filepath == Path(""):
                return
            ok = False
            try:
                if frame_ref is not None and np is not None:
                    from PIL import Image

                    img = Image.fromarray(frame_ref)
                    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if filepath.suffix.lower() in {".jpg", ".jpeg", ".png"}:
                        img.save(filepath)
                    else:
                        img.save(filepath.with_suffix(".jpg"))
                    _ = ts
                else:
                    ok = self._proc.capture_photo(filepath)
                ok = True if frame_ref is not None else ok
            except Exception as exc:
                logger.error("async save failed: %s", exc)
            if callback:
                callback(ok, filepath)

    def set_zoom(self, zoom: float):
        self._proc.set_zoom(zoom)

    def set_exposure_compensation(self, ev: float):
        self._proc.set_exposure_compensation(ev)

    def get_stats(self) -> CameraStats:
        return self._proc.stats


class SceneAnalyzer:
    def __init__(self):
        self.last_analysis_time = 0.0
        self.analysis_interval = 1.0

    def analyze(self, frame: Optional[np.ndarray], lux: float) -> str:
        now = time.perf_counter()
        if now - self.last_analysis_time < self.analysis_interval:
            return "auto"
        self.last_analysis_time = now
        if lux < 10:
            return "night"
        if lux < 100:
            return "low_light"
        if lux > 10_000:
            return "bright"
        if frame is not None and frame.mean() < 40:
            return "low_light"
        return "auto"
