"""Tournament-only recommendations; never fill missing slots with ranked pubs."""
from datetime import datetime
from dataclasses import asdict
import json
import uuid
import threading
import time

from .catalog import HEROES, PATCHES
from .fast_lookup import DeadlineJobs
from .providers import DataError, OpenDota
from .models import Route, Purchase
from .ranking import patch_group, ranked, route_key
from .stratz import Stratz, SUMMARY, PLAYER, references, reference_query, normalize_stratz

TIERS = ('PROFESSIONAL','MINOR','MAJOR','INTERNATIONAL','DPC_QUALIFIER',
         'DPC_LEAGUE_QUALIFIER','DPC_LEAGUE','DPC_LEAGUE_FINALS')


def tournament_index(client, hero, since, cancel):
    """Discover actual league matches even when STRATZ has no league object."""
    index=OpenDota(client.cache_dir)
    index.cancel=cancel
    index.force_refresh=client.refresh
    base=("SELECT m.match_id,m.start_time,m.leagueid,l.name,l.tier,pm.account_id "
         "FROM matches m JOIN player_matches pm USING(match_id) "
         "JOIN leagues l ON l.leagueid=m.leagueid "
         f"WHERE pm.hero_id={int(hero)} AND m.start_time>={int(since)} "
         "AND m.leagueid IN (SELECT leagueid FROM leagues WHERE tier='{tier}') "
         "ORDER BY m.start_time DESC LIMIT 30")
    sql=base.format(tier='premium')
    data=index.get('explorer',{'sql':sql},ttl=1800)
    if not isinstance(data,dict) or data.get('err') or not isinstance(data.get('rows'),list):
        raise DataError('Tournament match index unavailable')
    return sorted((r for r in data['rows'] if r.get('tier') in ('premium','professional')),
                  key=lambda r:(r['tier']=='premium',r['start_time']),reverse=True)


def tournament_player(match, player, hero, role, since):
    return (match.get('lobbyType') == 'PRACTICE' and (match.get('leagueId') or 0)>0
            and since <= match.get('startDateTime',0) <= time.time()
            and player.get('heroId')==hero and player.get('position')==f'POSITION_{role}'
            and bool(player.get('steamAccountId')))


def tournament_routes(client, hero, role, progress=lambda _:None, cancel=None, on_update=None, reference_ids=None, deadline=None):
    if str(hero) not in HEROES or role not in range(1,6):
        raise DataError('Choose a valid hero and position.')
    cancel=cancel or threading.Event()
    jobs=DeadlineJobs(cancel)
    if deadline is not None:
        jobs.deadline=min(jobs.deadline,deadline)
    start=time.monotonic()
    since=int(datetime.fromisoformat(PATCHES[-1]['date'].replace('Z','+00:00')).timestamp())
    refs=references(hero) if reference_ids is None else reference_ids[:10]
    snapshot=client.cache_dir/f'tournaments-v1-{hero}-{role}.json'
    fallback=[]
    try:
        saved=json.loads(snapshot.read_text(encoding='utf-8'))
        for record in saved['routes']:
            record['purchases']=[Purchase(**p) for p in record['purchases']]
            route=Route(**record)
            if route.tournament and route.hero_id==hero and route.role==role and since<=route.start_time<=time.time():
                fallback.append(route)
        fallback = ranked(fallback)
        if fallback and on_update:
            on_update((fallback,'Cached tournament builds ready · refreshing tournament index…'))
    except (OSError,ValueError,KeyError,TypeError):
        fallback=[]
    index_rows=[]
    index_failure=''
    progress('Finding premier tournament matches in the bundled patch-date window…')
    if jobs.submit('tournament-index',lambda:tournament_index(client,hero,since,cancel)):
        event=jobs.next()
        if event:
            _,index_rows,error=event
            if error:
                index_rows=[]
                index_failure=str(error)
    query=('{constants {gameVersions{id name}} '+reference_query(refs)
           +' leagues(request:{tiers:['+','.join(TIERS)+'],take:20}){id name tier '
           +f'matches(request:{{heroIds:[{hero}],positionIds:[POSITION_{role}],take:10,skip:0,startDateTime:{since}}})'
           +'{'+SUMMARY+' players{'+PLAYER+'}}}}')
    # The broader index supplies IDs; STRATZ still validates role, league and build data.
    if index_rows:
        query='{constants {gameVersions{id name}}}'
    progress('Loading exact tournament builds · ranked pubs excluded…')
    try:
        data=client.bounded(jobs,query)
    except DataError as exc:
        if cancel.is_set() or not fallback:
            raise
        return fallback,'Cached tournament builds · refresh unavailable: '+str(exc)
    versions={v['id']:v['name'] for v in data.get('constants',{}).get('gameVersions',[])}
    candidates=[]
    for row in index_rows:
        if row.get('tier') not in ('premium','professional') or not row.get('account_id'):
            continue
        name=('PREMIER · ' if row['tier']=='premium' else '')+(row.get('name') or f"League {row['leagueid']}")
        candidates.append(({'id':row['match_id'],'leagueId':row['leagueid']},
                           {'steamAccountId':row['account_id']},name))
    for i,mid in enumerate(refs):
        match=data.get(f'm{i}')
        if match:
            for player in match.get('players') or []:
                if tournament_player(match,player,hero,role,since):
                    candidates.append((match,player,'Comparison tournament reference'))
    discovered=[]
    for league in data.get('leagues') or []:
        if league.get('tier') not in TIERS:
            continue
        for match in league.get('matches') or []:
            if match.get('leagueId') != league.get('id'):
                continue
            for player in match.get('players') or []:
                if tournament_player(match,player,hero,role,since):
                    discovered.append((match,player,league.get('name') or f"League {league['id']}"))
    candidates+=sorted(discovered,key=lambda x:x[0]['startDateTime'],reverse=True)
    routes=[]
    attempted=set()
    signatures={}
    rejected=0
    failure=''
    while candidates and sum(patch_group(route) == 2 for route in routes)<10 and time.monotonic()<jobs.deadline and not cancel.is_set():
        selected={}
        slots = 10 - sum(patch_group(route) == 2 for route in routes)
        while candidates and len(selected)<slots:
            match,player,name=candidates.pop(0)
            if match['id'] not in attempted:
                selected[match['id']]=(player,name,match['leagueId'])
                attempted.add(match['id'])
        if not selected:
            continue
        try:
            details=client.bounded(jobs,'{'+reference_query(list(selected),True,
                {mid:p[0]['steamAccountId'] for mid,p in selected.items()})+'}')
        except DataError as exc:
            failure=str(exc)
            break
        for i,(mid,(account,name,league_id)) in enumerate(selected.items()):
            match=details.get(f'm{i}')
            players=[p for p in (match or {}).get('players') or []
                     if tournament_player(match,p,hero,role,since) and p.get('steamAccountId')==account['steamAccountId']]
            route=normalize_stratz(match,players[0],versions) if len(players)==1 and match.get('leagueId')==league_id else None
            if not route or not route.skills:
                rejected+=1
                continue
            route.evidence=f'TOURNAMENT · {name} · no pub MMR'
            route.warnings.insert(0,'Tournament-only source. '+name+'. Ranked pub games are never substituted.')
            signature=(tuple(p.key for p in route.purchases),tuple(route.skills))
            previous = signatures.get(signature)
            if previous is not None and route_key(previous) >= route_key(route):
                rejected+=1
                continue
            signatures[signature] = route
        routes = ranked(signatures.values())
        if routes and on_update:
            on_update((list(routes),f'{len(routes)} tournament builds ready · ranked pubs excluded'))
    if cancel.is_set():
        raise DataError('Search cancelled')
    if candidates and sum(patch_group(route) == 2 for route in routes)<10 and not failure:
        failure='Search deadline reached; retry uses cached responses.'
    status=f'{len(routes)} tournament builds in {time.monotonic()-start:.2f}s · ranked pubs excluded · {rejected} unavailable/duplicate builds. '
    if not routes:
        status+='No usable tournament games in the available index/reference sample. '
    status+=failure+' Patch evidence may be unverified; tournament coverage is incomplete.'
    if index_rows:
        status+=' OpenDota match index + STRATZ builds; bundled patch-date window. Patch confidence first, then premier events and newest games.'
    elif index_failure:
        status+=' Limited STRATZ directory fallback: '+index_failure
    if routes:
        temp=snapshot.with_suffix(f'.{uuid.uuid4().hex}.tmp')
        temp.write_text(json.dumps({'at':time.time(),'routes':[asdict(r) for r in routes]}),encoding='utf-8')
        temp.replace(snapshot)
    return routes,status
