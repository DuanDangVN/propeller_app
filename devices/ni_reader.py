"""NI USB-6001 analog and RPM counter access."""

from __future__ import annotations

import logging

import nidaqmx.system
import numpy as np
from nidaqmx import Task
from nidaqmx.constants import AcquisitionType, TerminalConfiguration

from app_runtime import CALIBRATION_CAPTURE_WINDOW_S
from processing.rpm import CounterRpmTracker, DEFAULT_PULSES_PER_REVOLUTION


LOGGER = logging.getLogger(__name__)
FORCE_CHANNEL = "ai0"
TORQUE_CHANNEL = "ai1"
ANALOG_MIN_V = 0.0
ANALOG_MAX_V = 10.0


class NIDeviceReader:
    """Read synchronized force, torque and RPM data from NI hardware."""

    # Fixed-size DAQmx reads block until a complete block is available.
    paces_reads = True

    def __init__(
        self,
        dev_name,
        rate,
        samples,
        force_channel=FORCE_CHANNEL,
        torque_channel=TORQUE_CHANNEL,
        rpm_counter="ctr0",
        rpm_terminal="PFI0",
        pulses_per_revolution=DEFAULT_PULSES_PER_REVOLUTION,
        rpm_calculation_window_s=0.1,
        rpm_timeout_s=1.5,
    ):
        self.rate = float(rate)
        self.samples = int(samples)
        self.task = Task()
        self.counter_task = Task()
        self.rpm_tracker = CounterRpmTracker(
            pulses_per_revolution=int(pulses_per_revolution),
            calculation_window_s=float(rpm_calculation_window_s),
            timeout_s=float(rpm_timeout_s),
        )
        try:
            # Both JSY-S60 voltage outputs share NI AI GND in RSE mode.
            self.task.ai_channels.add_ai_voltage_chan(
                f"{dev_name}/{force_channel}",
                name_to_assign_to_channel="force_voltage",
                terminal_config=TerminalConfiguration.RSE,
                min_val=ANALOG_MIN_V,
                max_val=ANALOG_MAX_V,
            )
            self.task.ai_channels.add_ai_voltage_chan(
                f"{dev_name}/{torque_channel}",
                name_to_assign_to_channel="torque_voltage",
                terminal_config=TerminalConfiguration.RSE,
                min_val=ANALOG_MIN_V,
                max_val=ANALOG_MAX_V,
            )
            input_buffer_samples = max(
                int(self.rate * 5.0),
                self.samples * 20,
            )
            self.task.timing.cfg_samp_clk_timing(
                self.rate,
                sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=input_buffer_samples,
            )

            counter_channel = (
                self.counter_task.ci_channels.add_ci_count_edges_chan(
                    f"{dev_name}/{rpm_counter}",
                    name_to_assign_to_channel="rpm_edges",
                )
            )
            counter_channel.ci_count_edges_term = f"/{dev_name}/{rpm_terminal}"
            self.counter_task.start()
            initial_count = int(self.counter_task.read())
            self.rpm_tracker.reset(initial_count=initial_count)
            self.task.start()
        except Exception:
            self.close()
            raise

    def read_data(self):
        data = self.task.read(number_of_samples_per_channel=self.samples)
        counter_value = int(self.counter_task.read())
        rpm_reading = self.rpm_tracker.update(counter_value)
        return np.array(data[0]), np.array(data[1]), rpm_reading

    def stop(self):
        for task in (self.task, self.counter_task):
            try:
                task.stop()
            except Exception:
                pass

    def close(self):
        for task in (self.task, self.counter_task):
            try:
                task.close()
            except Exception:
                pass


class AnalogCalibrationReader:
    """Read both analog channels without reserving the RPM counter."""

    def __init__(
        self,
        dev_name,
        rate,
        samples,
        force_channel=FORCE_CHANNEL,
        torque_channel=TORQUE_CHANNEL,
        **_reader_kwargs,
    ):
        self.rate = float(rate)
        self.samples = int(samples)
        self.task = Task()
        try:
            self.task.ai_channels.add_ai_voltage_chan(
                f"{dev_name}/{force_channel}",
                name_to_assign_to_channel="calibration_force_voltage",
                terminal_config=TerminalConfiguration.RSE,
                min_val=ANALOG_MIN_V,
                max_val=ANALOG_MAX_V,
            )
            self.task.ai_channels.add_ai_voltage_chan(
                f"{dev_name}/{torque_channel}",
                name_to_assign_to_channel="calibration_torque_voltage",
                terminal_config=TerminalConfiguration.RSE,
                min_val=ANALOG_MIN_V,
                max_val=ANALOG_MAX_V,
            )
            self.task.timing.cfg_samp_clk_timing(
                self.rate,
                sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=max(int(self.rate * 2.0), self.samples * 4),
            )
            self.task.start()
        except Exception:
            self.close()
            raise

    def read_data(self):
        """Read one force/torque block for the calibration worker."""
        data = self.task.read(number_of_samples_per_channel=self.samples)
        return np.asarray(data[0]), np.asarray(data[1])

    def stop(self):
        try:
            self.task.stop()
        except Exception:
            pass

    def close(self):
        try:
            self.task.close()
        except Exception:
            pass


def list_dev():
    """Return visible NI-DAQmx devices without crashing the UI."""
    try:
        system = nidaqmx.system.System.local()
        devices = [device.name for device in system.devices]
        default_dev = devices[0] if devices else ""
        return devices, default_dev
    except Exception:
        LOGGER.exception("Unable to enumerate NI-DAQmx devices")
        return [], ""


def read_ni_voltage_snapshot(
    dev_name,
    channel,
    rate,
    duration_s=CALIBRATION_CAPTURE_WINDOW_S,
):
    """Read one finite analog window without starting main acquisition."""
    rate = float(rate)
    duration_s = float(duration_s)
    sample_count = max(10, int(round(rate * duration_s)))
    task = Task()
    try:
        task.ai_channels.add_ai_voltage_chan(
            f"{dev_name}/{channel}",
            name_to_assign_to_channel="calibration_voltage",
            terminal_config=TerminalConfiguration.RSE,
            min_val=ANALOG_MIN_V,
            max_val=ANALOG_MAX_V,
        )
        task.timing.cfg_samp_clk_timing(
            rate,
            sample_mode=AcquisitionType.FINITE,
            samps_per_chan=sample_count,
        )
        data = task.read(
            number_of_samples_per_channel=sample_count,
            timeout=max(2.0, duration_s + 1.0),
        )
        return np.asarray(data, dtype=np.float64).reshape(-1)
    finally:
        task.close()
