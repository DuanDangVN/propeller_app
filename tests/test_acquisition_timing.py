from types import SimpleNamespace

import numpy as np
import pytest

from acquisition_worker import AcquisitionWorker
import devices.ni_reader as ni_reader
from devices.ni_reader import read_ni_voltage_snapshot
from processing.rpm import align_rpm_elapsed_time


def test_blocking_hardware_reader_has_no_extra_timer_delay() -> None:
    reader = SimpleNamespace(paces_reads=True)

    assert AcquisitionWorker._timer_interval_for_reader(reader, 100) == 0


def test_nonblocking_simulation_keeps_configured_timer() -> None:
    reader = SimpleNamespace(paces_reads=False)

    assert AcquisitionWorker._timer_interval_for_reader(reader, 100) == 100


def test_rpm_keeps_live_time_when_analog_reader_has_backlog() -> None:
    first_rpm_time, offset = align_rpm_elapsed_time(0.1, 0.1, None)
    delayed_rpm_time, offset = align_rpm_elapsed_time(0.2, 2.2, offset)

    assert first_rpm_time == pytest.approx(0.1)
    assert delayed_rpm_time == pytest.approx(2.2)
    assert offset == pytest.approx(0.0)


def test_calibration_snapshot_uses_finite_analog_task(monkeypatch) -> None:
    calls = {}

    class FakeTask:
        def __init__(self):
            self.ai_channels = SimpleNamespace(
                add_ai_voltage_chan=lambda *args, **kwargs: calls.update(
                    channel_args=args,
                    channel_kwargs=kwargs,
                )
            )
            self.timing = SimpleNamespace(
                cfg_samp_clk_timing=lambda *args, **kwargs: calls.update(
                    timing_args=args,
                    timing_kwargs=kwargs,
                )
            )

        def read(self, **kwargs):
            calls["read_kwargs"] = kwargs
            return [1.0, 1.1, 1.2]

        def close(self):
            calls["closed"] = True

    monkeypatch.setattr(ni_reader, "Task", FakeTask)

    result = read_ni_voltage_snapshot(
        "Dev125",
        "ai0",
        rate=10.0,
        duration_s=0.5,
    )

    assert result == pytest.approx(np.asarray([1.0, 1.1, 1.2]))
    assert calls["channel_args"][0] == "Dev125/ai0"
    assert (
        calls["timing_kwargs"]["sample_mode"]
        == ni_reader.AcquisitionType.FINITE
    )
    assert calls["read_kwargs"]["number_of_samples_per_channel"] == 10
    assert calls["closed"] is True
