"""Windows user-bound credential storage. Secrets never enter app settings."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path


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
    encrypted = _crypt(token.encode("utf-8"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encrypted)


def load_token():
    token = os.environ.get("STRATZ_API_TOKEN", "").strip()
    if token:
        return token
    path = credential_path()
    if not path.exists():
        return ""
    return _crypt(path.read_bytes(), decrypt=True).decode("utf-8")
