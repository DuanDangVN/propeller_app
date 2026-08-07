"""Simple CSV and Excel exporters for time and primary measurements."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

EXPORT_COLUMNS = {
    "elapsed_time_s": "Time Data (s)",
    "force_filtered_n": "Thrust (N)",
    "torque_filtered_nm": "Torque (N.m)",
    "rpm": "RPM",
}


def _measurement_frame(
    rows: Sequence[Mapping[str, Any]],
) -> pd.DataFrame:
    if not rows:
        raise ValueError("No measurement data is available to save.")
    frame = pd.DataFrame(rows)
    missing_columns = [
        column for column in EXPORT_COLUMNS if column not in frame.columns
    ]
    if missing_columns:
        raise ValueError(
            "Measurement data is missing required columns: "
            + ", ".join(missing_columns)
        )
    return frame[list(EXPORT_COLUMNS)].rename(columns=EXPORT_COLUMNS)


def save_measurements_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    """Save time, Thrust, Torque and RPM rows to UTF-8 CSV."""
    frame = _measurement_frame(rows)
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def save_measurements_excel(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    """Save time, Thrust, Torque and RPM to one Excel worksheet."""
    frame = _measurement_frame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Measurements", index=False)
