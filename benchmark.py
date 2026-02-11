#!/usr/bin/env python3
"""Pi-3A+ focused benchmark with dependency-safe fallbacks and JSON output."""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None

from camera_service import CameraConfig, CameraService


@dataclass
class BenchmarkReport:
    avg_frame_ms: float
    p95_frame_ms: float
    max_frame_ms: float
    avg_input_latency_ms: float
    max_input_latency_ms: float
    max_queue_depth: int
    rss_mb: Optional[float]


def _rss_fallback_mb() -> Optional[float]:
    if psutil is not None:
        return float(psutil.Process().memory_info().rss / (1024 * 1024))

    # Linux /proc fallback
    status = Path("/proc/self/status")
    if status.exists():
        for line in status.read_text().splitlines():
            if line.startswith("VmRSS:"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    return float(int(parts[1]) / 1024.0)

    return None


def _stats(samples: list[float]) -> tuple[float, float, float]:
    if not samples:
        return 0.0, 0.0, 0.0

    if np is not None:
        arr = np.array(samples, dtype=float)
        return float(np.mean(arr)), float(np.percentile(arr, 95)), float(np.max(arr))

    sorted_s = sorted(samples)
    mean = sum(sorted_s) / len(sorted_s)
    p95_idx = min(len(sorted_s) - 1, int((len(sorted_s) - 1) * 0.95))
    return float(mean), float(sorted_s[p95_idx]), float(sorted_s[-1])


def run_benchmark(seconds: float = 3.0, fps: float = 30.0) -> BenchmarkReport:
    svc = CameraService(CameraConfig())
    svc.start()

    frame_times: list[float] = []
    input_latencies: list[float] = []
    max_q = 0

    start = time.perf_counter()
    last = start

    while time.perf_counter() - start < seconds:
        loop_t0 = time.perf_counter()
        svc.pump_preview()

        now = time.perf_counter()
        frame_times.append((now - last) * 1000.0)
        last = now

        t_input = time.perf_counter()
        _ = svc.get_preview_frame()
        input_latencies.append((time.perf_counter() - t_input) * 1000.0)

        max_q = max(max_q, svc.get_stats().queue_depth)

        sleep = (1.0 / fps) - (time.perf_counter() - loop_t0)
        if sleep > 0:
            time.sleep(sleep)

    svc.stop()

    avg_frame, p95_frame, max_frame = _stats(frame_times)
    avg_in, _, max_in = _stats(input_latencies)

    return BenchmarkReport(
        avg_frame_ms=avg_frame,
        p95_frame_ms=p95_frame,
        max_frame_ms=max_frame,
        avg_input_latency_ms=avg_in,
        max_input_latency_ms=max_in,
        max_queue_depth=int(max_q),
        rss_mb=_rss_fallback_mb(),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--json", nargs="?", const="-", default=None)
    args = parser.parse_args()

    report = run_benchmark(args.seconds, args.fps)
    payload = json.dumps(asdict(report), indent=2)

    if args.json is not None:
        if args.json == "-":
            print(payload)
        else:
            out_path = Path(args.json)
            out_path.write_text(payload + os.linesep)
            print(f"wrote benchmark json: {out_path}")
        return 0

    print("SelimCam benchmark")
    print(f"avg frame     : {report.avg_frame_ms:.2f} ms")
    print(f"p95 frame     : {report.p95_frame_ms:.2f} ms")
    print(f"max frame     : {report.max_frame_ms:.2f} ms")
    print(f"avg input     : {report.avg_input_latency_ms:.3f} ms")
    print(f"max input     : {report.max_input_latency_ms:.3f} ms")
    print(f"max queue     : {report.max_queue_depth}")
    print(f"process rss   : {report.rss_mb if report.rss_mb is not None else 'n/a'} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
