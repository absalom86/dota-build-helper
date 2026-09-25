from collections import Counter
from dataclasses import dataclass, field
import time


@dataclass
class Purchase:
    key: str
    time: int
    occurrence: int = 1
    low: int | None = None
    high: int | None = None
    samples: int = 1

    @property
    def identity(self):
        return (self.key, self.occurrence)


@dataclass
class Route:
    id: str
    hero_id: int
    role: int
    lane: int
    patch: int
    title: str
    purchases: list[Purchase]
    skills: list[str]
    match_ids: list[int]
    start_time: int
    evidence: str
    player: str
    facet: int | None = None
    demo: bool = False
    warnings: list[str] = field(default_factory=list)
    result: str = "Unknown"
    source: str = "OpenDota"
    patch_label: str = ""
    tournament: bool = False
    pro_player: bool = False
    average_mmr: int | None = None
    account_id: int | None = None
    player_slot: int | None = None


@dataclass
class Session:
    hero_id: int = 1
    match_id: str = ""
    selected: str | None = None
    explicit_choice: bool = False
    completed: set[tuple[str, int]] = field(default_factory=set)
    learned: Counter = field(default_factory=Counter)
    inventory: Counter = field(default_factory=Counter)
    clock: int | None = None
    last_gsi: float = 0
    paused: bool = False
    level: int = 1
    hero_at: float | None = None
    clock_at: float | None = None
    inventory_at: float | None = None
    charges_at: float | None = None
    skills_at: float | None = None
    inventory_slots: dict[str, str] = field(default_factory=dict)
    inventory_slot_charges: dict[str, int] = field(default_factory=dict)
    inventory_slot_secondary_charges: dict[str, int] = field(default_factory=dict)
    inventory_charges: Counter = field(default_factory=Counter)
    inventory_secondary_charges: Counter = field(default_factory=Counter)

    def reset(self, hero_id=None, match_id=""):
        fresh = Session(hero_id=self.hero_id if hero_id is None else hero_id, match_id=match_id)
        self.__dict__.update(fresh.__dict__)

    def choose(self, route_id, explicit=True):
        self.selected = route_id
        self.explicit_choice = explicit

    def accept_routes(self, routes):
        if self.selected in {r.id for r in routes}:
            return
        # The caller retains the old route if the player explicitly chose it.
        if not self.explicit_choice:
            self.selected = routes[0].id if routes else None

    def is_complete(self, purchase):
        return purchase.identity in self.completed

    def field_status(self, name, now=None, max_age=5):
        """Freshness belongs to the received field, not an unrelated GSI heartbeat."""
        if name not in ('hero', 'clock', 'inventory', 'charges', 'skills'):
            raise ValueError(f'Unknown telemetry field: {name}')
        received = getattr(self, name + '_at')
        if received is None:
            return 'missing'
        now = time.monotonic() if now is None else now
        return 'stale' if now - received > max_age else 'fresh'

    @staticmethod
    def _reported_count(data, aliases):
        for key in aliases:
            value = data.get(key)
            if type(value) is int and value >= 0:
                return value
        return None

    def _ingest_items(self, items, now):
        if not isinstance(items, dict):
            return
        slots, primary, secondary = {}, {}, {}
        for slot, value in items.items():
            if not isinstance(slot, str) or not slot.startswith(('slot', 'stash')):
                continue
            # A malformed slot is not evidence of an empty inventory.
            if not isinstance(value, dict) or not isinstance(value.get('name'), str):
                return
            name = value['name']
            if name == 'empty':
                continue
            if not name.startswith('item_') or name == 'item_':
                return
            slots[slot] = name.removeprefix('item_')
            charges = self._reported_count(value, ('charges', 'primary_charges', 'item_charges'))
            secondary_charges = self._reported_count(value, ('secondary_charges', 'charges2'))
            if charges is not None:
                primary[slot] = charges
            if secondary_charges is not None:
                secondary[slot] = secondary_charges
        # Nonempty, unrecognized/spectator-shaped data is not an empty local inventory.
        if items and not any(isinstance(key, str) and key.startswith(('slot', 'stash')) for key in items):
            return
        self.inventory_slots = slots
        self.inventory = Counter(slots.values())
        self.inventory_slot_charges = primary
        self.inventory_slot_secondary_charges = secondary

        def complete_totals(reported):
            # Never present a partial sum as the total for multiple stacks of one item.
            return Counter({key: sum(reported[slot] for slot, item in slots.items() if item == key)
                            for key in self.inventory
                            if all(slot in reported for slot, item in slots.items() if item == key)})

        self.inventory_charges = complete_totals(primary)
        self.inventory_secondary_charges = complete_totals(secondary)
        self.inventory_at = now
        self.charges_at = now if primary or secondary or not slots else None

    def _ingest_skills(self, abilities, now):
        if not isinstance(abilities, dict):
            return
        learned = Counter()
        valid = not abilities
        for key, value in abilities.items():
            if not isinstance(key, str) or not key.startswith('ability'):
                continue
            if (not isinstance(value, dict) or not isinstance(value.get('name'), str)
                    or type(value.get('level')) is not int or value['level'] < 0):
                return
            valid = True
            # Passive upgrades remain valid. Only explicitly hidden/innate entries are excluded.
            if any(value.get(flag) is True or value.get(flag) == 1 for flag in
                   ('hidden', 'ability_hidden', 'is_hidden', 'innate', 'ability_innate', 'is_innate')):
                continue
            if value['name'] and value['level']:
                learned[value['name']] = max(learned[value['name']], value['level'])
        if valid:
            self.learned = learned
            self.skills_at = now

    def next_skill(self, route):
        wanted = Counter(route.skills)
        # GSI also reports innates and granted skills, which are not route conflicts.
        extra = Counter({k: v for k, v in (self.learned - wanted).items() if k.startswith("special_bonus_")})
        if extra:
            return None, "Learned skills differ from this route; review the sequence."
        remaining = self.learned.copy()
        for skill in route.skills:
            if remaining[skill]:
                remaining[skill] -= 1
            else:
                return skill, "Upgrade sequence; exact hero levels unavailable"
        return None, "Recorded upgrade sequence complete"

    def ingest(self, payload):
        hero = payload.get("hero", {})
        player = payload.get("player", {})
        game_map = payload.get("map", {})
        # Spectator-shaped data is deliberately ignored.
        if (not isinstance(hero, dict) or type(hero.get("id")) is not int
                or not isinstance(player, dict) or not player.get("steamid")
                or not isinstance(game_map, dict)):
            return False
        if hero["id"] <= 0:
            return False
        match_id = str(game_map.get("matchid") or "")
        if match_id == "0":
            match_id = ""
        state = game_map.get("game_state", "")
        confirmed = state in {
            "DOTA_GAMERULES_STATE_STRATEGY_TIME", "DOTA_GAMERULES_STATE_PRE_GAME",
            "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS", "DOTA_GAMERULES_STATE_TEAM_SHOWCASE",
            "DOTA_GAMERULES_STATE_WAIT_FOR_MAP_TO_LOAD",
        }
        if not confirmed:
            return False
        if (match_id and self.match_id and self.match_id != match_id) or hero["id"] != self.hero_id:
            self.reset(hero["id"], match_id)
        # Local bot games may use match ID 0; a positive-to-pregame transition is a new session.
        incoming_clock = game_map.get('clock_time')
        clock_received = type(incoming_clock) is int
        if self.clock is not None and self.clock > 0 and clock_received and incoming_clock < 0:
            self.reset(hero["id"], match_id)
        self.match_id = match_id or self.match_id
        now = time.monotonic()
        self.last_gsi = self.hero_at = now
        if clock_received:
            self.clock = incoming_clock
            self.clock_at = now
        if type(game_map.get('paused')) is bool:
            self.paused = game_map['paused']
        if type(hero.get('level')) is int and hero['level'] >= 0:
            self.level = hero['level']
        self._ingest_items(payload.get('items'), now)
        self._ingest_skills(payload.get('abilities'), now)
        return True
