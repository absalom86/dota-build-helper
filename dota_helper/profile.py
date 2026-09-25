"""Atomic profile files with a last-good backup, independent of app versions."""
import json
import os
from pathlib import Path
import tempfile


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def backup_path(path):
    return Path(str(path) + '.bak')


def load_settings(path):
    path = Path(path)
    for candidate in (path, backup_path(path)):
        try:
            value = json.loads(candidate.read_text(encoding='utf-8'))
            if isinstance(value, dict):
                return value
        except (OSError, ValueError):
            pass
    if path.exists() or backup_path(path).exists():
        raise RuntimeError('Saved settings cannot be read. Existing files were preserved; do not reset the profile.')
    return {}


def save_settings(path, settings):
    path = Path(path)
    previous = load_settings(path)
    if path.exists() or backup_path(path).exists():
        atomic_write(backup_path(path), json.dumps(previous, indent=2).encode('utf-8'))
    atomic_write(path, json.dumps(settings, indent=2).encode('utf-8'))
