"""Fail a release before building if its tag and embedded versions disagree."""
import os
from pathlib import Path
import re
import runpy
import tomllib

root = Path(__file__).resolve().parents[1]
version = runpy.run_path(str(root / 'dota_helper/version.py'))['VERSION']
assert re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', version), 'Invalid version'
assert os.environ.get('RELEASE_TAG', f'v{version}') == f'v{version}', 'Tag must match the application version'
assert tomllib.loads((root / 'pyproject.toml').read_text())['project']['version'] == version
assert f'#define AppVersion "{version}"' in (root / 'packaging/installer.iss').read_text()
assert f"$Version = '{version}'" in (root / 'build-installer.ps1').read_text()
print(f'Release versions agree: v{version}')
