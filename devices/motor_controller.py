"""Arduino serial control for the ESC."""

from __future__ import annotations

import serial
import serial.tools.list_ports


class MotorControl:
    """Send validated throttle commands to the Arduino controller."""

    def __init__(self, serial_port="COM6", baud_rate=9600):
        self.arduino = serial.Serial(
            serial_port,
            baud_rate,
            timeout=0.1,
            write_timeout=1,
        )

    def set_power(self, value):
        self.arduino.write(f"{value}\n".encode())

    def start_motor(self, power):
        power = int(power)
        if not 10 <= power <= 95:
            raise ValueError("Motor power must be between 10 and 95 percent.")
        self.arduino.write(f"{power}\n".encode())

    def stop_motor(self):
        self.arduino.write(b"10\n")

    def close(self):
        if self.arduino.is_open:
            self.arduino.close()


def list_com():
    """Return serial port names, descriptions and the preferred port."""
    ports = serial.tools.list_ports.comports()
    com_default = "COM6"
    description_default = f"Arduino Uno ({com_default})"
    port_name = []
    port_description = []
    for port in ports:
        port_value = f"Arduino Uno ({port.device})"
        if port.description == port_value:
            com_default = port.device
            description_default = port_value
    port_name.append(com_default)
    port_description.append(description_default)
    for port in ports:
        port_name.append(port.device)
        port_description.append(port.description)
    return port_name, port_description, com_default
