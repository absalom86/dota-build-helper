"""Windows user-bound credential storage. Secrets never enter app settings."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
from .profile import atomic_write, backup_path


UNREADABLE_KEY = ('Your saved STRATZ key is still present, but this Windows account cannot read it. '
                  'Close the helper and open it normally under the Windows account that saved the key. '
                  'The existing key has not been removed or replaced.')


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(value, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Encrypted credential storage requires Windows.")
    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise RuntimeError("Windows could not access the encrypted credential.")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def credential_path():
    from .paths import user_data_dir
    return user_data_dir() / "stratz-key.bin"


def save_token(token, path=None):
    token = token.strip()
    if not token or len(token) > 8192 or any(c.isspace() for c in token):
        raise ValueError("Enter a valid STRATZ token.")
    path = Path(path) if path else credential_path()
    previous = _read_saved(path)
    encrypted = _crypt(token.encode("utf-8"))
    if _crypt(encrypted, decrypt=True).decode('utf-8') != token:
        raise RuntimeError('Windows could not verify the saved key. The previous key is unchanged.')
    if previous is not None:
        atomic_write(backup_path(path), previous[0])
    atomic_write(path, encrypted)


def _read_saved(path):
    for candidate in (path, backup_path(path)):
        try:
            encrypted = candidate.read_bytes()
            token = _crypt(encrypted, decrypt=True).decode('utf-8')
            if token:
                return encrypted, token
        except (OSError, RuntimeError, UnicodeError):
            pass
    if path.exists() or backup_path(path).exists():
        raise RuntimeError(UNREADABLE_KEY)
    return None


def load_token():
    token = os.environ.get("STRATZ_API_TOKEN", "").strip()
    if token:
        return token
    path = credential_path()
    saved = _read_saved(path)
    return saved[1] if saved is not None else ''
