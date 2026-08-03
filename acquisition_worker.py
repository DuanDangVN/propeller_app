"""Background NI acquisition worker for the Qt application."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot


class AcquisitionWorker(QObject):
    """Read NI blocks outside the GUI thread and emit NumPy arrays."""

    block_ready = Signal(object, object, object)
    error = Signal(str)
    finished = Signal()

    def __init__(
        self,
        reader_factory: Callable[..., Any],
        device_name: str,
        sampling_rate_hz: float,
        block_size: int,
        update_interval_ms: int,
        reader_kwargs: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._reader_factory = reader_factory
        self._device_name = device_name
        self._sampling_rate_hz = sampling_rate_hz
        self._block_size = block_size
        self._update_interval_ms = update_interval_ms
        self._reader_kwargs = dict(reader_kwargs or {})
        self._reader: Any | None = None
        self._timer: QTimer | None = None
        self._stopping = False

    @Slot()
    def start(self) -> None:
        """Create the NI task in this thread and start periodic block reads."""
        try:
            self._reader = self._reader_factory(
                self._device_name,
                self._sampling_rate_hz,
                self._block_size,
                **self._reader_kwargs,
            )
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.read_once)
            self._timer.start(self._update_interval_ms)
            self.read_once()
        except Exception as exc:
            self.error.emit(str(exc))
            self.stop()

    @Slot()
    def read_once(self) -> None:
        """Read and emit one synchronized force/torque/RPM block."""
        if self._stopping or self._reader is None:
            return
        try:
            force_voltage, torque_voltage, rpm_reading = (
                self._reader.read_data()
            )
            self.block_ready.emit(
                force_voltage,
                torque_voltage,
                rpm_reading,
            )
        except Exception as exc:
            self.error.emit(str(exc))
            self.stop()

    @Slot()
    def stop(self) -> None:
        """Stop the timer and release the NI task."""
        if self._stopping:
            return
        self._stopping = True
        if self._timer is not None:
            self._timer.stop()
        if self._reader is not None:
            try:
                self._reader.stop()
            except Exception:
                pass
            try:
                self._reader.close()
            except Exception:
                pass
            self._reader = None
        self.finished.emit()
        QThread.currentThread().quit()


class CalibrationWorker(QObject):
    """Collect one finite analog sample set outside the GUI thread."""

    progress = Signal(int, int)
    data_ready = Signal(object, object)
    error = Signal(str)
    finished = Signal()

    def __init__(
        self,
        reader_factory: Callable[..., Any],
        device_name: str,
        sampling_rate_hz: float,
        sample_count: int,
        chunk_size: int,
        reader_kwargs: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._reader_factory = reader_factory
        self._device_name = device_name
        self._sampling_rate_hz = float(sampling_rate_hz)
        self._sample_count = max(1, int(sample_count))
        self._chunk_size = max(1, min(int(chunk_size), self._sample_count))
        self._reader_kwargs = dict(reader_kwargs or {})
        self._reader: Any | None = None
        self._force_blocks: list[np.ndarray] = []
        self._torque_blocks: list[np.ndarray] = []
        self._collected = 0
        self._stopping = False

    @Slot()
    def start(self) -> None:
        """Create an analog-only reader and begin finite block collection."""
        try:
            self._reader = self._reader_factory(
                self._device_name,
                self._sampling_rate_hz,
                self._chunk_size,
                **self._reader_kwargs,
            )
            self.progress.emit(0, self._sample_count)
            QTimer.singleShot(0, self.read_once)
        except Exception as exc:
            self.error.emit(str(exc))
            self.stop()

    @Slot()
    def read_once(self) -> None:
        """Read the next chunk and emit the completed finite sample set."""
        if self._stopping or self._reader is None:
            return
        try:
            result = self._reader.read_data()
            force_voltage = np.asarray(result[0], dtype=np.float64).reshape(-1)
            torque_voltage = np.asarray(result[1], dtype=np.float64).reshape(-1)
            available = min(force_voltage.size, torque_voltage.size)
            if available <= 0:
                raise RuntimeError("The calibration read returned no samples.")

            take = min(available, self._sample_count - self._collected)
            self._force_blocks.append(force_voltage[:take])
            self._torque_blocks.append(torque_voltage[:take])
            self._collected += take
            self.progress.emit(self._collected, self._sample_count)

            if self._collected >= self._sample_count:
                self.data_ready.emit(
                    np.concatenate(self._force_blocks),
                    np.concatenate(self._torque_blocks),
                )
                self.stop()
                return
            QTimer.singleShot(0, self.read_once)
        except Exception as exc:
            self.error.emit(str(exc))
            self.stop()

    @Slot()
    def stop(self) -> None:
        """Release the temporary reader and end the worker thread."""
        if self._stopping:
            return
        self._stopping = True
        if self._reader is not None:
            try:
                self._reader.stop()
            except Exception:
                pass
            try:
                self._reader.close()
            except Exception:
                pass
            self._reader = None
        self.finished.emit()
        QThread.currentThread().quit()
