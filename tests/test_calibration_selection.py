"""Tests for clearing temporary calibration data when changing sensors."""

from types import SimpleNamespace
from unittest.mock import Mock

from processing.calibration import CalibrationCoefficients
from ui.main_window import MainWindow


def _selection_state(parameter: str) -> SimpleNamespace:
    state = SimpleNamespace(
        parameter_selected=parameter,
        clear_count=0,
        display_update_count=0,
    )
    state.clear_all_value = lambda: setattr(
        state,
        "clear_count",
        state.clear_count + 1,
    )
    state._update_calibration_voltage_display = lambda: setattr(
        state,
        "display_update_count",
        state.display_update_count + 1,
    )
    return state


def test_switching_from_thrust_to_torque_clears_temporary_data() -> None:
    state = _selection_state("Thrust")

    MainWindow.handle_parameter_selection(state, "Torque")

    assert state.parameter_selected == "Torque"
    assert state.clear_count == 1
    assert state.display_update_count == 1


def test_initial_selection_does_not_trigger_unnecessary_clear() -> None:
    state = _selection_state("None")

    MainWindow.handle_parameter_selection(state, "Thrust")

    assert state.parameter_selected == "Thrust"
    assert state.clear_count == 0
    assert state.display_update_count == 1


def test_clear_removes_points_and_stale_linear_fit() -> None:
    state = SimpleNamespace(
        mass_cablibration=[0.0, 9.80665],
        vol_cablibration=[0.2, 0.4],
        slope=49.03325,
        intercept=-9.80665,
        get_voltage_click_count=2,
        get_vol=Mock(),
        plot_widget=Mock(),
        show_storage=Mock(),
        show_slope=Mock(),
    )

    MainWindow.clear_all_value(state)

    assert state.mass_cablibration == []
    assert state.vol_cablibration == []
    assert not hasattr(state, "slope")
    assert not hasattr(state, "intercept")
    assert state.get_voltage_click_count == 0


def test_applied_calibration_summary_shows_zeroed_and_unzeroed_formulas() -> None:
    state = SimpleNamespace(
        force_calibration=CalibrationCoefficients(10.0, -2.0, 0.2),
        torque_calibration=CalibrationCoefficients(-3.0, 1.5),
        _format_applied_calibration=MainWindow._format_applied_calibration,
    )

    summary = MainWindow._applied_calibration_text(state)

    assert "Thrust (N) = 10 × (V - 0.2)" in summary
    assert "Torque (N.m) = -3 × V +1.5" in summary
    assert "Zero: 0.2 V" in summary
    assert "Zero: Not set" in summary
