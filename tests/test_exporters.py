"""Tests for CSV and Excel measurement exports."""

import pandas as pd

from storage.exporters import save_measurements_csv, save_measurements_excel


def _rows() -> list[dict[str, object]]:
    return [
        {
            "timestamp": "2026-07-29T12:00:00+07:00",
            "elapsed_time_s": 0.0,
            "force_voltage_raw_v": 1.0,
            "torque_voltage_raw_v": 2.0,
            "force_raw_n": 3.0,
            "torque_raw_nm": 4.0,
            "force_filtered_n": 3.1,
            "torque_filtered_nm": 4.1,
            "rpm": 1000,
            "acquisition_status": "OK",
        }
    ]


def test_csv_can_exclude_raw_columns(tmp_path) -> None:
    path = tmp_path / "measurements.csv"
    save_measurements_csv(path, _rows(), save_raw=False)
    frame = pd.read_csv(path)
    assert "force_filtered_n" in frame.columns
    assert "force_voltage_raw_v" not in frame.columns


def test_excel_contains_required_sheets(tmp_path) -> None:
    path = tmp_path / "measurements.xlsx"
    save_measurements_excel(
        path,
        _rows(),
        save_raw=True,
        configuration={"filter": {"mode": "moving_average"}},
        calibration_rows=[{"channel": "Force", "slope": 1.0}],
        statistics_rows=[{"channel": "Force", "mean": 3.1}],
    )
    assert pd.ExcelFile(path).sheet_names == [
        "Measurements",
        "Configuration",
        "Calibration",
        "Statistics",
    ]
