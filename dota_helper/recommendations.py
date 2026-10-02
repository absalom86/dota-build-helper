"""Bounded discovery with all usable games retained, patch evidence first."""
import threading
import time
from .providers import DataError
from .tournaments import tournament_routes
from .ranking import RANKING_DESCRIPTION, ranked


def recommended_routes(client,hero,role,progress=lambda _:None,cancel=None,on_update=None):
    cancel=cancel or threading.Event()
    started=time.monotonic()
    deadline=started+8
    routes=[]
    issues=[]
    def publish(result):
        nonlocal routes
        routes=ranked(routes+result[0])
        if routes and on_update:
            on_update((routes,f'{len(routes)} builds ready · {RANKING_DESCRIPTION}'))
    try:
        result=tournament_routes(client,hero,role,progress,cancel,publish,deadline=min(deadline,started+5))
        publish(result)
        issues.append(result[1])
    except DataError as exc:
        issues.append(str(exc))
    # Retain tournament options and use the remaining shared budget for pubs.
    if time.monotonic()<deadline and not cancel.is_set():
        try:
            result=client.routes(hero,role,progress,cancel,publish,reference_ids=[],deadline=deadline)
            publish(result)
            issues.append(result[1])
        except DataError as exc:
            issues.append(str(exc))
    if cancel.is_set():
        raise DataError('Search cancelled')
    if not routes:
        raise DataError('No usable builds. '+' '.join(issues))
    status=(f'{len(routes)} builds in {time.monotonic()-started:.2f}s · {RANKING_DESCRIPTION}. '
            'Equal ratings use newest first; team strength is not ranked. ')
    # Keep source failures explicit without confusing the unified list with source-only labels.
    if any(any(marker in s.lower() for marker in ('refresh unavailable','directory fallback','request limit','deadline','http','timed out','partial search')) for s in issues):
        status+='Some discovery was unavailable or incomplete. '+' '.join(issues)
    return routes,status
