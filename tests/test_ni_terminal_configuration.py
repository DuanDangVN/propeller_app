import inspect

from nidaqmx.constants import TerminalConfiguration

from main import AnalogCalibrationReader, NIDeviceReader


def test_differential_terminal_configuration_is_available():
    assert TerminalConfiguration.DIFF.name == "DIFF"

    reader_source = inspect.getsource(NIDeviceReader)
    assert "TerminalConfiguration.DIFF" in reader_source
    assert "TerminalConfiguration.DIFFERENTIAL" not in reader_source


def test_calibration_reader_is_analog_only():
    reader_source = inspect.getsource(AnalogCalibrationReader)
    assert "TerminalConfiguration.DIFF" in reader_source
    assert "add_ci_count_edges_chan" not in reader_source
    assert "counter_task" not in reader_source
