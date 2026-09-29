"""Smoke test the actual frozen UI and bundled assets without Dota or network."""
import json
from pathlib import Path
import sys
import time


def run(report_path):
    from PySide6.QtCore import QRect, QTimer, Qt
    from PySide6.QtWidgets import QApplication
    from .app import MainWindow
    from .catalog import HEROES, ITEMS, ABILITIES
    from .detection import capture
    from .draft import rank_picks
    from .providers import LOCAL
    from . import guides, invoker, kez, shadow_shaman, starting_items
    from .credentials import load_token
    import mss

    report = Path(report_path).resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    window = MainWindow(demo=True, start_services=False)
    window.show()
    deadline = time.monotonic() + 15
    result = {}

    def check():
        if window.fetching and time.monotonic() < deadline:
            QTimer.singleShot(100, check)
            return
        try:
            assert len(HEROES) > 100 and ITEMS and ABILITIES
            assert len(window.routes) == 3, "Demo routes did not load"
            assert window.match_table.columnCount() == 6
            assert window.match_table.horizontalHeaderItem(0).text() == 'Avg. MMR'
            assert window.match_table.horizontalHeaderItem(1).text() == 'Avg. rank'
            window.purchases.item(6, 0).setCheckState(Qt.CheckState.Checked)
            window.route_choice.setCurrentIndex(1)
            assert ("bfury", 1) in window.session.completed
            assert window.session.selected == "demo:1"
            assert rank_picks([2], {2: [{"hero_id": 5, "games_played": 100, "wins": 30}]})
            assert window.draft is not None
            window.grab().save(str(report.with_suffix(".png")))
            route = window.current_route()
            exported = guides.write_guide(route, LOCAL / 'guides' / guides.filename(route))
            assert 'item_black_king_bar' in exported.read_text(encoding='utf-8')
            assert all(value['provenance'] == 'recorded' for value in starting_items.details(route))
            window.hero.setCurrentIndex(window.hero.findData(invoker.HERO_ID))
            window.tick()
            assert not window.overlay.invoker_spells.isHidden()
            assert all(name in window.overlay.invoker_spells.text() for name, _ in invoker.SPELLS)
            window.overlay.move(990, 160)
            window.overlay.fit_content(QRect(0, 0, 1280, 720))
            assert window.overlay.fit_ok
            assert window.overlay.invoker_spells.geometry().bottom() < window.overlay.height()
            window.session.ingest({'hero': {'id': invoker.HERO_ID}, 'player': {'steamid': 'offline-self-test'},
                'map': {'game_state': 'DOTA_GAMERULES_STATE_GAME_IN_PROGRESS', 'clock_time': 120},
                'items': {'slot0': {'name': 'item_tango', 'charges': 2}}})
            assert window.session.inventory['tango'] == 1 and window.session.inventory_charges['tango'] == 2
            assert window.session.field_status('inventory') == 'fresh' and window.session.field_status('skills') == 'missing'
            window.hero.setCurrentIndex(window.hero.findData(kez.HERO_ID))
            window.tick()
            window.overlay.fit_content(QRect(0, 0, 1280, 720))
            assert window.overlay.fit_ok and not window.overlay.kez_combos.isHidden()
            assert window.overlay.invoker_spells.isHidden()
            assert all(combo.keys in window.overlay.kez_combos.text()
                       for _, combos in kez.STAGES for combo in combos)
            window.overlay.grab().save(str(report.with_name(f'{report.stem}-kez.png')))
            window.hero.setCurrentIndex(window.hero.findData(shadow_shaman.HERO_ID))
            window.tick()
            window.overlay.fit_content(QRect(0, 0, 1280, 720))
            assert window.overlay.fit_ok and not window.overlay.shadow_shaman_tips.isHidden()
            assert window.overlay.invoker_spells.isHidden() and window.overlay.kez_combos.isHidden()
            assert 'Blink → W → R → E' in window.overlay.shadow_shaman_tips.text()
            assert 'Shackles' in window.overlay.shadow_shaman_tips.text()
            window.overlay.grab().save(str(report.with_name(f'{report.stem}-shadow-shaman.png')))
            from .setup_ui import SetupDialog
            from . import game_setup
            # Only a disposable fixture is written; never configure or launch the real game.
            setup_root = LOCAL / 'setup-fixture'
            fixture_exe = setup_root / 'game' / 'bin' / 'win64' / 'dota2.exe'
            fixture_exe.parent.mkdir(parents=True, exist_ok=True)
            fixture_exe.write_bytes(b'offline setup fixture; not executable')
            discover = game_setup.dota_directories
            try:
                game_setup.dota_directories = lambda: [setup_root]
                window.settings.pop('dota_directory', None)
                setup = SetupDialog(window)
                setup.connect_game()
                assert game_setup.config_ready(setup_root, window.settings['gsi_token'])
                assert not setup.launch_button.isEnabled()  # no live receiver in offline test
                setup.close()
            finally:
                game_setup.dota_directories = discover
            # An isolated verification profile can include real saved lookups.
            # Check their frozen-table path offline without inventing ratings or
            # fetching data during the executable smoke test.
            from .history import decode
            from .ratings import numeric_mmr
            saved_mmr = []
            for entry in list(window.history.entries):
                expected = {r.match_ids[0]: numeric_mmr(r.average_mmr) for r in decode(entry)
                            if r.match_ids and numeric_mmr(r.average_mmr) and not r.tournament}
                if not expected:
                    continue
                window.source.setCurrentIndex(entry['source'])
                window.hero.setCurrentIndex(window.hero.findData(entry['hero']))
                window.role.setCurrentIndex(window.role.findData(entry['role']))
                window.show_saved_search(entry)
                for row, loaded in enumerate(window.routes):
                    mid = loaded.match_ids[0] if loaded.match_ids else None
                    if mid not in expected:
                        continue
                    assert window.match_table.item(row, 0).text() == f'{expected[mid]:,}'
                    window.route_choice.setCurrentIndex(row)
                    window.select_route()
                    assert window.current_route().match_ids[0] == mid
                    saved_mmr.append(dict(match_id=mid, average_mmr=expected[mid], selectable=True))
                window.grab().save(str(report.with_name(f'{report.stem}-mmr-{entry["hero"]}-{entry["role"]}.png')))
            result.update(ok=True, frozen=bool(getattr(sys, "frozen", False)), heroes=len(HEROES),
                          demo_routes=3, route_switch=True, draft_ranking=True, capture_module=True,
                          invoker_spells=len(invoker.SPELLS), kez_combos=sum(len(c) for _, c in kez.STAGES),
                          shadow_shaman_reference=True,
                          shop_guide_export=True, overlay_fit=True,
                          quantity_provenance=True, independent_telemetry=True, quick_setup=True, match_rating_columns=True,
                          saved_mmr_routes_checked=saved_mmr,
                          credential_available=bool(load_token()),
                          data_directory=str(LOCAL), window_visible=window.isVisible())
        except Exception as exc:
            result.update(ok=False, error=f"{type(exc).__name__}: {exc}")
        window.close()
        result["settings_saved"] = (LOCAL / "settings.json").exists()
        report.write_text(json.dumps(result, indent=2), encoding="utf-8")
        app.exit(0 if result.get("ok") else 1)

    QTimer.singleShot(100, check)
    return app.exec()
