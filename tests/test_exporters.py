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


def test_csv_contains_time_and_primary_measurements(tmp_path) -> None:
    path = tmp_path / "measurements.csv"
    save_measurements_csv(path, _rows())
    frame = pd.read_csv(path)
    assert frame.columns.tolist() == [
        "Time Data (s)",
        "Thrust (N)",
        "Torque (N.m)",
        "RPM",
    ]
    assert frame.iloc[0].tolist() == [0.0, 3.1, 4.1, 1000.0]


def test_excel_contains_one_simple_measurement_sheet(tmp_path) -> None:
    path = tmp_path / "measurements.xlsx"
    save_measurements_excel(path, _rows())
    assert pd.ExcelFile(path).sheet_names == ["Measurements"]
    frame = pd.read_excel(path)
    assert frame.columns.tolist() == [
        "Time Data (s)",
        "Thrust (N)",
        "Torque (N.m)",
        "RPM",
    ]
