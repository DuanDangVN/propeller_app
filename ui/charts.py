"""Chart styling helpers."""

from __future__ import annotations

import pyqtgraph as pg


def configure_chart(chart, title, label_left, label_bottom):
    """Apply the shared dark chart style."""
    chart.setTitle(title)
    chart.setLabel("left", label_left)
    chart.setLabel("bottom", label_bottom)
    chart.setBackground("black")
    chart.getAxis("left").setPen(pg.mkPen(color="white", width=2))
    chart.getAxis("bottom").setPen(pg.mkPen(color="white", width=2))
    chart.getAxis("left").setTextPen(pg.mkPen(color="white"))
    chart.getAxis("bottom").setTextPen(pg.mkPen(color="white"))
    chart.showGrid(x=False, y=True, alpha=0.3)
