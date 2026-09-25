"""Keep writable user data out of a frozen executable's temporary extraction folder."""
import os
from pathlib import Path
import sys


def user_data_dir():
    override = os.environ.get("DOTA_HELPER_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "DotaBuildHelper"
    return Path(__file__).resolve().parent.parent / ".local"
