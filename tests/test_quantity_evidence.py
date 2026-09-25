import json
import threading

import pytest

from dota_helper import quantity_evidence, starting_items
from dota_helper.models import Purchase, Route
from dota_helper.providers import DataError


@pytest.fixture
def route(tmp_path, monkeypatch):
    monkeypatch.setattr(starting_items, 'user_data_dir', lambda: tmp_path)
    monkeypatch.setattr(quantity_evidence, 'user_data_dir', lambda: tmp_path)
    starting_items.load.cache_clear()
    quantity_evidence._load.cache_clear()
    route = Route('stratz:100:0', 8, 1, 1, 0, 'Example',
                  [Purchase('branches', -60), Purchase('tango', -60), Purchase('manta', 1200)],
                  [], [100], 0, '', 'Example player', source='STRATZ')
    route.account_id = 12345
    route.player_slot = 0
    yield route
    starting_items.load.cache_clear()
    quantity_evidence._load.cache_clear()


def match(*, branches=2):
    return {'match_id': 100, 'players': [
        {'hero_id': 8, 'account_id': 12345, 'player_slot': 0,
         'purchase_log': [{'key': 'branches', 'time': -60} for _ in range(branches)]
                         + [{'key': 'tango', 'time': -60}, {'key': 'branches', 'time': 0},
                            {'key': 'tango', 'time': 120}]},
        {'hero_id': 8, 'account_id': 54321, 'player_slot': 128,
         'purchase_log': [{'key': 'branches', 'time': -60}] * 5},
    ]}


class Client:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def get(self, path, **kwargs):
        self.calls.append((path, kwargs))
        if self.error:
            raise self.error
        return self.response


def test_details_distinguish_recorded_estimated_and_corrected_packs(route):
    detail = {row['key']: row for row in starting_items.details(route)}
    assert detail['branches']['count'] == 2
    assert detail['branches']['recorded_count'] == 1
    assert detail['branches']['provenance'] == 'estimated'
    assert detail['tango']['provenance'] == 'recorded'
    assert detail['tango']['unit'] == 'packs'
    assert 'not remaining charges' in detail['tango']['note']
    original = [vars(p).copy() for p in route.purchases]
    starting_items.save(route, {'branches': 5, 'tango': 2})
    detail = {row['key']: row for row in starting_items.details(route)}
    assert detail['branches']['count'] == 5 and detail['branches']['recorded_count'] == 1
    assert all(row['provenance'] == 'corrected' for row in detail.values())
    assert [vars(p) for p in route.purchases] == original
    starting_items.reset(route)
    assert starting_items.correction(route) is None
    assert starting_items.counts(route) == {'branches': 2, 'tango': 1}


def test_branch_assumption_is_limited_to_incomplete_stratz(route):
    route.source = 'OpenDota'
    assert starting_items.counts(route)['branches'] == 1
    assert not starting_items.estimated_branches(route)
    assert starting_items.details(route)[0]['provenance'] == 'recorded'
    route.source = 'STRATZ'
    assert starting_items.counts(route)['branches'] == 2
    route.purchases = [Purchase(key, -60) for key in
                       ('branches', 'tango', 'magic_stick', 'quelling_blade', 'faerie_fire', 'circlet')]
    assert starting_items.counts(route)['branches'] == 1


def test_legacy_corrections_and_reset_of_bundled_screenshot(route, tmp_path):
    path = tmp_path / 'starting-items.json'
    path.write_text(json.dumps({'100:8': {'branches': 4}}), encoding='utf-8')
    starting_items.load.cache_clear()
    assert starting_items.counts(route) == {'branches': 4}
    assert starting_items.details(route)[0]['source'] == 'User correction'
    route.match_ids = [8946414154]
    assert starting_items.correction(route)['branches'] == 2
    assert starting_items.details(route)[0]['source'] == 'Screenshot correction'
    starting_items.reset(route)
    starting_items.load.cache_clear()
    assert starting_items.correction(route) is None
    assert starting_items.details(route)[0]['provenance'] == 'estimated'
    assert json.loads(path.read_text())['100:8'] == {'branches': 4}


def test_same_player_conflict_is_cached_but_never_silently_applied(route, tmp_path):
    original = [vars(p).copy() for p in route.purchases]
    client = Client(match())
    result = quantity_evidence.verify_selected(route, client)
    assert result['status'] == 'conflict'
    assert result['counts'] == {'branches': 2, 'tango': 1}
    assert result['differences'] == {'branches': {'recorded': 1, 'opendota': 2}}
    assert result['matched_by'] == 'account_id'
    assert client.calls == [('matches/100', {'ttl': quantity_evidence.SUCCESS_TTL})]
    assert starting_items.correction(route) is None
    assert [vars(p) for p in route.purchases] == original
    assert 'OpenDota records 2' in starting_items.details(route)[0]['note']
    again = quantity_evidence.verify_selected(route, client)
    assert again['cached'] and len(client.calls) == 1
    assert (tmp_path / 'quantity-evidence.json').exists()
    # Applying the reviewed comparison is an explicit override with provenance.
    starting_items.save(route, result['counts'], source='OpenDota comparison accepted', note=result['message'])
    assert starting_items.details(route)[0]['provenance'] == 'corrected'
    assert starting_items.details(route)[0]['source'] == 'OpenDota comparison accepted'
    assert quantity_evidence.verify_selected(route, client)['status'] == 'skipped'
    assert len(client.calls) == 1


def test_corroboration_preserves_event_counts_and_excludes_zero_time(route):
    route.purchases.insert(1, Purchase('branches', -60, 2))
    result = quantity_evidence.verify_selected(route, Client(match()))
    assert result['status'] == 'verified' and result['differences'] == {}
    assert result['counts'] == {'branches': 2, 'tango': 1}
    assert 'completeness is not guaranteed' in result['message']
    assert 'OpenDota agrees' in starting_items.details(route)[0]['note']
    assert starting_items.details(route)[0]['provenance'] == 'recorded'


@pytest.mark.parametrize('changed,value', [('match_id', 101), ('hero_id', 1),
                                          ('account_id', 99999), ('player_slot', 1)])
def test_known_identity_contradictions_never_supply_counts(route, changed, value):
    response = match()
    if changed == 'match_id':
        response[changed] = value
    else:
        response['players'][0][changed] = value
    result = quantity_evidence.verify_selected(route, Client(response))
    assert result['status'] == 'unavailable' and result['counts'] is None
    assert starting_items.correction(route) is None


def test_explicit_slot_supports_anonymous_player_but_ambiguous_players_fail(route):
    route.account_id = None
    response = match()
    response['players'][0]['account_id'] = None
    client = Client(response)
    assert quantity_evidence.verify_selected(route, client)['matched_by'] == 'player_slot'
    response['players'].append(dict(response['players'][0]))
    ambiguous = quantity_evidence.verify_selected(route, client, force=True)
    assert ambiguous['status'] == 'unavailable' and ambiguous['counts'] is None
    assert client.calls[-1] == ('matches/100', {'ttl': 0})


def test_legacy_route_ids_do_not_substitute_for_explicit_player_identity(route):
    route.account_id = None
    route.player_slot = None
    client = Client(match())
    result = quantity_evidence.verify_selected(route, client)
    assert result['status'] == 'skipped' and 'Refresh this lookup' in result['message']
    assert not client.calls
    route.account_id = 12345
    route.match_ids = [100, 101]
    assert quantity_evidence.verify_selected(route, client)['status'] == 'skipped'
    assert not client.calls


@pytest.mark.parametrize('log', [None, [], [{'key': 'branches', 'time': 0}],
                               [{'key': 'unknown', 'time': -60}],
                               [{'key': 'branches', 'time': float('-inf')}],
                               [{'key': ['branches'], 'time': -60}],
                               [{'key': 'branches', 'time': -60}, {'time': None}]])
def test_missing_or_malformed_purchase_data_does_not_clear_starting_buy(route, log):
    response = match()
    response['players'][0]['purchase_log'] = log
    result = quantity_evidence.verify_selected(route, Client(response))
    assert result['status'] == 'unavailable' and result['counts'] is None
    assert starting_items.counts(route) == {'branches': 2, 'tango': 1}


def test_errors_are_briefly_cached_without_exposing_request_secrets(route, tmp_path):
    client = Client(error=DataError('https://example.test/?api_key=secret-value'))
    first = quantity_evidence.verify_selected(route, client)
    assert first['status'] == 'unavailable'
    assert 'secret-value' not in json.dumps(first)
    assert 'secret-value' not in (tmp_path / 'quantity-evidence.json').read_text()
    assert quantity_evidence.verify_selected(route, client)['cached']
    assert len(client.calls) == 1


def test_http_failure_status_is_useful_without_echoing_request_details(route):
    result = quantity_evidence.verify_selected(
        route, Client(error=DataError('OpenDota HTTP 429 https://example.test/?api_key=secret-value')))
    assert 'OpenDota HTTP 429' in result['message']
    assert 'secret-value' not in result['message']


def test_cached_secondary_data_is_labelled_and_callers_cannot_mutate_saved_evidence(route):
    client = Client(match())
    client.stale = ['Cached matches/100: 72 hours old']
    result = quantity_evidence.verify_selected(route, client)
    assert 'cached OpenDota data' in result['message']
    saved = quantity_evidence.get_saved(route)
    saved['counts']['branches'] = 99
    assert quantity_evidence.get_saved(route)['counts']['branches'] == 2


def test_cancellation_during_request_is_not_cached(route, tmp_path):
    cancel = threading.Event()
    class CancelledClient(Client):
        def get(self, *args, **kwargs):
            cancel.set()
            raise DataError('Search cancelled')
    result = quantity_evidence.verify_selected(route, CancelledClient(), cancel)
    assert result['status'] == 'cancelled'
    assert not (tmp_path / 'quantity-evidence.json').exists()


def test_cache_cannot_be_reused_for_changed_source_log_or_player(route):
    quantity_evidence.verify_selected(route, Client(match()))
    assert quantity_evidence.get_saved(route) is not None
    route.purchases.insert(0, Purchase('flask', -60))
    assert quantity_evidence.get_saved(route) is None
    route.purchases.pop(0)
    route.account_id = 54321
    assert quantity_evidence.get_saved(route) is None
