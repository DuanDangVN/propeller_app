"""Tests for linear calibration and independent tare behavior."""

import json
from pathlib import Path

import numpy as np
import pytest

from processing.calibration import (
    CalibrationCoefficients,
    calibration_value_from_mass,
    summarize_voltage_samples,
    two_point_calibration,
)


def test_linear_conversion() -> None:
    calibration = CalibrationCoefficients(slope=100.0, intercept=3.0)
    assert calibration.convert(0.5) == pytest.approx(53.0)


def test_zero_does_not_change_coefficients() -> None:
    calibration = CalibrationCoefficients(100.0, 3.0).with_zero(0.25)
    converted = calibration.convert(np.asarray([0.25, 0.30]))
    assert calibration.slope == 100.0
    assert calibration.intercept == 3.0
    assert converted == pytest.approx([0.0, 5.0])


def test_two_point_calibration() -> None:
    result = two_point_calibration(1.0, 10.0, 3.0, 50.0)
    assert result.slope == pytest.approx(20.0)
    assert result.intercept == pytest.approx(-10.0)


def test_two_point_rejects_equal_voltage() -> None:
    with pytest.raises(ValueError):
        two_point_calibration(1.0, 10.0, 1.0, 20.0)


def test_voltage_summary_uses_only_recent_window() -> None:
    samples = np.concatenate((np.zeros(1000), np.full(500, 2.0)))
    summary = summarize_voltage_samples(samples, 1000.0, window_s=0.5)
    assert summary.mean_v == pytest.approx(2.0)
    assert summary.standard_deviation_v == pytest.approx(0.0)
    assert summary.peak_to_peak_v == pytest.approx(0.0)
    assert summary.sample_count == 500


def test_voltage_summary_rejects_empty_samples() -> None:
    with pytest.raises(ValueError, match="No voltage samples"):
        summarize_voltage_samples([], 1000.0)


def test_old_calibration_gram_input_converts_to_engineering_units() -> None:
    assert calibration_value_from_mass(2000, "Thrust") == pytest.approx(19.6133)
    assert calibration_value_from_mass(2000, "Torque") == pytest.approx(
        0.784532
    )


def test_bundled_default_uses_nta_rig_calibration() -> None:
    calibration_path = (
        Path(__file__).resolve().parents[1] / "public" / "storeage_calib.json"
    )
    data = json.loads(calibration_path.read_text(encoding="utf-8"))

    assert data == pytest.approx(
        {
            "thrust_slope": 61.9097335779648,
            "thrust_intercept": -19.3004887439589,
            "thrust_zero_offset_v": 0.3119909100402147,
            "torque_slope": 0.7621357785117475,
            "torque_intercept": -0.435808379472578,
            "torque_zero_offset_v": 0.5883615249954164,
        }
    )

    thrust = CalibrationCoefficients(
        data["thrust_slope"],
        data["thrust_intercept"],
        data["thrust_zero_offset_v"],
    )
    torque = CalibrationCoefficients(
        data["torque_slope"],
        data["torque_intercept"],
        data["torque_zero_offset_v"],
    )
    assert thrust.convert(data["thrust_zero_offset_v"]) == pytest.approx(0.0)
    assert torque.convert(data["torque_zero_offset_v"]) == pytest.approx(0.0)
