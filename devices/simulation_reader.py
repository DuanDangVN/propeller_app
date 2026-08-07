"""Repeatable simulated force, torque and RPM acquisition."""

from __future__ import annotations

import numpy as np

from processing.rpm import DEFAULT_PULSES_PER_REVOLUTION, RpmReading


class SimulationReader:
    """Generate repeatable voltage blocks without NI hardware."""

    paces_reads = False

    def __init__(
        self,
        _dev_name,
        rate,
        samples,
        pulses_per_revolution=DEFAULT_PULSES_PER_REVOLUTION,
        **_reader_kwargs,
    ):
        self.rate = float(rate)
        self.samples = int(samples)
        self.pulses_per_revolution = int(pulses_per_revolution)
        self.sample_index = 0
        self.pulse_count = 0.0
        self.random = np.random.default_rng(20260729)

    def read_data(self):
        time_s = (
            np.arange(self.samples, dtype=np.float64) + self.sample_index
        ) / self.rate
        self.sample_index += self.samples
        force_voltage = (
            0.80
            + 0.06 * np.sin(2 * np.pi * 0.7 * time_s)
            + self.random.normal(0.0, 0.008, self.samples)
        )
        torque_voltage = (
            1.49
            + 0.04 * np.sin(2 * np.pi * 0.7 * time_s + 0.4)
            + self.random.normal(0.0, 0.006, self.samples)
        )
        block_end_s = self.sample_index / self.rate
        rpm = 1800.0 + 450.0 * np.sin(2 * np.pi * 0.12 * block_end_s)
        frequency_hz = rpm * self.pulses_per_revolution / 60.0
        self.pulse_count += frequency_hz * self.samples / self.rate
        rpm_reading = RpmReading(
            pulse_count=int(self.pulse_count),
            frequency_hz=float(frequency_hz),
            rpm=float(rpm),
            status="SIMULATION",
            elapsed_time_s=block_end_s,
        )
        return force_voltage, torque_voltage, rpm_reading

    def stop(self):
        """Match the NI reader interface."""

    def close(self):
        """Match the NI reader interface."""
