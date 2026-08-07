"""Propeller application entrypoint."""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app_runtime import smoke_trace
from ui.main_window import MainWindow


def main() -> int:
    """Create and run the desktop application."""
    smoke_trace("main entered")
    app = QApplication(sys.argv)
    smoke_trace("QApplication created")
    window = MainWindow()
    smoke_trace(f"MainWindow created ppr={window.pulses_per_revolution}")

    if "--smoke-test" in sys.argv:
        window.acquisition_mode = "simulation"

        def finish_smoke_test() -> None:
            window.stop_reading()
            required_columns = {
                "force_filtered_n",
                "torque_filtered_nm",
                "rpm",
            }
            last_row = (
                window.measurement_rows[-1]
                if window.measurement_rows
                else {}
            )
            succeeded = (
                len(window.measurement_rows) > 0
                and window.acquisition_thread is None
                and required_columns.issubset(last_row)
                and float(last_row.get("rpm", 0.0)) > 0.0
            )
            smoke_trace(
                f"smoke finished succeeded={succeeded} "
                f"rows={len(window.measurement_rows)}"
            )
            window.close()
            app.exit(0 if succeeded else 1)

        QTimer.singleShot(0, window.start_reading)
        QTimer.singleShot(700, finish_smoke_test)
        return app.exec()

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
