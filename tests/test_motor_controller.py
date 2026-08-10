"""Tests for Arduino serial-port selection."""

import inspect

import devices.motor_controller as motor_controller


def test_com10_is_the_fallback_arduino_port(monkeypatch) -> None:
    monkeypatch.setattr(
        motor_controller.serial.tools.list_ports,
        "comports",
        lambda: [],
    )

    port_names, port_descriptions, default_port = (
        motor_controller.list_com()
    )

    assert default_port == "COM10"
    assert port_names == ["COM10"]
    assert port_descriptions == ["Arduino Uno (COM10)"]
    assert (
        inspect.signature(motor_controller.MotorControl)
        .parameters["serial_port"]
        .default
        == "COM10"
    )
