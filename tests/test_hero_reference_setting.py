import json

import pytest

from dota_helper.app import MainWindow


@pytest.mark.parametrize('hero_id,card', [(74, 'invoker_spells'), (145, 'kez_combos'),
                                         (27, 'shadow_shaman_tips')])
def test_hide_reference_is_immediate_persistent_and_keeps_build(tmp_path, monkeypatch, hero_id, card):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setattr('dota_helper.app.dota_active', lambda: False)
    window = MainWindow(start_services=False)
    try:
        window.timer.stop()
        window.capture_timer.stop()
        window.draft.meta_active = False
        window.hero.setCurrentIndex(window.hero.findData(hero_id))
        window.tick()
        assert window.hero_references.isChecked()
        assert not getattr(window.overlay, card).isHidden()
        build_text = window.overlay.items.text()
        skill_text = window.overlay.skill.text()
        window.hero_references.setChecked(False)
        assert all(label.isHidden() for label in window.overlay.references)
        assert window.overlay.items.text() == build_text and not window.overlay.items.isHidden()
        assert window.overlay.skill.text() == skill_text and not window.overlay.skill.isHidden()
        assert json.loads(window.settings_file.read_text())['hero_references'] is False
        for other in (74, 145, 27):
            window.hero.setCurrentIndex(window.hero.findData(other))
            window.tick()
            assert all(label.isHidden() for label in window.overlay.references)
        window.hero_references.setChecked(True)
        assert not window.overlay.shadow_shaman_tips.isHidden()
        window.hero_references.setChecked(False)
    finally:
        window.close()
    reopened = MainWindow(start_services=False)
    try:
        reopened.draft.meta_active = False
        reopened.tick()
        assert not reopened.hero_references.isChecked()
        assert all(label.isHidden() for label in reopened.overlay.references)
    finally:
        reopened.close()
