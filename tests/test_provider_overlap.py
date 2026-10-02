"""A game found by two providers stays one selectable game without losing a choice."""
from dataclasses import asdict, replace

import pytest

from dota_helper.app import MainWindow
from dota_helper.catalog import PATCHES
from dota_helper.history import SearchHistory, decode
from dota_helper.models import Purchase, Route
from dota_helper.ranking import game_identity, ranked


def game(mid=9017541452, source='OpenDota', **overrides):
    slot = 3 if source == 'OpenDota' else 0
    values = dict(
        id=f'{source.lower()}:{mid}:{slot}', hero_id=1, role=1, lane=1,
        patch=PATCHES[-1]['id'], patch_label=PATCHES[-1]['name'],
        title=f'{source} game {mid}', purchases=[Purchase('tango', -30), Purchase('power_treads', 300)],
        skills=['antimage_mana_break'], match_ids=[mid], start_time=1_790_000_000,
        evidence='Match bracket Immortal', player='', source=source, match_rank=80,
        player_slot=slot if source == 'OpenDota' else None,
    )
    values.update(overrides)
    return Route(**values)


@pytest.fixture
def window(tmp_path, monkeypatch, qt_application):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    monkeypatch.setenv('DOTA_HELPER_HOME', str(tmp_path))
    view = MainWindow(start_services=False)
    view.timer.stop()
    view.capture_timer.stop()
    view.live_ratings_timer.stop()
    jobs = []
    view.launch_worker = lambda *args, **kwargs: jobs.append((args, kwargs))
    yield view, jobs
    view.close()
    qt_application.processEvents()


def test_provider_slot_disagreement_deduplicates_by_exact_game_and_prefers_ranking_evidence():
    opendota = game(average_mmr=9000)
    stratz = game(source='STRATZ')
    assert opendota.id != stratz.id and opendota.player_slot != stratz.player_slot
    assert game_identity(opendota) == game_identity(stratz)
    assert ranked([opendota, stratz]) == [opendota]
    selected, = ranked([opendota, stratz], preferred_id=stratz.id)
    assert selected.id == stratz.id and selected.source == stratz.source
    assert selected.purchases == stratz.purchases and selected.skills == stratz.skills
    assert selected.average_mmr == 9000
    assert selected.average_mmr_source == 'OpenDota supplied match average MMR'
    assert opendota.id.startswith('opendota:') and stratz.id.startswith('stratz:')


def test_equal_provider_evidence_prefers_latest_arrival_after_same_id_refresh():
    opendota, stratz = game(), game(source='STRATZ')
    assert ranked([opendota, stratz]) == [stratz]
    assert ranked([stratz, opendota]) == [opendota]
    refreshed = replace(opendota, title='Refreshed data', purchases=opendota.purchases + [Purchase('bfury', 840)])
    assert ranked([opendota, stratz, refreshed]) == [refreshed]
    assert ranked([opendota, stratz, refreshed], preferred_id=opendota.id) == [refreshed]


@pytest.mark.parametrize('changes', [
    {'demo': True}, {'match_ids': []}, {'match_ids': [True]}, {'match_ids': [0]},
    {'match_ids': ['invalid']}, {'match_ids': [9017541452, 9017541453]},
])
def test_demo_aggregated_and_invalid_game_id_routes_keep_their_separate_ids(changes):
    opendota, stratz = game(**changes), game(source='STRATZ', **changes)
    assert len(ranked([opendota, stratz])) == 2


def test_same_match_different_hero_or_position_is_not_merged():
    original = game()
    different_hero = game(source='STRATZ', hero_id=2)
    different_role = game(source='STRATZ', id='stratz:other-position', role=4)
    assert len(ranked([original, different_hero, different_role])) == 3
    numeric_string = game(source='STRATZ', match_ids=['9017541452'])
    assert len(ranked([original, numeric_string])) == 1


def test_saved_provider_overlap_keeps_explicit_source_and_more_than_ten_games(tmp_path):
    selected = game()
    alternative = game(source='STRATZ', average_mmr=10000)
    others = [game(mid) for mid in range(100, 111)]
    raw_entry = dict(hero=1, role=1, selected=selected.id, selected_explicit=True,
                     routes=[asdict(route) for route in [selected, alternative] + others])
    assert len(decode(raw_entry)) == 12
    assert selected.id in {route.id for route in decode(raw_entry)}
    assert alternative.id not in {route.id for route in decode(raw_entry)}
    history = SearchHistory(tmp_path)
    history.save(1, 1, 0, [selected] + others, selected.id, 'Initial results')
    history.save(1, 1, 0, [alternative], selected.id, 'Refreshed results')
    saved = SearchHistory(tmp_path).find(1, 1, 0)
    restored = decode(saved)
    assert saved['selected'] == selected.id and saved['selected_explicit']
    assert len(restored) == 12
    assert selected.id in {route.id for route in restored}
    assert alternative.id not in {route.id for route in restored}


def test_live_provider_overlap_preserves_manual_selection_updates_and_reload(window, tmp_path):
    view, jobs = window
    selected = game()
    alternative = game(source='STRATZ', average_mmr=10000)
    others = [game(mid, average_mmr=8000) for mid in range(100, 111)]
    view.fetch(force=True)
    args, kwargs = jobs[-1]
    partial, finish = kwargs['partial'], args[1]
    partial(([selected] + others, 'OpenDota results'))
    view.route_choice.setCurrentIndex(view.route_choice.findData(selected.id))
    assert view.session.explicit_choice
    view.session.completed.add(('power_treads', 1))
    view.session.learned['antimage_mana_break'] = 1
    partial(([alternative], 'STRATZ results'))
    assert view.current_route().id == selected.id
    assert len(view.routes) == 12
    refreshed = replace(selected, title='Refreshed selected source')
    partial(([refreshed], 'Updated purchases'))
    finish(([alternative], 'Lookup complete'))
    assert view.current_route().id == refreshed.id
    assert view.current_route().title == refreshed.title
    assert view.current_route().purchases == refreshed.purchases
    assert view.current_route().average_mmr == 10000
    assert view.match_table.rowCount() == view.route_choice.count() == 12
    assert ('power_treads', 1) in view.session.completed
    assert view.session.learned['antimage_mana_break'] == 1

    saved = SearchHistory(tmp_path).find(1, 1, 0)
    assert len(decode(saved)) == 12
    # Restore an explicit stored choice even if an automatic alternative is already loaded.
    view.routes = [alternative]
    view.session.choose(alternative.id, explicit=False)
    view.show_saved_search(saved)
    assert view.current_route().id == selected.id
    assert view.current_route().title == refreshed.title
    assert view.session.explicit_choice
    assert len(view.routes) == 12


def test_manual_import_can_replace_duplicate_provider_without_evicting_other_games(window, tmp_path):
    view, jobs = window
    selected = game(average_mmr=11000)
    others = [game(mid) for mid in range(100, 111)]
    view.routes = [selected] + others
    view.session.choose(selected.id)
    view.render_routes()
    view.history.save(1, 1, 0, view.routes, selected.id, 'Existing results')
    imported = game(source='STRATZ')
    view.match_input.setText(str(imported.match_ids[0]))
    view.import_match()
    jobs[-1][0][1](imported)
    assert view.current_route().id == imported.id
    assert len(view.routes) == view.match_table.rowCount() == 12
    assert selected.id not in {route.id for route in view.routes}
    saved = SearchHistory(tmp_path).find(1, 1, 0)
    assert saved['selected'] == imported.id
    assert imported.id in {route.id for route in decode(saved)}
    assert selected.id not in {route.id for route in decode(saved)}
    assert len(decode(saved)) == 12
