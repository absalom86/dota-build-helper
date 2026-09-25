# PyInstaller recipe for the Windows 10/11 standalone companion.
from pathlib import Path, PureWindowsPath
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent
a = Analysis(
    [str(root / 'desktop_entry.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / 'dota_helper' / 'data'), 'dota_helper/data'), (str(root / 'README.md'), '.')],
    hiddenimports=collect_submodules('mss'),
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
# The bundled development Python registers other tools' DLL directories even
# with a clean PATH. Poppler's ICU exports versioned symbols, while Qt expects
# Windows ICU's unversioned API. Use the OS ICU/UCRT/API sets, never those tools'
# incompatible DLLs. These system libraries are present on supported Windows.
def system_library(entry):
    name = PureWindowsPath(entry[0]).name.lower()
    return name.startswith(('icu', 'api-ms-win-')) or name == 'ucrtbase.dll'

a.binaries = [entry for entry in a.binaries if not system_library(entry)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name='DotaBuildHelper',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=str(root / 'dota_helper' / 'data' / 'app-icon.ico'),
)
