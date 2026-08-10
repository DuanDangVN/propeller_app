"""Stateful signal filters for continuous NI acquisition blocks."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import median_filter as scipy_median_filter
from scipy.signal import butter, sosfilt, sosfilt_zi

FloatArray = NDArray[np.float64]


@dataclass(slots=True)
class FilterSettings:
    """User-configurable filter settings."""

    mode: str = "butterworth"
    moving_average_window: int = 9
    median_window: int = 5
    lowpass_cutoff_hz: float = 10.0
    lowpass_order: int = 4

    def validate(self, sampling_rate_hz: float) -> None:
        """Validate settings against the current sampling rate."""
        if self.mode not in {"none", "moving_average", "median", "butterworth"}:
            raise ValueError("Unknown filter mode.")
        if self.moving_average_window < 1:
            raise ValueError("Moving-average window must be at least 1.")
        if self.median_window < 1 or self.median_window % 2 == 0:
            raise ValueError("Median window must be a positive odd number.")
        if self.mode == "butterworth":
            if self.lowpass_order < 1 or self.lowpass_order > 12:
                raise ValueError("Low-pass order must be between 1 and 12.")
            if not 0 < self.lowpass_cutoff_hz < sampling_rate_hz / 2:
                raise ValueError(
                    "Low-pass cutoff must be below the Nyquist frequency."
                )


def moving_average(values: FloatArray, window: int) -> FloatArray:
    """Return a causal moving average with partial windows at the start."""
    data = np.asarray(values, dtype=np.float64)
    if window < 1:
        raise ValueError("Moving-average window must be at least 1.")
    if data.size == 0 or window == 1:
        return data.copy()
    cumulative = np.cumsum(np.insert(data, 0, 0.0))
    result = np.empty_like(data)
    for index in range(data.size):
        start = max(0, index - window + 1)
        result[index] = (cumulative[index + 1] - cumulative[start]) / (
            index - start + 1
        )
    return result


def median_filter(values: FloatArray, window: int) -> FloatArray:
    """Return a same-length median-filtered signal."""
    data = np.asarray(values, dtype=np.float64)
    if window < 1 or window % 2 == 0:
        raise ValueError("Median window must be a positive odd number.")
    if data.size == 0 or window == 1:
        return data.copy()
    return np.asarray(
        scipy_median_filter(data, size=window, mode="nearest"),
        dtype=np.float64,
    )


class SignalFilter:
    """Filter one block at a time while preserving streaming state."""

    def __init__(self, settings: FilterSettings, sampling_rate_hz: float) -> None:
        self.settings = settings
        self.sampling_rate_hz = float(sampling_rate_hz)
        self._history = np.empty(0, dtype=np.float64)
        self._sos: NDArray[np.float64] | None = None
        self._zi: NDArray[np.float64] | None = None
        self.settings.validate(self.sampling_rate_hz)
        if self.settings.mode == "butterworth":
            self._sos = butter(
                self.settings.lowpass_order,
                self.settings.lowpass_cutoff_hz,
                btype="low",
                fs=self.sampling_rate_hz,
                output="sos",
            )

    def reset(self) -> None:
        """Clear the filter history."""
        self._history = np.empty(0, dtype=np.float64)
        self._zi = None

    def process(self, values: FloatArray) -> FloatArray:
        """Filter a block and preserve state for the next block."""
        data = np.asarray(values, dtype=np.float64)
        if data.size == 0 or self.settings.mode == "none":
            return data.copy()

        if self.settings.mode == "butterworth":
            assert self._sos is not None
            if self._zi is None:
                self._zi = sosfilt_zi(self._sos) * data[0]
            filtered, self._zi = sosfilt(self._sos, data, zi=self._zi)
            return np.asarray(filtered, dtype=np.float64)

        if self.settings.mode == "moving_average":
            history_length = max(0, self.settings.moving_average_window - 1)
            combined = np.concatenate((self._history, data))
            filtered = moving_average(
                combined,
                self.settings.moving_average_window,
            )
        else:
            history_length = max(0, self.settings.median_window - 1)
            combined = np.concatenate((self._history, data))
            filtered = median_filter(combined, self.settings.median_window)

        self._history = (
            combined[-history_length:]
            if history_length
            else np.empty(0, dtype=np.float64)
        )
        return np.asarray(filtered[-data.size:], dtype=np.float64)
