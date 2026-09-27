from dataclasses import replace
from email.message import Message
from email.utils import formatdate
import io
import json
import ssl
from urllib.error import HTTPError, URLError

import pytest

from dota_helper import live_ratings
from dota_helper.live_ratings import LiveRatings, MAX_AGE, MAX_BACKOFF, SOURCE, URL
from dota_helper.models import Purchase, Route


NOW = 1_790_000_000


@pytest.fixture(autouse=True)
def clock_and_no_network(monkeypatch):
    monkeypatch.setattr(live_ratings.time, 'time', lambda: NOW)
    monkeypatch.setattr(live_ratings, 'urlopen', lambda *args, **kwargs: pytest.fail('Unexpected network call'))


def response(monkeypatch, payload):
    calls = []
    def fetch(request, **kwargs):
        calls.append((request, kwargs))
        return io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(live_ratings, 'urlopen', fetch)
    return calls


def game(mid=9017541452, **kwargs):
    return Route('r', 155, 4, 3, 0, 'Route', [Purchase('boots', 200)], [], [mid], NOW, '', '', **kwargs)


def test_refresh_records_only_rating_observations_and_restores_across_restart(tmp_path, monkeypatch):
    calls = response(monkeypatch, [{'match_id': '9017541452', 'average_mmr': 8199, 'players': [{'secret': 'unused'}]}])
    cache = LiveRatings(tmp_path)
    result = cache.refresh()
    assert result.fetched and result.count == 1 and result.error is None
    request, options = calls[0]
    assert request.full_url == URL and options['timeout'] == 3
    assert not request.has_header('Authorization')
    saved = json.loads(cache.path.read_text())
    assert set(saved) == {'version', 'last_fetch', 'next_refresh_at', 'matches',
                          'last_success', 'last_error', 'last_count'}
    assert saved['matches'] == {'9017541452': {'average_mmr': 8199, 'observed_at': NOW, 'source': SOURCE}}
    assert saved['last_success'] == NOW and saved['last_count'] == 1 and saved['last_error'] is None
    assert not list(tmp_path.glob('*.tmp'))
    restored = LiveRatings(tmp_path)
    assert restored.enrich([game()])[0].average_mmr == 8199
    assert not restored.refresh().fetched
    assert len(calls) == 1


def test_enrichment_matches_exact_first_id_and_preserves_provider_and_non_pub_routes(tmp_path, monkeypatch):
    response(monkeypatch, [{'match_id': 9017541452, 'average_mmr': 8199}])
    cache = LiveRatings(tmp_path)
    cache.refresh()
    plain = game()
    pro = game(pro_player=True)
    tournament = game(tournament=True)
    demo = game(demo=True)
    provider = game(average_mmr=9999, average_mmr_source='Provider average')
    different = game(9017541453)
    multi = replace(different, match_ids=[9017541453, 9017541452])
    enriched = cache.enrich([plain, pro, tournament, demo, provider, different, multi])
    assert enriched[0] is not plain and plain.average_mmr is None
    assert enriched[0].average_mmr == enriched[1].average_mmr == 8199
    assert enriched[0].average_mmr_source == SOURCE
    assert enriched[2:] == [tournament, demo, provider, different, multi]
    assert enriched[4] is provider


@pytest.mark.parametrize('bad', [None, 0, -1, True, 900.2, '', '001', '1.0', ' 123 ', 'nan', 2 ** 64])
def test_invalid_match_identifiers_are_not_cached(tmp_path, monkeypatch, bad):
    response(monkeypatch, [{'match_id': bad, 'average_mmr': 8000}])
    cache = LiveRatings(tmp_path)
    assert cache.refresh().count == 0
    assert cache.records == {}


@pytest.mark.parametrize('bad', [None, 0, -1, True, float('nan'), float('inf'), '9000', 30000])
def test_invalid_mmr_cannot_replace_saved_observation(tmp_path, monkeypatch, bad):
    response(monkeypatch, [{'match_id': 123, 'average_mmr': 8000}])
    cache = LiveRatings(tmp_path)
    cache.refresh()
    monkeypatch.setattr(live_ratings.time, 'time', lambda: NOW + 121)
    response(monkeypatch, [{'match_id': 123, 'average_mmr': bad}])
    assert cache.refresh().count == 0
    assert cache.enrich([game(123)])[0].average_mmr == 8000


@pytest.mark.parametrize('failure', [URLError('offline'), ValueError('broken JSON')])
def test_failures_retain_cache_and_throttle_retries(tmp_path, monkeypatch, failure):
    response(monkeypatch, [{'match_id': 123, 'average_mmr': 8000}])
    cache = LiveRatings(tmp_path)
    cache.refresh()
    monkeypatch.setattr(live_ratings.time, 'time', lambda: NOW + 121)
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(live_ratings, 'urlopen', fail)
    result = cache.refresh()
    assert result.error and result.fetched
    restored = LiveRatings(tmp_path)
    assert restored.enrich([game(123)])[0].average_mmr == 8000
    assert not restored.refresh().fetched


@pytest.mark.parametrize('retry,delay', [('600', 600), ('5', 120), ('99999999', MAX_BACKOFF),
                                        ('nan', 300), (formatdate(NOW + 900, usegmt=True), 900)])
def test_429_backoff_is_persisted_and_bounded(tmp_path, monkeypatch, retry, delay):
    headers = Message()
    headers['Retry-After'] = retry
    def fail(*args, **kwargs):
        raise HTTPError(URL, 429, 'Limited', headers, None)
    monkeypatch.setattr(live_ratings, 'urlopen', fail)
    cache = LiveRatings(tmp_path)
    result = cache.refresh()
    assert result.error == 'HTTP 429'
    assert cache.next_refresh_at == NOW + delay
    assert not LiveRatings(tmp_path).refresh().fetched


def test_old_malformed_and_excess_cache_entries_are_discarded_without_settings_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(live_ratings, 'MAX_RECORDS', 2)
    record = dict(average_mmr=8000, observed_at=NOW, source=SOURCE)
    saved = dict(last_fetch=NOW, next_refresh_at=NOW + 120, matches={
        '1': record, '2': dict(record, observed_at=NOW - 1), '3': dict(record, observed_at=NOW - 2),
        '4': dict(record, observed_at=NOW - MAX_AGE - 1), '5': dict(record, observed_at=True),
        '6': dict(record, source='unknown'), '0': record, '7': 'invalid',
    })
    (tmp_path / 'match-ratings.json').write_text(json.dumps(saved))
    settings = tmp_path / 'settings.json'
    settings.write_text('unchanged settings')
    cache = LiveRatings(tmp_path)
    assert set(cache.records) == {'1', '2'}
    assert settings.read_text() == 'unchanged settings'


def test_corrupt_optional_cache_and_storage_failure_do_not_block_enrichment(tmp_path, monkeypatch):
    (tmp_path / 'match-ratings.json').write_text('{broken')
    cache = LiveRatings(tmp_path)
    assert cache.records == {}
    response(monkeypatch, [{'match_id': 123, 'average_mmr': 8000}])
    monkeypatch.setattr(cache, '_save', lambda: (_ for _ in ()).throw(OSError('locked')))
    result = cache.refresh()
    assert result.count == 1 and result.error
    assert cache.enrich([game(123)])[0].average_mmr == 8000


def test_empty_feed_preserves_observations_until_retention_expires(tmp_path, monkeypatch):
    response(monkeypatch, [{'match_id': 123, 'average_mmr': 8000}])
    cache = LiveRatings(tmp_path)
    cache.refresh()
    monkeypatch.setattr(live_ratings.time, 'time', lambda: NOW + 121)
    response(monkeypatch, [])
    assert cache.refresh().count == 0
    assert cache.enrich([game(123)])[0].average_mmr == 8000
    monkeypatch.setattr(live_ratings.time, 'time', lambda: NOW + MAX_AGE + 1)
    assert cache.enrich([game(123)])[0].average_mmr is None
    cache.refresh()
    assert cache.records == {}


@pytest.mark.parametrize('failure,category', [
    (TimeoutError('private timeout details'), 'Connection timed out'),
    (URLError(TimeoutError('private timeout details')), 'Connection timed out'),
    (ssl.SSLError('private certificate details'), 'TLS connection failed'),
    (URLError(ssl.SSLError('private certificate details')), 'TLS connection failed'),
    (URLError('https://private.invalid/?key=secret'), 'Network connection failed'),
])
def test_failure_categories_are_safe_persistent_and_reported_during_cooldown(tmp_path, monkeypatch, failure, category):
    response(monkeypatch, [{'match_id': 123, 'average_mmr': 8000}])
    cache = LiveRatings(tmp_path)
    cache.refresh()
    monkeypatch.setattr(live_ratings.time, 'time', lambda: NOW + 121)
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(live_ratings, 'urlopen', fail)
    result = cache.refresh()
    assert result.error == category and category in result.status
    restored = LiveRatings(tmp_path)
    assert restored.last_error == category
    assert restored.last_success == NOW and restored.last_fetch == NOW + 121
    assert restored.last_count == 0
    assert 'private' not in restored.path.read_text()
    assert 'secret' not in restored.path.read_text()
    monkeypatch.setattr(live_ratings.time, 'time', lambda: NOW + 151)
    skipped = restored.refresh()
    assert not skipped.fetched and skipped.error == category
    assert category in skipped.status and 'retry in 90s' in skipped.status
    assert restored.enrich([game(123)])[0].average_mmr == 8000


@pytest.mark.parametrize('body', [b'\xffnot-utf8', b'{bad JSON', b'{"not":"a list"}'])
def test_invalid_response_diagnostics_do_not_expose_payload(tmp_path, monkeypatch, body):
    monkeypatch.setattr(live_ratings, 'urlopen', lambda *args, **kwargs: io.BytesIO(body))
    cache = LiveRatings(tmp_path)
    result = cache.refresh()
    assert result.error == 'Invalid live feed response'
    assert cache.last_success == 0
    assert LiveRatings(tmp_path).last_error == result.error


def test_zero_success_never_fetched_and_unknown_legacy_outcomes_are_distinct(tmp_path, monkeypatch):
    cache = LiveRatings(tmp_path)
    assert cache.status_text() == 'MMR feed waiting for first check'
    # Original caches recorded an attempt but not its result. Do not invent one.
    cache.path.write_text(json.dumps(dict(version=1, last_fetch=NOW, next_refresh_at=NOW + 120, matches={})))
    legacy = LiveRatings(tmp_path)
    assert 'outcome unavailable' in legacy.status_text()
    assert 'retry in 120s' in legacy.refresh().status
    monkeypatch.setattr(live_ratings.time, 'time', lambda: NOW + 121)
    response(monkeypatch, [])
    result = legacy.refresh()
    assert result.error is None and result.count == 0
    assert 'responded with no positive readings' in result.status
    restored = LiveRatings(tmp_path)
    assert restored.last_success == NOW + 121
    assert restored.last_count == 0 and restored.last_error is None


def test_429_reason_and_retry_survive_restart_then_success_clears_error(tmp_path, monkeypatch):
    headers = Message()
    headers['Retry-After'] = '600'
    def limited(*args, **kwargs):
        raise HTTPError(URL, 429, 'private server details', headers, None)
    monkeypatch.setattr(live_ratings, 'urlopen', limited)
    cache = LiveRatings(tmp_path)
    assert 'HTTP 429' in cache.refresh().status
    restored = LiveRatings(tmp_path)
    assert 'HTTP 429' in restored.refresh().status
    assert 'retry in 600s' in restored.status_text()
    assert 'private' not in restored.path.read_text()
    monkeypatch.setattr(live_ratings.time, 'time', lambda: NOW + 601)
    response(monkeypatch, [{'match_id': 123, 'average_mmr': 8000}])
    result = restored.refresh()
    assert result.error is None and restored.last_error is None
    assert restored.last_success == NOW + 601 and restored.last_count == 1
    assert 'feed ready' in result.status
    assert LiveRatings(tmp_path).last_error is None


def test_untrusted_cached_diagnostics_are_not_shown(tmp_path):
    (tmp_path / 'match-ratings.json').write_text(json.dumps(dict(
        last_fetch=NOW, next_refresh_at=NOW + 120, last_success=True,
        last_count=True, last_error='https://private.invalid/?key=secret', matches={})))
    cache = LiveRatings(tmp_path)
    assert cache.last_success == 0 and cache.last_count == 0 and cache.last_error is None
    assert 'private' not in cache.status_text()


def test_observation_count_excludes_expired_records_without_mutating_cache(tmp_path):
    cache = LiveRatings(tmp_path)
    record = dict(average_mmr=8000, observed_at=NOW, source=SOURCE)
    cache.records = {'1': record, '2': dict(record, observed_at=NOW - MAX_AGE - 1),
                     '3': dict(record, observed_at=NOW + 301)}
    before = dict(cache.records)
    assert cache.observation_count() == 1
    assert cache.records == before


def test_hero_discovery_persists_only_hero_ids_and_exact_reported_match_mmr(tmp_path, monkeypatch):
    response(monkeypatch, [{
        'match_id': 123, 'average_mmr': 8100, 'players': [
            {'hero_id': 155, 'account_id': 987654321, 'name': 'private player name'},
            {'hero_id': 1}, {'hero_id': 155}, {'hero_id': True}, {'hero_id': '2'},
            {'hero_id': 0}, {'hero_id': -1}, {'hero_id': 3.0}, 'invalid',
        ],
    }])
    cache = LiveRatings(tmp_path)
    cache.refresh()
    payload = cache.path.read_text()
    assert 'private player name' not in payload and '987654321' not in payload
    assert 'players' not in payload and 'account_id' not in payload
    restored = LiveRatings(tmp_path)
    assert restored.records['123']['hero_ids'] == [1, 155]
    assert restored.candidates(155) == [{'match_id': 123, 'average_mmr': 8100, 'observed_at': NOW}]
    assert restored.candidates(1) == restored.candidates(155)
    assert restored.candidates(2) == []
    assert restored.candidates(155, minimum_mmr=8101) == []


def test_candidates_are_not_capped_at_ten_and_sort_by_mmr_then_observation_time(tmp_path, monkeypatch):
    response(monkeypatch, [{'match_id': mid, 'average_mmr': 7000 + mid * 10, 'players': [{'hero_id': 155}]}
                           for mid in range(1, 16)])
    cache = LiveRatings(tmp_path)
    cache.refresh()
    assert [row['match_id'] for row in cache.candidates(155)] == list(range(15, 0, -1))
    monkeypatch.setattr(live_ratings.time, 'time', lambda: NOW + 121)
    response(monkeypatch, [{'match_id': 16, 'average_mmr': 7150, 'players': [{'hero_id': 155}]}])
    cache.refresh()
    assert [row['match_id'] for row in cache.candidates(155)][:2] == [16, 15]
    assert cache.candidates(155)[0]['average_mmr'] == 7150
    assert cache.candidates(155, minimum_mmr=0)[-1]['average_mmr'] == 7010


@pytest.mark.parametrize('players', [None, {}, 'invalid', [], [None], [{'account_id': 999}],
                                     [{'hero_id': True}], [{'hero_id': '155'}]])
def test_missing_hero_metadata_preserves_previous_heroes_without_inflating_updated_mmr(tmp_path, monkeypatch, players):
    response(monkeypatch, [{'match_id': 123, 'average_mmr': 9000, 'players': [{'hero_id': 155}]}])
    cache = LiveRatings(tmp_path)
    cache.refresh()
    monkeypatch.setattr(live_ratings.time, 'time', lambda: NOW + 121)
    response(monkeypatch, [{'match_id': 123, 'average_mmr': 8000, 'players': players}])
    cache.refresh()
    restored = LiveRatings(tmp_path)
    assert restored.candidates(155) == [{'match_id': 123, 'average_mmr': 8000, 'observed_at': NOW + 121}]


@pytest.mark.parametrize('heroes', [None, True, 155, '155', {'hero_id': 155}, [True, '155', 0, -1, 155.0]])
def test_legacy_or_invalid_cached_hero_metadata_remains_enrichable_but_not_discoverable(tmp_path, heroes):
    record = dict(average_mmr=8100, observed_at=NOW, source=SOURCE)
    if heroes is not None:
        record['hero_ids'] = heroes
    (tmp_path / 'match-ratings.json').write_text(json.dumps({'matches': {'123': record}}))
    cache = LiveRatings(tmp_path)
    assert cache.enrich([game(123)])[0].average_mmr == 8100
    assert cache.candidates(155) == []


@pytest.mark.parametrize('hero,minimum', [(True, 7000), ('155', 7000), (155.0, 7000), (0, 7000),
                                        (155, True), (155, '7000'), (155, float('nan')),
                                        (155, float('inf')), (155, -1)])
def test_invalid_candidate_filters_return_nothing(tmp_path, hero, minimum):
    cache = LiveRatings(tmp_path)
    cache.records = {'123': dict(average_mmr=8100, observed_at=NOW, source=SOURCE, hero_ids=[155])}
    assert cache.candidates(hero, minimum_mmr=minimum) == []


def test_expired_candidate_is_excluded_without_network_or_cache_mutation(tmp_path):
    cache = LiveRatings(tmp_path)
    cache.records = {'123': dict(average_mmr=8100, observed_at=NOW - MAX_AGE - 1,
                                 source=SOURCE, hero_ids=[155])}
    assert cache.candidates(155) == []
    assert '123' in cache.records


def test_positive_mmr_below_seven_thousand_reaches_independent_rank_verification(tmp_path, monkeypatch):
    response(monkeypatch, [
        {'match_id': '9017688569', 'average_mmr': 6520, 'players': [{'hero_id': 32}]},
        {'match_id': '9017846688', 'average_mmr': 5869, 'players': [{'hero_id': 32}]},
    ])
    cache = LiveRatings(tmp_path)
    cache.refresh()
    assert [row['average_mmr'] for row in cache.candidates(32)] == [6520, 5869]
    assert cache.candidates(32, minimum_mmr=7000) == []
