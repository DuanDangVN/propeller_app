"""Tests for linear calibration and independent tare behavior."""

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
