"""An exact match's rating survives updated builds and provider selection."""
import time

import pytest

from dota_helper.history import SearchHistory, decode
from dota_helper.models import Purchase, Route
from dota_helper.ranking import ranked


def game(source='STRATZ', **overrides):
    values = dict(id=f'{source}:9017730384:4', hero_id=136, role=4, lane=3,
                  patch=0, title='Recorded Hoodwink game', purchases=[Purchase('boots', 300)],
                  skills=['hoodwink_acorn_shot'], match_ids=[9017730384],
                  start_time=int(time.time()) - 3600, evidence='Match bracket Immortal',
                  player='', source=source, account_id=1218097624)
    values.update(overrides)
    return Route(**values)


def rated(source='STRATZ', **overrides):
    values = dict(average_mmr=8352, average_mmr_source='OpenDota live feed',
                  average_rank=80, average_rank_source='STRATZ averageRank')
    values.update(overrides)
    return game(source, **values)


def test_refresh_keeps_exact_match_averages_and_new_build_details_without_mutation():
    old = rated()
    fresh = game(title='Updated purchases', purchases=[Purchase('boots', 320)])
    result, = ranked([old, fresh])
    assert result.id == fresh.id and result.title == fresh.title
    assert result.purchases == fresh.purchases and result.skills == fresh.skills
    assert (result.average_mmr, result.average_mmr_source) == (8352, 'OpenDota live feed')
    assert (result.average_rank, result.average_rank_source) == (80, 'STRATZ averageRank')
    assert fresh.average_mmr is None and fresh.average_rank is None


def test_preferred_provider_keeps_its_build_and_borrows_exact_match_averages():
    donor, selected = rated('OpenDota'), game('STRATZ')
    result, = ranked([donor, selected], preferred_id=selected.id)
    assert result.id == selected.id and result.source == 'STRATZ'
    assert result.purchases == selected.purchases
    assert result.average_mmr == 8352 and result.average_rank == 80
    assert result.average_mmr_source == donor.average_mmr_source


def test_missing_donor_source_uses_its_provider_instead_of_selected_provider():
    donor, selected = rated('OpenDota', average_mmr_source='', average_rank_source=''), game()
    result, = ranked([donor, selected], preferred_id=selected.id)
    assert 'OpenDota' in result.average_mmr_source
    assert 'OpenDota' in result.average_rank_source


def test_selected_valid_values_are_never_overwritten_by_different_measurements():
    donor = rated('OpenDota')
    selected = rated(average_mmr=9000, average_mmr_source='New provider average', average_rank=79)
    result, = ranked([donor, selected], preferred_id=selected.id)
    assert result is selected
    assert (result.average_mmr, result.average_rank) == (9000, 79)


def test_conflicting_donors_do_not_fill_a_missing_measurement():
    first = rated('OpenDota')
    second = rated('Second provider', average_mmr=9000, average_rank=79)
    selected = game()
    result, = ranked([first, second, selected], preferred_id=selected.id)
    assert result is selected
    assert result.average_mmr is None and result.average_rank is None


@pytest.mark.parametrize('changes', [
    {'account_id': 999}, {'hero_id': 1}, {'role': 1}, {'match_ids': [9017730385]},
    {'tournament': True}, {'demo': True}, {'match_ids': []},
])
def test_unrelated_or_conflicting_donors_never_supply_ratings(changes):
    selected = game()
    donor = rated('OpenDota', **changes)
    result = next(route for route in ranked([donor, selected], preferred_id=selected.id)
                  if route.id == selected.id)
    assert result.average_mmr is None and result.average_rank is None


@pytest.mark.parametrize('changes', [{'tournament': True}, {'demo': True}, {'match_ids': []}])
def test_non_pub_selected_routes_never_receive_ratings(changes):
    selected = game(**changes)
    result = next(route for route in ranked([rated('OpenDota'), selected], preferred_id=selected.id)
                  if route.id == selected.id)
    assert result.average_mmr is None and result.average_rank is None


def test_recovered_rating_changes_sort_order_and_survives_history_reopen(tmp_path):
    selected = game()
    other = game('Other', match_ids=[9017730385], id='other', average_mmr=8000)
    history = SearchHistory(tmp_path)
    history.save(136, 4, 0, [rated(), other], selected.id, 'Original ratings')
    history.save(136, 4, 0, [selected], selected.id, 'Updated purchases')
    result = decode(SearchHistory(tmp_path).find(136, 4, 0))
    assert [route.id for route in result] == [selected.id, other.id]
    assert result[0].average_mmr == 8352
    assert result[0].average_mmr_source == 'OpenDota live feed'


def test_pro_priority_survives_rating_recovery_and_both_provenances_are_preserved():
    pro = game('Pro', id='pro', match_ids=[9017730385], pro_player=True)
    selected = game()
    donor = rated('OpenDota')
    result = ranked([selected, donor, pro], preferred_id=selected.id)
    assert [route.id for route in result] == [pro.id, selected.id]
    assert result[1].average_mmr_source == 'OpenDota live feed'
    assert result[1].average_rank_source == 'STRATZ averageRank'
