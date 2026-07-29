"""RPM calculation helpers for an NI edge counter."""

from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass(frozen=True, slots=True)
class RpmReading:
    """One RPM result derived from the cumulative NI counter value."""

    pulse_count: int
    frequency_hz: float
    rpm: float
    status: str = "OK"


class CounterRpmTracker:
    """Convert cumulative edge counts into RPM with low-speed timeout handling."""

    def __init__(
        self,
        pulses_per_revolution: int = 1,
        calculation_window_s: float = 0.1,
        timeout_s: float = 1.5,
        counter_bits: int = 32,
    ) -> None:
        if pulses_per_revolution <= 0:
            raise ValueError("Pulses per revolution must be positive.")
        if calculation_window_s <= 0:
            raise ValueError("RPM calculation window must be positive.")
        if timeout_s <= 0:
            raise ValueError("RPM timeout must be positive.")
        if counter_bits <= 0:
            raise ValueError("Counter bit width must be positive.")

        self.pulses_per_revolution = int(pulses_per_revolution)
        self.calculation_window_s = float(calculation_window_s)
        self.timeout_s = float(timeout_s)
        self._counter_modulus = 1 << int(counter_bits)
        self._last_counter = 0
        self._window_start_time = 0.0
        self._window_pulses = 0
        self._last_pulse_time: float | None = None
        self._frequency_hz = 0.0
        self._rpm = 0.0
        self._initialized = False

    def reset(
        self,
        initial_count: int = 0,
        now: float | None = None,
    ) -> None:
        """Reset calculation state using the counter's current value."""
        current_time = time.monotonic() if now is None else float(now)
        self._last_counter = int(initial_count) % self._counter_modulus
        self._window_start_time = current_time
        self._window_pulses = 0
        self._last_pulse_time = None
        self._frequency_hz = 0.0
        self._rpm = 0.0
        self._initialized = True

    def update(
        self,
        counter_value: int,
        now: float | None = None,
    ) -> RpmReading:
        """Update RPM from a monotonically increasing hardware edge count."""
        current_time = time.monotonic() if now is None else float(now)
        current_count = int(counter_value) % self._counter_modulus
        if not self._initialized:
            self.reset(current_count, current_time)
            return RpmReading(current_count, 0.0, 0.0, "WAITING_FOR_PULSE")

        pulse_delta = (
            current_count - self._last_counter
        ) % self._counter_modulus
        self._last_counter = current_count

        # A real USB-6001 counter cannot advance by half its 32-bit range in one
        # GUI block. Treat such a jump as a device/task reset instead of a burst.
        if pulse_delta > self._counter_modulus // 2:
            self.reset(current_count, current_time)
            return RpmReading(current_count, 0.0, 0.0, "COUNTER_RESET")

        if pulse_delta:
            self._window_pulses += pulse_delta
            self._last_pulse_time = current_time

        elapsed_window_s = current_time - self._window_start_time
        if (
            self._window_pulses > 0
            and elapsed_window_s + 1e-12 >= self.calculation_window_s
        ):
            self._frequency_hz = self._window_pulses / elapsed_window_s
            self._rpm = (
                self._frequency_hz
                * 60.0
                / self.pulses_per_revolution
            )
            self._window_pulses = 0
            self._window_start_time = current_time

        if self._last_pulse_time is None:
            status = "WAITING_FOR_PULSE"
            self._frequency_hz = 0.0
            self._rpm = 0.0
        elif current_time - self._last_pulse_time > self.timeout_s:
            status = "TIMEOUT"
            self._frequency_hz = 0.0
            self._rpm = 0.0
            self._window_pulses = 0
            self._window_start_time = current_time
        else:
            status = "OK"

        return RpmReading(
            pulse_count=current_count,
            frequency_hz=self._frequency_hz,
            rpm=self._rpm,
            status=status,
        )
