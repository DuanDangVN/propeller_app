"""Tests for the streaming signal filters."""

import numpy as np
import pytest

from processing.filters import FilterSettings, SignalFilter, moving_average


def test_moving_average_uses_partial_initial_windows() -> None:
    result = moving_average(np.asarray([1.0, 2.0, 3.0, 4.0]), 3)
    assert result == pytest.approx([1.0, 1.5, 2.0, 3.0])


def test_streaming_moving_average_preserves_block_state() -> None:
    settings = FilterSettings(mode="moving_average", moving_average_window=3)
    signal_filter = SignalFilter(settings, sampling_rate_hz=1000.0)
    first = signal_filter.process(np.asarray([1.0, 2.0]))
    second = signal_filter.process(np.asarray([3.0, 4.0]))
    assert first == pytest.approx([1.0, 1.5])
    assert second == pytest.approx([2.0, 3.0])


def test_median_window_must_be_odd() -> None:
    settings = FilterSettings(mode="median", median_window=4)
    with pytest.raises(ValueError):
        SignalFilter(settings, sampling_rate_hz=1000.0)


def test_butterworth_reduces_high_frequency_noise() -> None:
    sampling_rate = 1000.0
    time_s = np.arange(2000) / sampling_rate
    low = np.sin(2 * np.pi * 2 * time_s)
    noise = 0.8 * np.sin(2 * np.pi * 200 * time_s)
    signal_filter = SignalFilter(
        FilterSettings(
            mode="butterworth",
            lowpass_cutoff_hz=20.0,
            lowpass_order=4,
        ),
        sampling_rate,
    )
    filtered = signal_filter.process(low + noise)
    raw_error = np.std((low + noise)[500:] - low[500:])
    filtered_error = np.std(filtered[500:] - low[500:])
    assert filtered_error < raw_error * 0.4
