"""Conservative item recipes in purchase units, never ability/stack charges.

The catalog omits some paid recipe scrolls and contains older or incomplete
recipes. A decomposition is usable only when every component is known and its
cost, including a paid scroll, exactly matches the completed item's cost.
"""
from collections import Counter
from collections.abc import Mapping

from .catalog import ITEMS


# The catalog records only the strength variant; the other two attributes can
# also build Treads, so a completed pair cannot prove which part was purchased.
_ALTERNATIVE_COMPONENTS = frozenset({'power_treads'})


def _cost(key):
    value = ITEMS.get(key, {}).get('cost')
    return value if type(value) is int and value > 0 else None


def _direct_components(key):
    item = ITEMS.get(key, {})
    parts = item.get('components')
    cost = _cost(key)
    if (not cost or key in _ALTERNATIVE_COMPONENTS
            or 'consumable' in str(item.get('qual', '')).split(';')
            or not isinstance(parts, (list, tuple)) or not parts
            or any(not isinstance(part, str) or not _cost(part) for part in parts)):
        return Counter()
    counts = Counter(parts)
    recipe = f'recipe_{key}'
    recipe_cost = _cost(recipe)
    if recipe_cost and recipe not in counts:
        counts[recipe] = 1
    if sum(_cost(part) * count for part, count in counts.items()) != cost:
        return Counter()
    return counts


def component_counts(key):
    """Return safe direct components, retaining duplicate parts and paid scrolls.

    An empty Counter means unknown/unsafe decomposition or an ordinary leaf.
    Cyclic catalog entries are rejected, rather than producing partial evidence.
    """
    if not isinstance(key, str):
        return Counter()
    counts = _direct_components(key)

    def acyclic(item, ancestors):
        if item in ancestors:
            return False
        return all(acyclic(part, ancestors | {item})
                   for part in _direct_components(item))

    return counts if counts and acyclic(key, set()) else Counter()


def _positive_counts(counts):
    return Counter({key: count for key, count in counts.items()
                    if isinstance(key, str) and type(count) is int and count > 0})


def expanded_counts(counts: Mapping[str, int], include_roots=False):
    """Expand inventory/purchase counts into the known leaf purchase units.

    With ``include_roots``, include each composite and its intermediate parts as
    well. Those overlapping counts are coverage evidence, not additional items.
    Unknown or unsafe recipes remain intact. Consumable quantities stay packs or
    slots as supplied; the catalog's ``charges`` field is never a multiplier.
    """
    result = Counter()

    def add(key, count):
        parts = component_counts(key)
        if include_roots or not parts:
            result[key] += count
        for part, quantity in parts.items():
            add(part, count * quantity)

    for key, count in _positive_counts(counts).items():
        add(key, count)
    return result


def assemble_counts(counts: Mapping[str, int]):
    """Combine complete, unambiguous recipes in an inventory count snapshot.

    This is not a purchase-log deduplicator: a completed item plus its parts
    represents additional units. Every required component, including duplicate
    branches and paid recipes, must be present. Competing recipes that require
    the same scarce parts are left unchanged instead of choosing a build.
    """
    inventory = _positive_counts(counts)
    recipes = {key: parts for key in sorted(ITEMS)
               if (parts := component_counts(key))}
    while True:
        possible = {key: parts for key, parts in recipes.items()
                    if all(inventory[part] >= count for part, count in parts.items())}
        required = Counter()
        for parts in possible.values():
            required.update(parts)
        contested = {part for part, count in required.items() if count > inventory[part]}
        choice = next(((key, parts) for key, parts in possible.items()
                       if not contested.intersection(parts)), None)
        if choice is None:
            return +inventory
        key, parts = choice
        inventory.subtract(parts)
        inventory[key] += 1
