"""Dated role statistics for the draft before any enemy picks are entered."""
from collections import defaultdict
from datetime import datetime, timezone
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
    valid=[]
    now=time.time()
    for row in (data.get('heroStats') or {}).get('winDay') or []:
        hero,day,games,wins=(row.get(k) for k in ('heroId','day','matchCount','winCount'))
        if (str(hero) not in HEROES or not all(type(v) is int for v in (day,games,wins))
                or games<=0 or not 0<=wins<=games or not 0<=day<=now):
            continue
        valid.append((hero,day,games,wins))
    if not valid:
        raise DataError('Role statistics unavailable; the source returned no usable games.')
    newest=max(day for _,day,_,_ in valid)
    age=int((now-newest)//86400)
    if now-newest>30*86400:
        date=datetime.fromtimestamp(newest,timezone.utc).strftime('%d %b %Y')
        raise DataError(f'Role statistics last updated {date} UTC (over 30 days old). Click Refresh role rankings to retry.')
    sums=defaultdict(lambda:[0,0])
    days=[]
    for hero,day,games,wins in valid:
        # Providers can lag behind today. Use their latest seven calendar days,
        # retaining the actual dates instead of silently labelling them current.
        if day<newest-6*86400:
            continue
        sums[hero][0]+=games
        sums[hero][1]+=wins
        days.append(day)
    first=datetime.fromtimestamp(min(days),timezone.utc).strftime('%d %b')
    last=datetime.fromtimestamp(newest,timezone.utc).strftime('%d %b %Y')
    status=f'{first}–{last} UTC · Immortal · patch unverified'
    if now-newest>3*86400:
        status=f'DELAYED DATA · {age} days behind · '+status
    return [dict(hero_id=h,games=g,wins=w,rate=w/g) for h,(g,w) in sums.items()], status


def leaders(rows,blocked=()):
    available=[r for r in rows if r['hero_id'] not in blocked]
    wins=sorted((r for r in available if r['games']>=100),key=lambda r:(r['rate'],r['games']),reverse=True)[:5]
    played=sorted(available,key=lambda r:(r['games'],r['rate']),reverse=True)[:5]
    return wins,played
