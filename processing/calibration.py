"""Linear calibration and independent zero/tare handling."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import NDArray


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
