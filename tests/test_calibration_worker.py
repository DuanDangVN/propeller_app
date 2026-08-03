"""Tests for finite calibration acquisition without the live Read data mode."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QCoreApplication, QEventLoop, QThread, QTimer

from acquisition_worker import CalibrationWorker


class FakeCalibrationReader:
    """Return deterministic analog blocks through the reader interface."""

    def __init__(self, _device, _rate, samples, **_kwargs):
        self.samples = int(samples)
        self.offset = 0

    def read_data(self):
        values = np.arange(
            self.offset,
            self.offset + self.samples,
            dtype=np.float64,
        )
        self.offset += self.samples
        return values, values + 100.0

    def stop(self):
        pass

    def close(self):
        pass


def test_calibration_worker_collects_exact_requested_sample_count():
    app = QCoreApplication.instance() or QCoreApplication([])
    thread = QThread()
    worker = CalibrationWorker(
        FakeCalibrationReader,
        "FakeDevice",
        sampling_rate_hz=1000.0,
        sample_count=10,
        chunk_size=4,
    )
    worker.moveToThread(thread)

    progress = []
    captured = []
    errors = []
    loop = QEventLoop()
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    thread.started.connect(worker.start)
    worker.progress.connect(lambda current, total: progress.append((current, total)))
    worker.data_ready.connect(
        lambda force, torque: captured.append((force, torque))
    )
    worker.error.connect(errors.append)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(loop.quit)
    thread.finished.connect(thread.deleteLater)

    thread.start()
    timeout.start(3000)
    loop.exec()
    app.processEvents()

    assert not errors
    assert len(captured) == 1
    force, torque = captured[0]
    assert force.size == 10
    assert torque.size == 10
    assert np.array_equal(force, np.arange(10, dtype=np.float64))
    assert np.array_equal(torque, np.arange(10, dtype=np.float64) + 100.0)
    assert progress[0] == (0, 10)
    assert progress[-1] == (10, 10)
