import inspect

from nidaqmx.constants import TerminalConfiguration

from main import NIDeviceReader


def test_differential_terminal_configuration_is_available():
    assert TerminalConfiguration.DIFF.name == "DIFF"

    reader_source = inspect.getsource(NIDeviceReader)
    assert "TerminalConfiguration.DIFF" in reader_source
    assert "TerminalConfiguration.DIFFERENTIAL" not in reader_source
