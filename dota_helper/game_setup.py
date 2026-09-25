"""Local Steam discovery and explicit setup actions; no Steam settings edits."""
import csv
import io
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from .gsi import config_text
from .guides import steam_roots


CONFIG_NAME = 'gamestate_integration_build_helper.cfg'


def _pairs(path):
    try:
        text = Path(path).read_text(encoding='utf-8-sig')
    except (OSError, UnicodeError):
        return []
    return [(key, value.replace('\\\\', '\\').replace('\\"', '"'))
            for key, value in re.findall(r'"([^"\\]+)"\s*"((?:\\.|[^"\\])*)"', text)]


def is_dota_directory(path):
    return (Path(path) / 'game' / 'bin' / 'win64' / 'dota2.exe').is_file()


def dota_directories(roots=None):
    roots = [Path(root) for root in (steam_roots() if roots is None else roots)]
    libraries = list(roots)
    for root in roots:
        for key, value in _pairs(root / 'steamapps' / 'libraryfolders.vdf'):
            if key == 'path' or key.isdecimal():
                if Path(value).is_absolute():
                    libraries.append(Path(value))
    result = []
    for library in libraries:
        manifest = dict(_pairs(library / 'steamapps' / 'appmanifest_570.acf'))
        name = manifest.get('installdir', 'dota 2 beta')
        if name in ('.', '..') or '/' in name or '\\' in name or ':' in name:
            continue
        path = library / 'steamapps' / 'common' / name
        if is_dota_directory(path) and path.resolve() not in result:
            result.append(path.resolve())
    return result


def config_path(root):
    return Path(root) / 'game' / 'dota' / 'cfg' / 'gamestate_integration' / CONFIG_NAME


def config_ready(root, token):
    try:
        return is_dota_directory(root) and config_path(root).read_text(encoding='utf-8') == config_text(token)
    except (OSError, UnicodeError):
        return False


def install_config(root, token):
    root = Path(root)
    if not is_dota_directory(root):
        raise ValueError('Choose the Dota installation folder containing game/bin/win64/dota2.exe.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', token):
        raise ValueError('The local connection token is invalid. Reopen the helper and try again.')
    path = config_path(root)
    if config_ready(root, token):
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        # Keep an exact backup of the helper's previous config; never edit other configs.
        backup = path.with_name(path.name + f'.{time.time_ns()}.bak')
        backup.write_bytes(path.read_bytes())
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                     dir=path.parent, suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(config_text(token))
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def steam_executable(roots=None):
    return next((Path(root) / 'steam.exe' for root in (steam_roots() if roots is None else roots)
                 if (Path(root) / 'steam.exe').is_file()), None)


def dota_running():
    tasklist = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32' / 'tasklist.exe'
    result = subprocess.run([str(tasklist), '/FI', 'IMAGENAME eq dota2.exe', '/FO', 'CSV', '/NH'],
                            capture_output=True, text=True, timeout=5,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError('Could not check whether Dota is running. Close Dota and try again.')
    return any(row and row[0].lower() == 'dota2.exe' for row in csv.reader(io.StringIO(result.stdout)))


def launch_dota(root, token):
    if not config_ready(root, token):
        raise ValueError('Connect Dota first so the connection file is installed.')
    steam = steam_executable()
    if steam is None:
        raise ValueError('Steam was not found. Open Steam and add -gamestateintegration in Dota launch options.')
    if dota_running():
        raise ValueError('Dota is already running. Close it normally, then click Launch Dota again.')
    # Arguments are passed directly, never composed into shell commands.
    return subprocess.Popen([str(steam), '-applaunch', '570', '-gamestateintegration'],
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
