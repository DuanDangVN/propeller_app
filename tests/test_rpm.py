"""Tests for NI counter edge-to-RPM conversion and timeout behavior."""

import pytest

from processing.rpm import CounterRpmTracker


def test_counter_edges_are_converted_to_rpm() -> None:
    tracker = CounterRpmTracker(
        pulses_per_revolution=2,
        calculation_window_s=0.1,
        timeout_s=1.5,
    )
    tracker.reset(initial_count=100, now=10.0)

    reading = tracker.update(counter_value=120, now=10.2)

    assert reading.pulse_count == 120
    assert reading.frequency_hz == pytest.approx(100.0)
    assert reading.rpm == pytest.approx(3000.0)
    assert reading.status == "OK"


def test_rpm_holds_between_low_speed_pulses_then_times_out() -> None:
    tracker = CounterRpmTracker(
        pulses_per_revolution=1,
        calculation_window_s=0.1,
        timeout_s=1.5,
    )
    tracker.reset(initial_count=0, now=10.0)
    first = tracker.update(counter_value=1, now=10.5)
    held = tracker.update(counter_value=1, now=11.0)
    timed_out = tracker.update(counter_value=1, now=12.1)

    assert first.rpm == pytest.approx(120.0)
    assert held.rpm == pytest.approx(120.0)
    assert held.status == "OK"
    assert timed_out.rpm == 0.0
    assert timed_out.frequency_hz == 0.0
    assert timed_out.status == "TIMEOUT"


def test_counter_rollover_is_handled() -> None:
    tracker = CounterRpmTracker(
        pulses_per_revolution=1,
        calculation_window_s=0.1,
        timeout_s=1.5,
    )
    tracker.reset(initial_count=(2**32) - 2, now=10.0)

    reading = tracker.update(counter_value=3, now=10.1)

    assert reading.rpm == pytest.approx(3000.0)
    assert reading.status == "OK"


@pytest.mark.parametrize(
    ("keyword", "value"),
    [
        ("pulses_per_revolution", 0),
        ("calculation_window_s", 0.0),
        ("timeout_s", 0.0),
    ],
)
def test_invalid_rpm_settings_are_rejected(keyword: str, value: float) -> None:
    settings = {
        "pulses_per_revolution": 1,
        "calculation_window_s": 0.1,
        "timeout_s": 1.5,
    }
    settings[keyword] = value

    with pytest.raises(ValueError):
        CounterRpmTracker(**settings)
