from pathlib import Path
import sys

from dota_helper.paths import user_data_dir


def test_frozen_app_uses_persistent_user_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("DOTA_HELPER_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert user_data_dir() == tmp_path / "DotaBuildHelper"


def test_explicit_data_directory_is_respected(monkeypatch, tmp_path):
    monkeypatch.setenv("DOTA_HELPER_HOME", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert user_data_dir() == tmp_path.resolve()
