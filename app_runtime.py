"""Runtime paths, logging and packaged-app diagnostics."""

from __future__ import annotations

import faulthandler
import logging
import os
from pathlib import Path
import shutil
import sys
import time


SMOKE_TEST_MODE = "--smoke-test" in sys.argv
SMOKE_TRACE_PATH = (
    Path(os.environ.get("TEMP", Path.home()))
    / "PropellerApp_smoke_trace.txt"
)


def smoke_trace(message: str) -> None:
    """Write minimal startup diagnostics during packaged smoke tests."""
    if not SMOKE_TEST_MODE:
        return
    with SMOKE_TRACE_PATH.open("a", encoding="utf-8") as trace_file:
        trace_file.write(f"{time.time():.3f} {message}\n")


if SMOKE_TEST_MODE and SMOKE_TRACE_PATH.exists():
    SMOKE_TRACE_PATH.unlink()
SMOKE_STACK_HANDLE = None
if SMOKE_TEST_MODE:
    smoke_stack_path = (
        Path(os.environ.get("TEMP", Path.home()))
        / "PropellerApp_smoke_stack.txt"
    )
    SMOKE_STACK_HANDLE = smoke_stack_path.open("w", encoding="utf-8")
    faulthandler.dump_traceback_later(
        10,
        repeat=True,
        file=SMOKE_STACK_HANDLE,
    )
smoke_trace("stdlib imports complete")


IS_FROZEN = bool(getattr(sys, "frozen", False))
PROJECT_DIR = Path(__file__).resolve().parent
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_DIR))
APP_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else PROJECT_DIR
PUBLIC_DIR = BUNDLE_DIR / "public"
if IS_FROZEN:
    USER_DATA_DIR = (
        Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PropellerApp"
    )
else:
    USER_DATA_DIR = PUBLIC_DIR

# Keep exported measurements beside the executable so a portable copy of the
# application also keeps its CSV and Excel files in the same parent folder.
EXPORT_DIR = APP_DIR / "Export data"

USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
APP_CONFIG_PATH = USER_DATA_DIR / "app_config.json"
CALIBRATION_PATH = USER_DATA_DIR / "storeage_calib.json"
for user_path in (APP_CONFIG_PATH, CALIBRATION_PATH):
    bundled_default = PUBLIC_DIR / user_path.name
    if not user_path.exists() and bundled_default.exists():
        shutil.copy2(bundled_default, user_path)

LOG_DIR = USER_DATA_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "propeller_app.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

CALIBRATION_CAPTURE_WINDOW_S = 0.5
CALIBRATION_MIN_DELTA_V = 0.002
RPM_SENSOR_PROFILE = "two-pulse-v1"

smoke_trace("runtime paths and logging configured")
