"""Tests for application runtime directories."""

from app_runtime import APP_DIR, EXPORT_DIR


def test_export_directory_is_beside_application() -> None:
    assert EXPORT_DIR == APP_DIR / "Export data"
    assert EXPORT_DIR.is_dir()
