"""Fresh role statistics for the draft before any enemy picks are entered."""
from collections import defaultdict
import time
from .catalog import HEROES
from .providers import DataError
from .stratz import Stratz


def role_meta(role,client=None):
    if role not in range(1,6):
        raise DataError('Choose position 1–5.')
    client=client or Stratz()
    query=('{heroStats{winDay(take:7,skip:0,positionIds:[POSITION_'+str(role)+
           '],bracketIds:[IMMORTAL],groupBy:HERO_ID){heroId day winCount matchCount}}}')
    data=client.query(query,ttl=1800)
    sums=defaultdict(lambda:[0,0])
    days=[]
    now=time.time()
    for row in (data.get('heroStats') or {}).get('winDay') or []:
        hero,day,games,wins=(row.get(k) for k in ('heroId','day','matchCount','winCount'))
        if (str(hero) not in HEROES or not all(type(v) is int for v in (day,games,wins))
                or games<=0 or not 0<=wins<=games or not now-8*86400<=day<=now):
            continue
        sums[hero][0]+=games
        sums[hero][1]+=wins
        days.append(day)
    if not days or max(days)<now-3*86400:
        raise DataError('Fresh role statistics unavailable; no current ranking shown.')
    return [dict(hero_id=h,games=g,wins=w,rate=w/g) for h,(g,w) in sums.items()], 'Recent 7 days · Immortal · patch unverified'


def leaders(rows,blocked=()):
    available=[r for r in rows if r['hero_id'] not in blocked]
    wins=sorted((r for r in available if r['games']>=100),key=lambda r:(r['rate'],r['games']),reverse=True)[:5]
    played=sorted(available,key=lambda r:(r['games'],r['rate']),reverse=True)[:5]
    return wins,played
