"""Selection and visibility regressions for the Shadow Shaman reference."""
from dota_helper import invoker, kez, shadow_shaman
from dota_helper.app import MainWindow


def test_reference_switching_and_draft_without_fetch(tmp_path, monkeypatch):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setattr('dota_helper.app.dota_active', lambda: False)
    window = MainWindow(start_services=False)
    try:
        window.timer.stop()
        window.capture_timer.stop()
        window.draft.meta_active = False
        refs = {shadow_shaman.HERO_ID: window.overlay.shadow_shaman_tips,
                invoker.HERO_ID: window.overlay.invoker_spells,
                kez.HERO_ID: window.overlay.kez_combos}
        for hero_id in (27, 74, 27, 145, 27, 1):
            window.hero.setCurrentIndex(window.hero.findData(hero_id))
            window.tick()
            assert not window.routes  # A build/provider result is not needed.
            for reference_id, label in refs.items():
                assert label.isHidden() == (reference_id != hero_id)
            assert window.overlay.fit_ok
        window.hero.setCurrentIndex(window.hero.findData(27))
        window.tick()
        label = window.overlay.shadow_shaman_tips
        assert 'Blink → W → R → E' in label.text()
        for name in ('Ether Shock', 'Hex', 'Mass Serpent Ward', 'Shackles'):
            assert name in label.text()
        assert 'LOW HEALTH' in label.text()
        assert 'not live health' in label.toolTip()
        monkeypatch.setattr(window.draft, 'overlay_text', lambda: ('Enemies', 'Suggestions', 'Note'))
        window.tick()
        assert all(label.isHidden() for label in refs.values())
        monkeypatch.setattr(window.draft, 'overlay_text', lambda: None)
        window.tick()
        assert not window.overlay.shadow_shaman_tips.isHidden()
    finally:
        window.close()


def test_confirmed_game_hero_shows_tips_before_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setattr('dota_helper.app.dota_active', lambda: False)
    window = MainWindow(start_services=False)
    try:
        window.timer.stop()
        window.capture_timer.stop()
        requests = []
        monkeypatch.setattr(window, 'fetch', lambda: requests.append(window.hero.currentData()))
        window.on_gsi({'hero': {'id': 27}, 'player': {'steamid': 'offline-fixture'},
                       'map': {'game_state': 'DOTA_GAMERULES_STATE_STRATEGY_TIME', 'clock_time': -60}})
        window.tick()
        assert window.hero.currentData() == 27 and requests == [27]
        assert not window.routes
        assert not window.overlay.shadow_shaman_tips.isHidden()
        assert window.overlay.invoker_spells.isHidden() and window.overlay.kez_combos.isHidden()
    finally:
        window.close()
