"""One bounded recommendation list, patch evidence before source preferences."""
import threading
import time
from .providers import DataError
from .tournaments import tournament_routes
from .ranking import RANKING_DESCRIPTION, patch_group, ranked


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
    # A full list of unknown/older tournament patches must not block current pubs.
    if sum(patch_group(route) == 2 for route in routes)<10 and time.monotonic()<deadline and not cancel.is_set():
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
            'Newest games within each preference; team strength is not ranked. ')
    # Keep source failures explicit without confusing the unified list with source-only labels.
    if any(any(marker in s.lower() for marker in ('refresh unavailable','directory fallback','request limit','deadline','http','timed out')) for s in issues):
        status+='Some discovery was unavailable or incomplete. '+' '.join(issues)
    return routes,status
