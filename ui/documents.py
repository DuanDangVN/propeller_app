"""Embedded document and information panels for the desktop application."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


REQUIRED_DOCUMENT_URLS = ("propeller_guided", "dhutech", "email")
WEB_LOAD_TIMEOUT_MS = 15_000


def load_document_urls(path: Path) -> dict[str, str]:
    """Load and validate the HTTPS URLs used by the document tabs."""
    with Path(path).open("r", encoding="utf-8") as file:
        raw_urls = json.load(file)

    urls: dict[str, str] = {}
    for key in REQUIRED_DOCUMENT_URLS:
        value = raw_urls.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing document URL: {key}")
        normalized = value.strip()
        url = QUrl(normalized)
        if not url.isValid() or url.scheme() != "https" or not url.host():
            raise ValueError(f"Invalid HTTPS document URL for {key}")
        urls[key] = normalized
    return urls


class EmbeddedWebPanel(QWidget):
    """Display a web document in-app with reload and browser fallbacks."""

    def __init__(self, title: str, url: str, parent=None) -> None:
        super().__init__(parent)
        self.title = title
        self.url = QUrl(url)
        self.load_timed_out = False

        root_layout = QVBoxLayout(self)
        toolbar_layout = QHBoxLayout()
        self.status_label = QLabel(f"Loading {title}...")
        reload_button = QPushButton("Reload")
        external_button = QPushButton("Open externally")
        toolbar_layout.addWidget(self.status_label, 1)
        toolbar_layout.addWidget(reload_button)
        toolbar_layout.addWidget(external_button)

        self.web_view = QWebEngineView(self)
        self.load_timeout = QTimer(self)
        self.load_timeout.setSingleShot(True)
        self.load_timeout.timeout.connect(self._on_load_timeout)
        reload_button.clicked.connect(self.web_view.reload)
        external_button.clicked.connect(
            lambda: QDesktopServices.openUrl(self.url)
        )
        self.web_view.loadStarted.connect(self._on_load_started)
        self.web_view.loadProgress.connect(self._on_load_progress)
        self.web_view.loadFinished.connect(self._on_load_finished)

        root_layout.addLayout(toolbar_layout)
        root_layout.addWidget(self.web_view, 1)
        self.web_view.setUrl(self.url)

    def _on_load_started(self) -> None:
        self.load_timed_out = False
        self.status_label.setText(f"Loading {self.title}...")
        self.load_timeout.start(WEB_LOAD_TIMEOUT_MS)

    def _on_load_progress(self, progress: int) -> None:
        self.status_label.setText(f"Loading {self.title}: {progress}%")

    def _on_load_finished(self, succeeded: bool) -> None:
        self.load_timeout.stop()
        if self.load_timed_out:
            return
        if succeeded:
            self.status_label.setText(self.title)
        else:
            self.status_label.setText(
                f"Unable to load {self.title}. Use Open externally."
            )

    def _on_load_timeout(self) -> None:
        self.load_timed_out = True
        self.web_view.stop()
        self.status_label.setText(
            f"{self.title} did not respond within 15 seconds. "
            "Check the URL/server or use Open externally."
        )
