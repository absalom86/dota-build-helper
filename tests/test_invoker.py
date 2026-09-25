import json

from dota_helper.app import MainWindow
from dota_helper import invoker


def test_all_ten_recipes_and_activation_are_present():
    assert dict(invoker.SPELLS) == {
        'Cold Snap': 'QQQ', 'Ghost Walk': 'QQW', 'Ice Wall': 'QQE',
        'EMP': 'WWW', 'Tornado': 'WWQ', 'Alacrity': 'WWE',
        'Sun Strike': 'EEE', 'Forge Spirit': 'EEQ', 'Chaos Meteor': 'EEW', 'Deafening Blast': 'QWE',
    }
    assert 'R (Invoke)' in invoker.reference_html() and 'D / F' in invoker.reference_html()


def test_reference_follows_hero_without_a_lookup_and_hides_in_draft(tmp_path, monkeypatch):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    window = MainWindow(start_services=False)
    window.draft.meta_active = False
    preferred_width = window.overlay.preferred_width
    window.hero.setCurrentIndex(window.hero.findData(74))
    window.tick()
    assert not window.routes
    assert not window.overlay.invoker_spells.isHidden()
    assert all(name in window.overlay.invoker_spells.text() for name, _ in invoker.SPELLS)
    window.save_settings()
    assert json.loads(window.settings_file.read_text())['overlay_w'] == preferred_width
    assert window.overlay.fit_ok
    monkeypatch.setattr(window.draft, 'overlay_text', lambda: ('Enemies', 'Suggestions', 'Note'))
    window.tick()
    assert window.overlay.invoker_spells.isHidden()
    assert not window.overlay.invoker_active
    assert window.overlay.fit_ok
    monkeypatch.setattr(window.draft, 'overlay_text', lambda: None)
    window.tick()
    assert not window.overlay.invoker_spells.isHidden()
    window.hero.setCurrentIndex(window.hero.findData(1))
    window.tick()
    assert window.overlay.invoker_spells.isHidden()
    window.close()
