"""Linear calibration and independent zero/tare handling."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class VoltageSummary:
    """Statistics for the most recent calibration voltage window."""

    mean_v: float
    standard_deviation_v: float
    peak_to_peak_v: float
    sample_count: int


def calibration_value_from_mass(
    mass_g: float,
    parameter: str,
    torque_arm_m: float = 0.04,
    gravity_m_s2: float = 9.80665,
) -> float:
    """Convert the old calibration UI's gram input to N or N.m."""
    mass_g = float(mass_g)
    torque_arm_m = float(torque_arm_m)
    gravity_m_s2 = float(gravity_m_s2)
    if not np.isfinite(mass_g) or mass_g < 0:
        raise ValueError("Mass must be zero or positive.")
    if not np.isfinite(gravity_m_s2) or gravity_m_s2 <= 0:
        raise ValueError("Gravity must be positive and finite.")

    force_n = mass_g * 0.001 * gravity_m_s2
    if parameter == "Thrust":
        return float(force_n)
    if parameter == "Torque":
        if not np.isfinite(torque_arm_m) or torque_arm_m <= 0:
            raise ValueError("Torque arm must be positive and finite.")
        return float(force_n * torque_arm_m)
    raise ValueError("Parameter must be Thrust or Torque.")


def summarize_voltage_samples(
    samples: float | Iterable[float] | NDArray[np.float64],
    sampling_rate_hz: float,
    window_s: float = 0.5,
) -> VoltageSummary:
    """Summarize only the newest samples so old loads do not bias a capture."""
    sampling_rate_hz = float(sampling_rate_hz)
    window_s = float(window_s)
    if not np.isfinite(sampling_rate_hz) or sampling_rate_hz <= 0:
        raise ValueError("Sampling rate must be positive and finite.")
    if not np.isfinite(window_s) or window_s <= 0:
        raise ValueError("Calibration window must be positive and finite.")

    values = np.asarray(samples, dtype=np.float64).reshape(-1)
    if values.size == 0:
        raise ValueError("No voltage samples are available.")
    if not np.all(np.isfinite(values)):
        raise ValueError("Voltage samples must be finite.")

    requested = max(1, int(round(sampling_rate_hz * window_s)))
    recent = values[-requested:]
    return VoltageSummary(
        mean_v=float(np.mean(recent)),
        standard_deviation_v=float(np.std(recent)),
        peak_to_peak_v=float(np.ptp(recent)),
        sample_count=int(recent.size),
    )


@dataclass(frozen=True, slots=True)
class CalibrationCoefficients:
    """Linear calibration coefficients plus an independent tare offset."""

    slope: float
    intercept: float
    zero_offset_v: float | None = None

    def validate(self) -> None:
        """Raise ValueError if a coefficient is invalid."""
        values = (self.slope, self.intercept)
        if not all(np.isfinite(value) for value in values):
            raise ValueError("Calibration coefficients must be finite.")
        if self.zero_offset_v is not None and not np.isfinite(self.zero_offset_v):
            raise ValueError("Zero offset must be finite.")

    def convert(
        self,
        voltage: float | Iterable[float] | NDArray[np.float64],
    ) -> float | NDArray[np.float64]:
        """Convert voltage to engineering units and apply tare if active."""
        self.validate()
        values = np.asarray(voltage, dtype=np.float64)
        converted = self.slope * values + self.intercept
        if self.zero_offset_v is not None:
            zero_value = self.slope * self.zero_offset_v + self.intercept
            converted = converted - zero_value
        if values.ndim == 0:
            return float(converted)
        return np.asarray(converted, dtype=np.float64)

    def with_zero(self, voltage_offset: float | None) -> "CalibrationCoefficients":
        """Return a copy with a new zero voltage without changing slope/intercept."""
        if voltage_offset is not None and not np.isfinite(voltage_offset):
            raise ValueError("Zero offset must be finite.")
        return replace(self, zero_offset_v=voltage_offset)


def two_point_calibration(
    voltage_1: float,
    value_1: float,
    voltage_2: float,
    value_2: float,
) -> CalibrationCoefficients:
    """Calculate y = slope*x + intercept from two distinct points."""
    values = (voltage_1, value_1, voltage_2, value_2)
    if not all(np.isfinite(value) for value in values):
        raise ValueError("Calibration points must be finite.")
    voltage_delta = voltage_2 - voltage_1
    if abs(voltage_delta) < 1e-12:
        raise ValueError("The two calibration voltages must be different.")
    slope = (value_2 - value_1) / voltage_delta
    intercept = value_1 - slope * voltage_1
    return CalibrationCoefficients(float(slope), float(intercept))
