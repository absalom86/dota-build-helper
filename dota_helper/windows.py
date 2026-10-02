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


def register_hotkey(key=0x77, hotkey_id=1, modifiers=0x4002):
    return IS_WINDOWS and bool(user32.RegisterHotKey(None, hotkey_id, modifiers, key))


def unregister_hotkey(hotkey_id=1):
    if IS_WINDOWS:
        user32.UnregisterHotKey(None, hotkey_id)


# Ctrl + Alt with no auto-repeat. IDs are separate from the overlay toggle.
SCROLL_HOTKEYS = {2: 0x21, 3: 0x22, 4: 0x24, 5: 0x78}  # Page Up, Page Down, Home, F9
SCROLL_HOTKEYS.update({6: 0x21, 7: 0x22, 8: 0x24})  # Add Shift for hero panel.


def unregister_scroll_hotkeys():
    for hotkey_id in SCROLL_HOTKEYS:
        unregister_hotkey(hotkey_id)


def register_scroll_hotkeys():
    for hotkey_id, key in SCROLL_HOTKEYS.items():
        if not register_hotkey(key, hotkey_id, 0x4007 if hotkey_id >= 6 else 0x4003):
            unregister_scroll_hotkeys()
            return False
    return True
