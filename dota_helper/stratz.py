"""Authenticated STRATZ guides and exact user-selected matches.

Only supported, ordinary-user fields are used: no bulk matches or replay rebuilds.
"""
from collections import Counter
from datetime import datetime
import hashlib
import json
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid
from email.utils import parsedate_to_datetime
from pathlib import Path

from .builds import normalize
from .catalog import HEROES, ITEMS, PATCHES
from .credentials import load_token
from .fast_lookup import DeadlineJobs
from .paths import user_data_dir
from .providers import DataError
from .ranking import ranked

SUMMARY = "id startDateTime gameVersionId rank lobbyType leagueId"
PLAYER = "heroId steamAccountId position playerSlot isRadiant variant steamAccount {name seasonRank seasonLeaderboardRank proSteamAccount {name}}"
DETAIL = SUMMARY + " didRadiantWin players {" + PLAYER + " stats {itemPurchases {time itemId}} abilities {abilityId time level isTalent}}"
ITEM_KEYS = {int(v['id']): k for k, v in ITEMS.items() if v.get('id') is not None}


def references(hero_id, root=None):
    try:
        data = json.loads(((root or user_data_dir()) / 'stratz-reference-matches.json').read_text())
        return list(dict.fromkeys(int(n) for n in data.get(str(hero_id), []) if str(n).isdecimal()))[:10]
    except (OSError, ValueError, TypeError):
        return []


def reference_query(ids, details=False, accounts=None):
    fields = DETAIL if details else SUMMARY + " players {" + PLAYER + "}"
    entries = []
    for i, mid in enumerate(ids):
        selected_fields = fields
        if details and accounts and accounts.get(mid):
            selected_fields = fields.replace('players {', f"players(steamAccountId:{int(accounts[mid])}) {{")
        entries.append(f"m{i}:match(id:{int(mid)}){{{selected_fields}}}")
    return " ".join(entries)


def guide_query(refs=(), first=True):
    extra = 'constants {gameVersions {id name asOfDateTime}} ' + reference_query(refs) if first else ''
    return ('query($hero:Short!,$position:MatchPlayerPositionType!,$skip:Int!){' + extra
            + ' heroStats {guide(heroId:$hero,positionId:$position) {matchCount guides(take:50,skip:$skip) {'
            + 'matchId heroId steamAccountId match {' + SUMMARY + '}}}}}')


class Stratz:
    def __init__(self, cache_dir=None, token=None, refresh=False):
        self.cache_dir = Path(cache_dir) if cache_dir else user_data_dir() / 'cache'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.token = token
        self.refresh = refresh

    def query(self, query, variables=None, ttl=300):
        try:
            token = self.token if self.token is not None else load_token()
        except RuntimeError:
            raise DataError("STRATZ key could not be decrypted. Save it again in Overlay & connection.") from None
        if not token:
            raise DataError("Save your STRATZ API key in Overlay & connection first.")
        body = json.dumps({'query': query, 'variables': variables or {}}, sort_keys=True).encode()
        file = self.cache_dir / ('stratz-' + hashlib.sha256(body).hexdigest() + '.json')
        detail_query = 'itemPurchases' in query and ':match(' in query and 'leagues(' not in query
        if ttl == 300:
            ttl = 30*86400 if detail_query else 0 if self.refresh else 300
        try:
            cached = json.loads(file.read_text(encoding='utf-8'))
            # Missing/unparsed matches are retried promptly instead of frozen for a month.
            complete = all(isinstance(v,dict) and any((p.get('stats') or {}).get('itemPurchases') and p.get('abilities')
                           for p in v.get('players') or []) for k,v in cached['data'].items() if k.startswith('m'))
            effective_ttl = min(ttl,300) if detail_query and not complete else ttl
            if time.time() - cached['at'] < effective_ttl:
                return cached['data']
        except (OSError, ValueError, KeyError):
            pass
        cooldown = self.cache_dir / 'stratz-rate-limit.json'
        try:
            until = float(json.loads(cooldown.read_text())['until'])
            if until > time.time():
                raise DataError(self.rate_limit_message(until))
        except (OSError, ValueError, KeyError, TypeError):
            pass
        req = Request('https://api.stratz.com/graphql', data=body, headers={
            'Authorization': 'Bearer ' + token, 'User-Agent': 'STRATZ_API', 'Content-Type': 'application/json'})
        try:
            with urlopen(req, timeout=3) as response:
                result = json.load(response)
        except HTTPError as exc:
            if exc.code == 429:
                retry = (exc.headers or {}).get('Retry-After', '60')
                try:
                    until = time.time() + max(1, int(retry))
                except (ValueError, TypeError):
                    try:
                        until = parsedate_to_datetime(retry).timestamp()
                    except (ValueError, TypeError, OverflowError):
                        until = time.time() + 60
                temp = cooldown.with_suffix(f'.{uuid.uuid4().hex}.tmp')
                try:
                    temp.write_text(json.dumps({'until':until}), encoding='utf-8')
                    temp.replace(cooldown)
                except OSError:
                    pass
                raise DataError(self.rate_limit_message(until)) from None
            raise DataError(f"STRATZ HTTP {exc.code}. " + ("Check the saved key and API access." if exc.code in (401,403) else "Try again shortly.")) from None
        except (URLError, OSError, ValueError):
            raise DataError("STRATZ request failed or timed out. Your selected game is retained.") from None
        if not isinstance(result, dict) or result.get('errors') or not isinstance(result.get('data'), dict):
            raise DataError("STRATZ could not complete this query. No partial response was saved.")
        temp = file.with_suffix(f'.{uuid.uuid4().hex}.tmp')
        temp.write_text(json.dumps({'at': time.time(), 'data': result['data']}), encoding='utf-8')
        temp.replace(file)
        return result['data']

    @staticmethod
    def rate_limit_message(until):
        seconds = max(1, int(until-time.time())+1)
        return (f"STRATZ request limit reached. New requests paused for {seconds//60}m {seconds%60:02d}s "
                f"(retry after {datetime.fromtimestamp(until).strftime('%H:%M:%S')} local time). Cached builds remain usable.")

    def bounded(self, jobs, query, variables=None):
        if not jobs.submit('stratz', lambda: self.query(query, variables)):
            raise DataError("STRATZ lookup busy or time budget exhausted. Try again shortly.")
        event = jobs.next()
        if jobs.cancel.is_set():
            raise DataError("Search cancelled")
        if event is None:
            raise DataError("STRATZ lookup exceeded the 8-second budget. Try again shortly.")
        _, data, error = event
        if error:
            raise error
        return data

    def routes(self, hero_id, role, progress=lambda _: None, cancel=None, on_update=None, reference_ids=None, deadline=None):
        if str(hero_id) not in HEROES or role not in range(1,6):
            raise DataError("Choose a valid hero and position.")
        cancel = cancel or threading.Event()
        jobs = DeadlineJobs(cancel)
        if deadline is not None:
            jobs.deadline=min(jobs.deadline,deadline)
        started = time.monotonic()
        refs = references(hero_id) if reference_ids is None else reference_ids[:10]
        versions, routes, attempted, fingerprints = {}, [], set(), set()
        skipped = Counter()
        offset, scanned, reported, exhausted = 0, 0, 0, False
        pending, older_pending, failure = [], [], None
        expanded = False
        player_fallback_round = 0
        history_accounts = set()
        history_ids = set()
        history_players_checked = 0
        history_matches_checked = 0

        def page_query(first):
            # Pagination is on guides, NOT on the outer hero-group field.
            return guide_query(refs,first)

        def publish():
            if routes and on_update:
                on_update((ranked(routes), f'STRATZ · {len(routes)}/10 distinct builds ready · searching for remaining games…'))

        progress('STRATZ · searching ranked games for this hero and position…')
        while len(routes) < 10 and time.monotonic() < jobs.deadline and not cancel.is_set():
            if not pending and exhausted and older_pending:
                pending = sorted(older_pending, key=lambda pair: pair[0]['startDateTime'], reverse=True)
                older_pending = []
                expanded = True
            if not pending and exhausted and not older_pending and player_fallback_round < 2:
                player_fallback_round += 1
                progress('STRATZ · guide list exhausted; checking high-ranked player histories…')
                try:
                    # A player's usual leaderboard position need not match every game.
                    # Second pass broadens PLAYER discovery, never match eligibility.
                    leader_query = ('query($hero:Short!,$position:MatchPlayerPositionType!){leaderboard {'
                        'season(request:{heroId:$hero,position:$position}) {playerCount players(take:20){steamAccountId rank}}}}')
                    variables = {'hero':hero_id,'position':f'POSITION_{role}'}
                    if player_fallback_round == 2:
                        leader_query = leader_query.replace(',$position:MatchPlayerPositionType!', '').replace(',position:$position', '')
                        variables = {'hero':hero_id}
                    leaders = self.bounded(jobs, leader_query, variables)
                    accounts = [p['steamAccountId'] for p in ((leaders.get('leaderboard',{}).get('season') or {}).get('players') or [])
                                if p.get('steamAccountId') and (p.get('rank') or 0)>0 and p['steamAccountId'] not in history_accounts][:20]
                    if accounts:
                        history_accounts.update(accounts)
                        history_players_checked += len(accounts)
                        since = int(datetime.fromisoformat(PATCHES[-1]['date'].replace('Z','+00:00')).timestamp())
                        fields = ' '.join(f'p{i}:player(steamAccountId:{int(account)}){{matches(request:{{heroIds:[{hero_id}],'
                            f'positionIds:[POSITION_{role}],startDateTime:{since},take:10,lobbyTypeIds:[7],rankIds:[80]}})'
                            '{' + SUMMARY + f' players(steamAccountId:{int(account)})' + '{' + PLAYER + '}}}'
                            for i,account in enumerate(accounts))
                        histories = self.bounded(jobs,'{'+fields+'}')
                        for entry in histories.values():
                            for match in (entry or {}).get('matches') or []:
                                history_matches_checked += 1
                                for player in match.get('players',[]):
                                    if eligible(match,player,hero_id,role,recent=False):
                                        pending.append((match,player))
                                        history_ids.add(match['id'])
                        pending.sort(key=lambda pair:pair[0]['startDateTime'],reverse=True)
                        expanded = True
                    else:
                        skipped['no matching active leaderboard players'] += 1
                except DataError as exc:
                    failure = str(exc)
                    break
            if not pending and not exhausted:
                try:
                    data = self.bounded(jobs, page_query(offset == 0),
                                        {'hero':hero_id,'position':f'POSITION_{role}','skip':offset})
                except DataError as exc:
                    failure = str(exc)
                    break
                if offset == 0:
                    versions = {v['id']:v['name'] for v in data.get('constants',{}).get('gameVersions',[])}
                    for i, mid in enumerate(refs):
                        match = data.get(f'm{i}')
                        if match:
                            for player in match.get('players',[]):
                                if eligible(match,player,hero_id,role,recent=False,allow_league=True):
                                    pending.append((match,player))
                        else:
                            skipped['reference unavailable'] += 1
                groups = (data.get('heroStats') or {}).get('guide') or []
                guides = [g for group in groups for g in group.get('guides') or []]
                reported = max(reported, sum(g.get('matchCount') or 0 for g in groups))
                scanned += len(guides)
                for guide in guides:
                    match = guide.get('match')
                    # matchPlayer is unreliable (can be null on valid guides).
                    # Use the stable guide account ID, and verify actual role in details.
                    player = guide.get('matchPlayer') or {'heroId':guide.get('heroId'),
                              'steamAccountId':guide.get('steamAccountId'), 'position':f'POSITION_{role}'}
                    if match and player.get('steamAccountId') and eligible(match,player,hero_id,role):
                        pending.append((match,player))
                    elif match and player.get('steamAccountId') and eligible(match,player,hero_id,role,recent=False):
                        older_pending.append((match,player))
                    else:
                        skipped['outside recent Immortal criteria or missing ID'] += 1
                exhausted = len(guides) < 50 or (reported > 0 and offset + len(guides) >= reported)
                offset += 50
            # Source summaries already identify game versions. Prioritize those
            # that agree with bundled metadata before spending detail requests.
            def candidate_key(pair):
                match, player = pair
                version = versions.get(match.get('gameVersionId'), '')
                major = re.match(r'^\d+\.\d+', version)
                verified = bool(major and major[0] == PATCHES[-1]['name'])
                account = player.get('steamAccount') or {}
                tier = 2 if match.get('leagueId') and match.get('lobbyType') == 'PRACTICE' else int(bool((account.get('proSteamAccount') or {}).get('name')))
                return verified, tier, match.get('startDateTime', 0)
            pending.sort(key=candidate_key, reverse=True)
            selected = {}
            while pending and len(selected) < 10 - len(routes):
                match, player = pending.pop(0)
                mid = match['id']
                if mid in attempted:
                    continue
                attempted.add(mid)
                selected[mid] = player
            if not selected:
                if exhausted and not older_pending and player_fallback_round >= 2:
                    break
                continue
            ids = list(selected)
            progress(f'STRATZ · {len(routes)}/10 ready · loading {len(ids)} further games…')
            try:
                details = self.bounded(jobs, '{' + reference_query(ids, details=True,
                                              accounts={mid:p.get('steamAccountId') for mid,p in selected.items()}) + '}')
            except DataError as exc:
                failure = str(exc)
                break
            for i, mid in enumerate(ids):
                match = details.get(f'm{i}')
                if not match:
                    skipped['match unavailable'] += 1
                    continue
                actual = [p for p in match.get('players',[]) if eligible(match,p,hero_id,role,recent=not expanded and mid not in refs,allow_league=mid in refs)]
                if len(actual) != 1:
                    skipped['actual rank/position mismatch'] += 1
                    continue
                route = normalize_stratz(match,actual[0],versions)
                if not route or not route.skills:
                    skipped['purchase or skill history unavailable'] += 1
                    continue
                signature = (tuple(p.key for p in route.purchases), tuple(route.skills))
                if signature in fingerprints:
                    skipped['duplicate purchase and skill sequence'] += 1
                    continue
                fingerprints.add(signature)
                if mid in refs:
                    route.warnings.insert(0,'User-provided reference game, fetched independently from STRATZ.')
                if mid in history_ids:
                    route.warnings.insert(0,'Discovered from a high-ranked player history rather than the curated guide list.')
                routes.append(route)
            publish()
        if cancel.is_set():
            raise DataError('Search cancelled')
        status = (f'STRATZ · {len(routes)}/10 distinct builds in {time.monotonic()-started:.2f}s · '
                  f'{scanned} guide summaries checked ({reported} reported). ')
        if refs:
            status += f'{sum(r.match_ids[0] in refs for r in routes)}/{len(refs)} reference games loaded. '
        if expanded:
            status += 'Expanded to the bundled patch-date window; older examples are labeled. '
        if player_fallback_round:
            status += f'{history_players_checked} player histories checked ({history_matches_checked} match records). '
        if len(routes) < 10:
            status += ('Available guide list and sampled player histories exhausted. ' if exhausted and not pending and not older_pending and player_fallback_round >= 2 and not failure else 'Partial search; retry continues from cached pages. ')
        if skipped:
            status += 'Excluded: ' + '; '.join(f'{v} {k}' for k,v in sorted(skipped.items())) + '. '
        if failure:
            status += failure + ' '
        status += 'Ranked pubs: Immortal bracket; reference league games labeled separately. Numeric MMR unavailable. Check patch evidence.'
        if not routes and failure:
            raise DataError(status)
        return ranked(routes),status


    def load_match(self, mid, hero_id, role, cancel):
        jobs = DeadlineJobs(cancel)
        query = '{ constants {gameVersions {id name asOfDateTime}} ' + reference_query([mid], details=True) + '}'
        data = self.bounded(jobs, query)
        match = data.get('m0')
        if not match:
            raise DataError("This match is currently unavailable in STRATZ.")
        if not datetime.fromisoformat(PATCHES[-1]['date'].replace('Z','+00:00')).timestamp() <= match.get('startDateTime',0) <= time.time():
            raise DataError("This STRATZ game is outside the bundled patch-date window.")
        for player in match.get('players', []):
            if player.get('heroId') == hero_id and player.get('position') == f'POSITION_{role}':
                route = normalize_stratz(match, player, {v['id']:v['name'] for v in data['constants']['gameVersions']})
                if route:
                    return route
        raise DataError("STRATZ has no matching hero/position with usable purchase history for this game.")


def eligible(match, player, hero_id, role, recent=True, allow_league=False):
    cutoff = time.time() - 7 * 86400 if recent else datetime.fromisoformat(PATCHES[-1]['date'].replace('Z','+00:00')).timestamp()
    return (player.get('heroId') == hero_id and player.get('position') == f'POSITION_{role}'
            and match.get('rank') == 80 and (match.get('lobbyType') == 'RANKED' or
                (allow_league and match.get('lobbyType') == 'PRACTICE' and (match.get('leagueId') or 0) > 0))
            and cutoff <= match.get('startDateTime', 0) <= time.time()
            and not (0 < ((player.get('steamAccount') or {}).get('seasonRank') or 0) < 80))


def normalize_stratz(match, player, versions):
    purchases = [{'key': ITEM_KEYS.get(p['itemId'], f"item_id_{p['itemId']}"), 'time':p['time']}
                 for p in (player.get('stats') or {}).get('itemPurchases') or []
                 if isinstance(p.get('itemId'), int) and isinstance(p.get('time'), int)]
    abilities = sorted(player.get('abilities') or [], key=lambda a:a.get('time',0))
    account = player.get('steamAccount') or {}
    role = int(player['position'].split('_')[-1])
    source_patch = versions.get(match.get('gameVersionId'), f"version {match.get('gameVersionId')}")
    bundled_patch = PATCHES[-1]['name']
    major = re.match(r'^\d+\.\d+', source_patch)
    agrees = major and major[0] == bundled_patch
    evidence = ('Match bracket Immortal' if match.get('rank') == 80 else f"Match bracket {match.get('rank', 'unknown')}")
    if account.get('seasonLeaderboardRank'):
        evidence += f" · player leaderboard #{account['seasonLeaderboardRank']} (profile)"
    evidence += " · numeric MMR unavailable"
    if match.get('lobbyType') == 'PRACTICE' and match.get('leagueId'):
        evidence = f"League match #{match['leagueId']} · numeric MMR not applicable"
    explicit_slot = player.get('playerSlot')
    slot = (explicit_slot if type(explicit_slot) is int and explicit_slot >= 0 else 0) % 128 + (0 if player.get('isRadiant') else 128)
    route = normalize({'match_id':match['id'],'start_time':match.get('startDateTime',0),
                       'radiant_win':match.get('didRadiantWin'), 'patch':PATCHES[-1]['id'] if agrees else 0},
                      {'hero_id':player['heroId'],'player_slot':slot,'name':(account.get('proSteamAccount') or {}).get('name') or account.get('name'),
                       'position_est':role,'purchase_log':purchases,'ability_upgrades_arr':[a['abilityId'] for a in abilities],
                       'hero_variant':player.get('variant')}, evidence)
    if route:
        route.id = f"stratz:{match['id']}:{slot}"
        route.source = 'STRATZ'
        account_id = player.get('steamAccountId')
        route.account_id = account_id if type(account_id) is int and account_id > 0 else None
        is_radiant = player.get('isRadiant')
        route.player_slot = (explicit_slot if type(explicit_slot) is int and
                             ((is_radiant is True and 0 <= explicit_slot <= 4) or
                              (is_radiant is False and 128 <= explicit_slot <= 132)) else None)
        route.pro_player = bool((account.get('proSteamAccount') or {}).get('name'))
        route.tournament = match.get('lobbyType') == 'PRACTICE' and bool(match.get('leagueId'))
        route.patch_label = source_patch if agrees else f"unverified (STRATZ {source_patch}; bundled {bundled_patch})"
        route.warnings = ["Exact STRATZ purchase events and observed skill upgrade sequence. Skill level fields are ability ranks, not hero levels.",
                          "Starting purchase events are not a complete inventory snapshot; components or quantities may be missing from this source.",
                          "Position comes from STRATZ. Timings describe purchases, not courier delivery.",
                          "Guide discovery is STRATZ's curated subset, not D2PT's complete tracked match list."]
        if not agrees:
            route.warnings.insert(0, "PATCH UNVERIFIED: STRATZ's version metadata conflicts with the bundled patch metadata. This game is not certified current-patch.")
        age_days = int((time.time()-route.start_time)/86400)
        if age_days >= 7:
            route.warnings.insert(0, f"OLDER EXAMPLE: {age_days} days old. Included from the bundled patch-date window; source patch evidence still applies.")
    return route
