"""CSV and multi-sheet Excel exporters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

RAW_COLUMNS = [
    "force_voltage_raw_v",
    "torque_voltage_raw_v",
    "force_raw_n",
    "torque_raw_nm",
]


def _measurement_frame(
    rows: Sequence[Mapping[str, Any]],
    save_raw: bool,
) -> pd.DataFrame:
    if not rows:
        raise ValueError("No measurement data is available to save.")
    frame = pd.DataFrame(rows)
    if not save_raw:
        frame = frame.drop(
            columns=[column for column in RAW_COLUMNS if column in frame],
        )
    return frame


def save_measurements_csv(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    save_raw: bool,
) -> None:
    """Save sample rows to UTF-8 CSV."""
    frame = _measurement_frame(rows, save_raw)
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def save_measurements_excel(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    save_raw: bool,
    configuration: Mapping[str, Mapping[str, Any]],
    calibration_rows: Sequence[Mapping[str, Any]],
    statistics_rows: Sequence[Mapping[str, Any]],
) -> None:
    """Save measurements and metadata to four Excel sheets."""
    frame = _measurement_frame(rows, save_raw)
    config_rows = []
    for section, values in configuration.items():
        for key, value in values.items():
            config_rows.append(
                {
                    "section": section,
                    "parameter": key,
                    "value": value,
                }
            )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Measurements", index=False)
        pd.DataFrame(config_rows).to_excel(
            writer,
            sheet_name="Configuration",
            index=False,
        )
        pd.DataFrame(calibration_rows).to_excel(
            writer,
            sheet_name="Calibration",
            index=False,
        )
        pd.DataFrame(statistics_rows).to_excel(
            writer,
            sheet_name="Statistics",
            index=False,
        )
