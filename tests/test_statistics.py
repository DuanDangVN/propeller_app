"""Tests for online measurement statistics."""

import numpy as np
import pytest

from processing.statistics import RunningStatistics


def test_statistics_merge_multiple_blocks() -> None:
    statistics = RunningStatistics()
    statistics.update(np.asarray([1.0, 2.0]))
    statistics.update(np.asarray([3.0, 4.0]))
    values = statistics.as_dict()
    assert values["count"] == 4
    assert values["mean"] == pytest.approx(2.5)
    assert values["min"] == pytest.approx(1.0)
    assert values["max"] == pytest.approx(4.0)


def test_statistics_ignore_non_finite_values() -> None:
    statistics = RunningStatistics()
    statistics.update(np.asarray([np.nan, 2.0, np.inf]))
    assert statistics.as_dict()["mean"] == pytest.approx(2.0)
