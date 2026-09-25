"""Windows window metadata and hotkeys only; no game process memory access."""
import ctypes
from ctypes import wintypes
import os

IS_WINDOWS = os.name == "nt"
if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]


def dota_active():
    if not IS_WINDOWS:
        return False
    hwnd = user32.GetForegroundWindow()
    text = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
    user32.GetWindowTextW(hwnd, text, len(text))
    return text.value.strip().lower() == "dota 2"


def register_hotkey(key=0x77):
    return IS_WINDOWS and bool(user32.RegisterHotKey(None, 1, 0x4002, key))  # Ctrl + F8; no repeat


def unregister_hotkey():
    if IS_WINDOWS:
        user32.UnregisterHotKey(None, 1)
