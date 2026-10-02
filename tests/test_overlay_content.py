"""Near-term lane hints stay small without changing the full purchase history."""
import pytest

from dota_helper.models import Purchase
from dota_helper.overlay import purchase_summary
from dota_helper.overlay_content import near_term_purchases


@pytest.mark.parametrize('second', [None, -60, 0])
def test_opening_window_keeps_nearby_components_but_not_future_restocks(second):
    purchases = [Purchase('circlet', 0), Purchase('gauntlets', 120),
                 Purchase('flask', 121), Purchase('flask', 450)]
    visible, window = near_term_purchases(purchases, second, 600)
    assert visible == purchases[:2]
    assert window == '00:00–02:00'
    assert len(purchases) == 4


def test_window_advances_keeps_repeat_quantities_and_does_not_change_events():
    purchases = [Purchase('flask', 359), Purchase('flask', 420),
                 Purchase('flask', 450, 2), Purchase('tango', 541)]
    original = [vars(purchase).copy() for purchase in purchases]
    visible, window = near_term_purchases(purchases, 420, 600)
    assert visible == purchases[1:3]
    assert window == '06:00–09:00'
    assert purchase_summary(visible) == '07:00–07:30 Healing Salve ×2'
    assert [vars(purchase) for purchase in purchases] == original


def test_window_respects_existing_exclusive_phase_deadline():
    purchases = [Purchase('circlet', 299), Purchase('gauntlets', 300)]
    visible, window = near_term_purchases(purchases, 299, 300)
    assert visible == purchases[:1]
    assert window == '03:59–05:00'
    assert near_term_purchases(purchases, 0, 0)[0] == []


def test_overlay_changes_temporary_hints_only_and_keeps_full_tooltip(tmp_path, monkeypatch):
    from dota_helper import starting_items
    from dota_helper.app import MainWindow
    from dota_helper.providers import Demo

    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setattr(starting_items, 'user_data_dir', lambda: tmp_path)
    monkeypatch.setattr('dota_helper.app.dota_active', lambda: False)
    window = MainWindow(start_services=False)
    try:
        window.timer.stop()
        window.capture_timer.stop()
        window.draft.meta_active = False
        route = Demo().routes(1, 1, 0)[0][0]
        route.purchases = [Purchase('branches', -60), Purchase('branches', -60, 2),
                           Purchase('circlet', 120), Purchase('flask', 420),
                           Purchase('flask', 450, 2), Purchase('manta', 1200)]
        window.routes = [route]
        window.session.accept_routes([route])
        window.manual_second = 0
        window.tick()
        assert 'Iron Branch ×2' in window.overlay.initial_buy.text()
        assert not window.overlay.initial_buy.isHidden()
        assert 'Circlet' in window.overlay.components.text()
        assert not window.overlay.components.isHidden()
        assert window.overlay.supplies.isHidden()
        assert 'Healing Salve ×2' in window.overlay.supplies.toolTip()
        assert 'Manta Style' in window.overlay.items.text()
        window.manual_second = 420
        window.tick()
        assert window.overlay.initial_buy.isHidden()
        assert window.overlay.components.isHidden()
        assert not window.overlay.supplies.isHidden()
        assert 'SUPPLIES · 06:00–09:00' in window.overlay.supplies.text()
        assert 'Healing Salve ×2' in window.overlay.supplies.text()
        assert 'Manta Style' in window.overlay.items.text()
        assert len(route.purchases) == 6
    finally:
        window.close()
