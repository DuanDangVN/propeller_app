"""Online statistics for force, torque and RPM."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(slots=True)
class RunningStatistics:
    """Track count, mean, minimum and maximum without storing every sample."""

    count: int = 0
    mean: float = 0.0
    minimum: float = float("inf")
    maximum: float = float("-inf")

    def update(self, values: NDArray[np.float64]) -> None:
        """Merge a NumPy block into the accumulated statistics."""
        data = np.asarray(values, dtype=np.float64)
        finite = data[np.isfinite(data)]
        if finite.size == 0:
            return
        block_count = int(finite.size)
        block_mean = float(np.mean(finite))
        total_count = self.count + block_count
        self.mean += (block_mean - self.mean) * block_count / total_count
        self.count = total_count
        self.minimum = min(self.minimum, float(np.min(finite)))
        self.maximum = max(self.maximum, float(np.max(finite)))

    def reset(self) -> None:
        """Reset all accumulated values."""
        self.count = 0
        self.mean = 0.0
        self.minimum = float("inf")
        self.maximum = float("-inf")

    def as_dict(self) -> dict[str, float | int]:
        """Return values ready for UI display or export."""
        if self.count == 0:
            return {"count": 0, "mean": 0.0, "min": 0.0, "max": 0.0}
        return {
            "count": self.count,
            "mean": self.mean,
            "min": self.minimum,
            "max": self.maximum,
        }
