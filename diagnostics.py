#!/usr/bin/env python3
"""Production diagnostics for Pi 3A+ deployment."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def run(cmd: str):
    try:
        out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT, timeout=4)
        return {"ok": True, "output": out.strip()}
    except Exception as exc:
        return {"ok": False, "output": str(exc)}


def main() -> int:
    report = {
        "model": run("cat /proc/device-tree/model 2>/dev/null"),
        "memory": run("free -m"),
        "i2c_scan": run("i2cdetect -y 1"),
        "gpio": run("gpio readall"),
        "camera": run("libcamera-hello --list-cameras"),
        "touch": run("libinput list-devices | sed -n '/Touch/,+4p'"),
    }

    Path("diag_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
