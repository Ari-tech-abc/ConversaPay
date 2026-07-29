from pathlib import Path

from backend.config import settings
from backend.routers.frontend import FALLBACK_HTML, _html_response, _safe_html_path


def test_delivery_paths_are_absolute_and_inside_repo():
    assert settings.base_dir.is_absolute()
    assert settings.frontend_dir.parent == settings.base_dir
    assert settings.html_dir.parent == settings.frontend_dir
    assert settings.images_dir.parent == settings.frontend_dir


def test_missing_html_returns_protected_404(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "html_dir", tmp_path)
    response = _html_response("missing.html")
    assert response.status_code == 404
    assert "Talk2Pay" in response.body.decode()


def test_traversal_is_rejected():
    try:
        _safe_html_path("../secrets.html")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("path traversal was not rejected")


def test_fallback_is_nonempty():
    assert FALLBACK_HTML.startswith("<!doctype html>")
    assert "Talk2Pay" in FALLBACK_HTML


def test_main_contains_no_delivery_paths():
    source = Path("main.py").read_text()
    assert "StaticFiles" not in source
    assert "FileResponse" not in source
    assert "frontend_router" in source
