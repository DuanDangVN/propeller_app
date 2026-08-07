import inspect

from nidaqmx.constants import TerminalConfiguration

from devices.ni_reader import AnalogCalibrationReader, NIDeviceReader


def test_rse_terminal_configuration_is_used():
    assert TerminalConfiguration.RSE.name == "RSE"

    reader_source = inspect.getsource(NIDeviceReader)
    assert "TerminalConfiguration.RSE" in reader_source
    assert "TerminalConfiguration.DIFF" not in reader_source
    assert "TerminalConfiguration.DIFFERENTIAL" not in reader_source


def test_calibration_reader_is_analog_only():
    reader_source = inspect.getsource(AnalogCalibrationReader)
    assert "TerminalConfiguration.RSE" in reader_source
    assert "add_ci_count_edges_chan" not in reader_source
    assert "counter_task" not in reader_source
