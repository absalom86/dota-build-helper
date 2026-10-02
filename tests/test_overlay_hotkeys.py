import ctypes
from ctypes import wintypes
import json

from dota_helper import windows
from dota_helper.app import HotkeyFilter, MainWindow


def test_native_hotkeys_dispatch_separately(monkeypatch):
    monkeypatch.setattr('dota_helper.app.IS_WINDOWS', True)
    calls = []
    event_filter = HotkeyFilter(lambda: calls.append('toggle'), calls.append, lambda: calls.append('hero'),
                               lambda value: calls.append(('hero', value)))
    for hotkey_id, expected in [(1, 'toggle'), (2, -1), (3, 1), (4, 0), (5, 'hero'),
                               (6, ('hero', -1)), (7, ('hero', 1)), (8, ('hero', 0))]:
        msg = wintypes.MSG()
        msg.message, msg.wParam = 0x0312, hotkey_id
        assert event_filter.nativeEventFilter(None, ctypes.addressof(msg)) == (True, 0)
        assert calls[-1] == expected
    msg.wParam = 999
    assert event_filter.nativeEventFilter(None, ctypes.addressof(msg)) == (False, 0)
    assert len(calls) == 8


def test_partial_registration_conflict_releases_scroll_shortcuts(monkeypatch):
    registered, removed = [], []

    def register(key, hotkey_id, modifiers):
        registered.append((key, hotkey_id, modifiers))
        return hotkey_id != 3

    monkeypatch.setattr(windows, 'register_hotkey', register)
    monkeypatch.setattr(windows, 'unregister_hotkey', removed.append)
    assert not windows.register_scroll_hotkeys()
    assert registered == [(0x21, 2, 0x4003), (0x22, 3, 0x4003)]
    assert removed == [2, 3, 4, 5, 6, 7, 8]  # Leave toggle ID 1 alone.


def test_scroll_preference_visibility_and_conflicts(tmp_path, monkeypatch):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setattr('dota_helper.app.unregister_scroll_hotkeys', lambda: None)
    monkeypatch.setattr('dota_helper.app.register_scroll_hotkeys', lambda: False)
    window = MainWindow(start_services=False)
    try:
        window.timer.stop()
        window.capture_timer.stop()
        calls = []
        monkeypatch.setattr(window.overlay, 'scroll_page', calls.append)
        window.scroll_overlay(1)
        assert calls == []
        window.overlay.show()
        window.scroll_overlay(1)
        assert calls == [1]
        window.scroll_hotkeys.setChecked(False)
        window.scroll_overlay(-1)
        assert calls == [1]
        assert json.loads(window.settings_file.read_text())['overlay_scroll_hotkeys'] is False
        window.services_started = True
        window.scroll_hotkeys.setChecked(True)
        assert not window.scroll_hotkeys_ok
        assert 'unavailable' in window.scroll_hotkey_status.text()
        assert not window.overlay.scroll_shortcuts_available
    finally:
        window.close()
