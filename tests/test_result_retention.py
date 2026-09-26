"""Regression coverage for games disappearing as lookup batches arrive."""
from dataclasses import replace

import pytest

from dota_helper.app import MainWindow
from dota_helper.catalog import HEROES, PATCHES
from dota_helper.history import SearchHistory, decode
from dota_helper.models import Purchase, Route
from dota_helper.ranking import ranked


LARGO = next(int(key) for key, hero in HEROES.items() if hero['localized_name'] == 'Largo')


def game(mid, *, tournament=False, hero=LARGO, role=4):
    return Route(
        id=f'lookup:{mid}:{hero}', hero_id=hero, role=role, lane=3,
        patch=0 if tournament else PATCHES[-1]['id'],
        patch_label='Unverified' if tournament else PATCHES[-1]['name'],
        title=f'Game {mid}', purchases=[Purchase('tango', -30), Purchase('tranquil_boots', 240)],
        skills=[], match_ids=[mid], start_time=1_750_000_000 + mid % 1000,
        evidence='Tournament match' if tournament else 'Immortal match bracket',
        player='League player' if tournament else '', tournament=tournament,
        match_rank=None if tournament else 80,
    )


@pytest.fixture
def window(tmp_path, monkeypatch, qt_application):
    monkeypatch.setattr('dota_helper.app.LOCAL', tmp_path)
    view = MainWindow(start_services=False)
    view.timer.stop()
    view.capture_timer.stop()
    view.hero.setCurrentIndex(view.hero.findData(LARGO))
    view.role.setCurrentIndex(view.role.findData(4))
    jobs = []
    view.launch_worker = lambda *args, **kwargs: jobs.append((args, kwargs))
    yield view, jobs
    view.close()
    qt_application.processEvents()


def start_lookup(view, jobs):
    view.fetch(force=True)
    args, kwargs = jobs[-1]
    return kwargs['partial'], args[1]


def ids(routes):
    return [route.id for route in routes]


def test_default_ranking_keeps_every_game_but_explicit_limits_still_work():
    tournaments = [game(mid, tournament=True) for mid in (8973207148, 8972898065)]
    pubs = [game(mid) for mid in range(10)]
    expected = ids(sorted(tournaments, key=lambda route: route.start_time, reverse=True))
    expected += ids(sorted(pubs, key=lambda route: route.start_time, reverse=True))
    assert ids(ranked(tournaments + pubs)) == expected
    assert ids(ranked(tournaments + pubs, limit=3)) == expected[:3]


def test_largo_tournaments_survive_pub_batch_and_remain_selectable_and_saved(window, tmp_path):
    view, jobs = window
    tournaments = [game(mid, tournament=True) for mid in (8973207148, 8972898065)]
    pubs = [game(mid) for mid in range(10)]
    partial, finish = start_lookup(view, jobs)
    partial((tournaments, 'Two tournament games'))
    view.route_choice.setCurrentIndex(view.route_choice.findData(tournaments[1].id))
    assert view.session.explicit_choice

    partial((pubs, 'Ten current-patch Immortal pubs'))
    finish((pubs, 'Lookup complete'))

    expected = ids(ranked(tournaments + pubs))
    assert len(view.routes) == 12
    assert ids(view.routes) == expected
    assert view.match_table.rowCount() == view.route_choice.count() == 12
    assert [view.route_choice.itemData(row) for row in range(12)] == expected
    assert view.current_route().id == tournaments[1].id
    for route_id in expected:
        view.route_choice.setCurrentIndex(view.route_choice.findData(route_id))
        assert view.current_route().id == route_id

    saved = SearchHistory(tmp_path).find(LARGO, 4, 0)
    assert ids(decode(saved)) == expected
    assert saved['selected'] == view.current_route().id


def test_automatic_choice_moves_to_strongest_new_result(window):
    view, jobs = window
    partial, finish = start_lookup(view, jobs)
    tournament = game(100, tournament=True)
    partial(([tournament], 'Tournament cache'))
    assert view.current_route().id == tournament.id
    assert not view.session.explicit_choice
    pub = game(101)
    finish(([pub], 'Current patch ready'))
    assert ids(view.routes) == [tournament.id, pub.id]
    assert view.current_route().id == tournament.id
    assert not view.session.explicit_choice


def test_refresh_replaces_matching_record_without_losing_other_games_and_filters_context(window, tmp_path):
    view, jobs = window
    original = [game(mid) for mid in range(12)]
    selected = original[0]
    view.history.save(LARGO, 4, 0, original, selected.id, 'Saved lookup')
    view.show_saved_search(view.history.find(LARGO, 4, 0))
    view.session.choose(selected.id)
    partial, finish = start_lookup(view, jobs)
    fresh = replace(selected, title='Refreshed purchases', average_mmr=10_500,
                    purchases=selected.purchases + [Purchase('blink', 600)])
    extra = game(20)
    wrong_hero = game(21, hero=1)
    wrong_role = game(22, role=5)
    partial(([fresh, extra, wrong_hero, wrong_role], 'Refresh partial'))
    finish(([extra], 'Refresh complete'))

    assert len(view.routes) == 13
    assert set(ids(view.routes)) == set(ids(original + [extra]))
    assert view.current_route() is fresh
    assert view.current_route().purchases[-1].key == 'blink'
    saved = SearchHistory(tmp_path).find(LARGO, 4, 0)
    records = decode(saved)
    assert len(records) == 13
    assert all(route.hero_id == LARGO and route.role == 4 for route in records)
    assert next(route for route in records if route.id == fresh.id).average_mmr == 10_500


def test_manual_import_adds_eleventh_game_without_evicting_existing_choices(window):
    view, jobs = window
    original = [game(mid) for mid in range(10)]
    view.routes = ranked(original)
    view.session.accept_routes(view.routes)
    view.render_routes()
    imported = game(8946414154)
    view.match_input.setText(str(imported.match_ids[0]))
    view.import_match()
    jobs[-1][0][1](imported)

    assert len(view.routes) == 11
    assert set(ids(view.routes)) == set(ids(original + [imported]))
    assert view.match_table.rowCount() == view.route_choice.count() == 11
    assert view.current_route().id == imported.id
    assert view.session.explicit_choice
