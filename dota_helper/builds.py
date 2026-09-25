"""Keep observed sequences together; never synthesize a slot-by-slot build."""
from collections import Counter, defaultdict
from statistics import median, quantiles

from .catalog import ABILITY_IDS, ITEMS, item_name
from .models import Purchase, Route


# These are useful milestones even if they later become part of an upgrade.
OVERLAY_MILESTONES = {
    'boots', 'magic_stick', 'magic_wand', 'bracer', 'wraith_band', 'null_talisman',
    'power_treads', 'phase_boots', 'arcane_boots', 'tranquil_boots', 'travel_boots',
    'urn_of_shadows', 'blink', 'gem', 'ghost', 'aghanims_shard', 'ultimate_scepter', 'ultimate_scepter_2',
}

LANING_SUPPLIES = frozenset({
    'tango', 'flask', 'clarity', 'enchanted_mango', 'faerie_fire',
    'infused_raindrop', 'blood_grenade',
})
OVERLAY_EXCLUDED = frozenset({
    'ward_observer', 'ward_sentry', 'ward_dispenser', 'tpscroll',
    'smoke_of_deceit', 'dust',
})


def starting_buy_text(route):
    """Count every recorded starting purchase, including same-second repeats."""
    from .starting_items import counts as starting_counts
    counts = starting_counts(route)
    from .starting_items import estimated_branches
    inferred=estimated_branches(route)
    return ', '.join(f'{item_name(key)} ×{count}'+(' (estimated)' if key=='branches' and inferred else '')
                     for key, count in counts.items())


def overlay_build_purchases(route, second=300):
    """Show completed build milestones, not shopping components or restocks."""
    def parts(key, seen=None):
        seen=set() if seen is None else seen
        if key in seen:
            return set()
        seen.add(key)
        direct={k for k in ITEMS.get(key,{}).get('components') or [] if k}
        return direct | {part for k in direct for part in parts(k,seen)}

    later_parts=set()
    result=[]
    for purchase in reversed(route.purchases):
        key=purchase.key
        item=ITEMS.get(key,{})
        keep=(purchase.time>=0 and bool(item) and not key.startswith('recipe_')
              and (key in OVERLAY_MILESTONES or
                   (item.get('qual') not in ('consumable','component')
                    and bool(item.get('created')) and key not in later_parts)))
        early = ((second is None or second < 300) and 0 <= purchase.time < 300
                 and bool(item) and not key.startswith('recipe_')
                 and key not in {'ward_observer', 'ward_sentry', 'tpscroll', 'smoke_of_deceit', 'dust'})
        if keep or early:
            result.append(purchase)
        later_parts.update(parts(key))
    return list(reversed(result))


def overlay_sections(route, second, supply_minutes=10):
    """Separate the full build from temporary early purchases without changing events.

    Initial purchases stay in the starting-buy section. Components are purchases
    from [0, 5 minutes); the listed laning supplies use [0, supply_minutes).
    A section expires when the clock reaches its upper bound. ``second=None``
    retains both sections, including for a permanent shop-guide export.
    """
    items = [p for p in overlay_build_purchases(route)
             if p.key not in OVERLAY_EXCLUDED and p.key not in LANING_SUPPLIES]
    major_events = {id(p) for p in items}
    components = []
    supplies = []
    supply_seconds = max(0, supply_minutes * 60)
    show_components = second is None or second < 300
    show_supplies = second is None or second < supply_seconds
    for purchase in sorted(route.purchases, key=lambda p: p.time):
        key = purchase.key
        if (purchase.time < 0 or key not in ITEMS or key in OVERLAY_EXCLUDED
                or key.startswith('recipe_') or id(purchase) in major_events):
            continue
        if key in LANING_SUPPLIES:
            if show_supplies and purchase.time < supply_seconds:
                supplies.append(purchase)
        elif show_components and purchase.time < 300:
            components.append(purchase)
    return {'items': sorted(items, key=lambda p: p.time),
            'components': components, 'supplies': supplies}


def normalize(match, player, evidence):
    log = player.get("purchase_log")
    if not isinstance(log, list) or not log:
        return None
    counts = Counter()
    purchases = []
    for event in sorted(log, key=lambda e: e.get("time", 0)):
        key, second = event.get("key"), event.get("time")
        if not isinstance(key, str) or not isinstance(second, (int, float)):
            continue
        # Keep recipes/components as separate observed events, never inferred completions.
        counts[key] += 1
        purchases.append(Purchase(key, int(second), counts[key]))
    major = [p for p in purchases if p.time >= 0 and ITEMS.get(p.key, {}).get("cost", 0) >= 1800
             and not p.key.startswith("recipe_")]
    if not purchases or not major:
        return None
    skills = [ABILITY_IDS.get(str(i), str(i)) for i in player.get("ability_upgrades_arr") or []]
    return Route(
        id=f"opendota:{match['match_id']}:{player['player_slot']}", hero_id=player["hero_id"],
        account_id=player.get('account_id'), player_slot=player.get('player_slot'),
        role=int(player.get("position_est") or 0), lane=int(player.get("lane_role") or 0),
        patch=match.get("patch", 0), title=" → ".join(item_name(p.key) for p in major[:3]),
        purchases=purchases, skills=skills, match_ids=[match["match_id"]],
        start_time=match.get("start_time", 0), evidence=evidence,
        player=player.get("name") or player.get("personaname") or "Unnamed player",
        average_mmr=(int(match['avg_mmr']) if type(match.get('avg_mmr')) in (int, float)
                     and 0 < match['avg_mmr'] < 30000 else None),
        facet=player.get("hero_variant"),
        result=("Won" if (player["player_slot"] < 128) == match["radiant_win"] else "Lost") if isinstance(match.get("radiant_win"), bool) else "Unknown",
        warnings=["Purchase-log timings; courier delivery is not measured.",
                  "Position is estimated by OpenDota. Skill entries are upgrade order, not exact hero levels."],
    )


def signature(route):
    return tuple(p.key for p in route.purchases if p.time >= 0
                 and ITEMS.get(p.key, {}).get("cost", 0) >= 1800
                 and not p.key.startswith("recipe_"))[:3]


def rank_routes(routes, role, lane, current_patch, now):
    # Unknown role is not a match. Never silently substitute a carry build for support.
    matching = [r for r in routes if r.role == role and (not lane or r.lane == lane)]
    recent = [r for r in matching if now - r.start_time <= 14 * 86400 and r.patch == current_patch]
    if not recent:
        recent = [r for r in matching if now - r.start_time <= 60 * 86400 and r.patch == current_patch]
    if not recent:
        recent = [r for r in matching if now - r.start_time <= 60 * 86400]
    groups = defaultdict(list)
    for route in recent:
        groups[(route.patch, route.facet, signature(route))].append(route)
    results = []
    for group in sorted(groups.values(), key=lambda g: (g[0].patch == current_patch, len(g), max(r.start_time for r in g)), reverse=True):
        representative = max(group, key=lambda r: r.start_time)
        representative.match_ids = list(dict.fromkeys(mid for r in group for mid in r.match_ids))
        representative.warnings.append("Route and skill sequence shown from the newest example; timing ranges use matching item-order samples.")
        evidence_types = set(r.evidence for r in group)
        if len(evidence_types) > 1:
            representative.warnings.append("Timing sample includes multiple evidence types: " + "; ".join(sorted(evidence_types)))
        if representative.patch != current_patch:
            representative.warnings.append("OLDER PATCH fallback: current-patch samples unavailable.")
        if now - representative.start_time > 14 * 86400:
            representative.warnings.append("Expanded to a 60-day sample window.")
        if len(group) < 3:
            representative.warnings.append("Small sample: example timings, not population benchmarks.")
        for purchase in representative.purchases:
            values = [p.time for r in group for p in r.purchases if p.identity == purchase.identity
                      and (p.time < 0) == (purchase.time < 0)]
            purchase.samples = len(values)
            if len(values) >= 3:
                purchase.time = int(median(values))
                qs = quantiles(values, n=4, method="inclusive")
                purchase.low, purchase.high = int(qs[0]), int(qs[2])
        results.append(representative)
        if len(results) == 3:
            break
    return results
