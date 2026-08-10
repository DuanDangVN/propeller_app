"""Tests for document URL configuration."""

import json
from pathlib import Path

import pytest

from ui.documents import load_document_urls


PROJECT_DIR = Path(__file__).resolve().parents[1]


def test_bundled_document_urls_match_the_configured_services() -> None:
    urls = load_document_urls(PROJECT_DIR / "public" / "documents_url.json")

    assert urls["propeller_guided"] == (
        "https://drive.google.com/file/d/"
        "10sMfy1HdHJO5ICNKFKgEJQFlsLxoQnFH/preview"
    )
    assert urls["dhutech"] == "https://dhutech.com/"
    assert urls["email"].startswith("https://accounts.google.com/")


def test_document_urls_are_loaded_from_https_config(tmp_path) -> None:
    path = tmp_path / "documents_url.json"
    expected = {
        "propeller_guided": "https://drive.google.com/file/example/preview",
        "dhutech": "https://dhutech.com/",
        "email": "https://accounts.google.com/signin",
    }
    path.write_text(json.dumps(expected), encoding="utf-8")

    assert load_document_urls(path) == expected


def test_document_urls_reject_insecure_or_missing_values(tmp_path) -> None:
    path = tmp_path / "documents_url.json"
    path.write_text(
        json.dumps(
            {
                "propeller_guided": "http://example.com/guide",
                "dhutech": "https://dhutech.com/",
                "email": "https://accounts.google.com/signin",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid HTTPS"):
        load_document_urls(path)
