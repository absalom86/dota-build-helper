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
    from . import guides, invoker, starting_items
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
            result.update(ok=True, frozen=bool(getattr(sys, "frozen", False)), heroes=len(HEROES),
                          demo_routes=3, route_switch=True, draft_ranking=True, capture_module=True,
                          invoker_spells=len(invoker.SPELLS), shop_guide_export=True, overlay_fit=True,
                          quantity_provenance=True, independent_telemetry=True,
                          data_directory=str(LOCAL), window_visible=window.isVisible())
        except Exception as exc:
            result.update(ok=False, error=f"{type(exc).__name__}: {exc}")
        window.close()
        result["settings_saved"] = (LOCAL / "settings.json").exists()
        report.write_text(json.dumps(result, indent=2), encoding="utf-8")
        app.exit(0 if result.get("ok") else 1)

    QTimer.singleShot(100, check)
    return app.exec()
