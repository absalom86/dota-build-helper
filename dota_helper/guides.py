"""Local Valve KeyValues v2 item guides, without publishing to the Workshop.

Shape checked against a guide saved by the installed Dota client and:
https://github.com/Darktex/d2pt-guides/blob/main/examples/sven_carry_example.build
"""
from collections import defaultdict
import hashlib
import os
from pathlib import Path
import re
import tempfile
import time

from . import starting_items
from .builds import overlay_sections
from .catalog import HEROES, ITEMS, ROLES, ability_name, clock_text, patch_name


def hero_key(route):
    return HEROES[str(route.hero_id)]['name'].removeprefix('npc_dota_hero_')


def filename(route):
    # Numeric suffix matches Dota's own file naming; stable per route/position.
    identity = f'{route.hero_id}:{route.role}:{route.id}'.encode('utf-8')
    # Stay within signed 32-bit timestamp range for older guide readers too.
    number = (int.from_bytes(hashlib.sha256(identity).digest()[:4], 'big') & 0x7FFFFFFF) or 1
    return f'{hero_key(route)}_{number}.build'


def title(route):
    hero = HEROES[str(route.hero_id)]['localized_name']
    source = (route.player if route.pro_player or route.tournament else
              f'{route.average_mmr:,} MMR' if route.average_mmr else 'Match')
    match = str(route.match_ids[0]) if route.match_ids else route.id
    return f'Helper · {hero} {ROLES.get(route.role, "")} · {"DEMO" if route.demo else source} · {match}'[:127]


def _quoted(value):
    # Escape all external strings, including player names and source notes.
    value = ''.join(c for c in str(value) if ord(c) >= 32 or c == '\n')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _block(name, pairs, depth=0):
    indent = '\t' * depth
    lines = [indent + _quoted(name), indent + '{']
    for key, value in pairs:
        if isinstance(value, list):
            lines.extend(_block(key, value, depth + 1))
        else:
            lines.append(indent + '\t' + _quoted(key) + '\t\t' + _quoted(value))
    lines.append(indent + '}')
    return lines


def build_text(route, *, now=None):
    initial = {key: count for key, count in starting_items.counts(route).items() if key in ITEMS}
    # A saved guide spans the entire match: early sections never expire here.
    sections = overlay_sections(route, second=None, supply_minutes=10)
    build_purchases = sorted(sections['items'] + sections['components'], key=lambda p: p.time)
    purchases = sorted(build_purchases + sections['supplies'], key=lambda p: p.time)
    categories = [('Starting items', [('item', 'item_' + key) for key, count in initial.items()
                                     for _ in range(count)])]
    if sections['supplies']:
        categories.append(('Laning supplies · 0–10 min',
                           [('item', 'item_' + p.key) for p in sections['supplies']]))
    for name, lower, upper in [('First 5 minutes', 0, 300), ('Early game · 5–15 min', 300, 900),
                               ('Mid game · 15–30 min', 900, 1800), ('Late game · 30+ min', 1800, float('inf'))]:
        values = [('item', 'item_' + p.key) for p in build_purchases if lower <= p.time < upper]
        if values:
            categories.append((name, values))
    if not initial and not purchases:
        raise ValueError('This route has no exportable items. Choose another build.')

    notes = defaultdict(list)
    quantities = {value['key']: value for value in starting_items.details(route)}
    for key, count in initial.items():
        notes[key].append(f'Starting buy: {count}.' + (' Estimated quantity; adjust if needed.'
                         if key == 'branches' and starting_items.estimated_branches(route) else ''))
        detail = quantities[key]
        notes[key].append(f"Quantity evidence: {detail['provenance']} ({detail['source']}). {detail['note']}")
    for p in purchases:
        timing = (f'{clock_text(p.low)}–{clock_text(p.high)}' if p.low is not None and p.high is not None
                  else clock_text(p.time))
        notes[p.key].append(f'Reference purchase: {timing}.')
    overview = [title(route), 'Local item guide exported by Dota Build Helper.',
                'Follow items left to right within each section. Hover an item for its recorded timing.',
                'Timings are reference points, not deadlines. Buying and switching guides is manual.',
                f'Source: {route.source}. Match IDs: ' + ', '.join(map(str, route.match_ids))]
    if route.demo:
        overview.append('SYNTHETIC OFFLINE DEMO - not match evidence or build advice.')
    if route.source == 'STRATZ' and starting_items.correction(route) is None:
        overview.append('Starting quantities may be incomplete in STRATZ. Edit starting buy in the helper if needed.')
    if starting_items.estimated_branches(route):
        overview.append('Starting Iron Branch x2 is estimated, not verified.')
    overview.extend(route.warnings)
    if route.skills:
        overview.append('Recorded skill/talent upgrade sequence (not hero levels):\n' +
                        ' → '.join(ability_name(key) for key in route.skills))
    overview.append('Skill level-up prompts are not exported: exact hero levels are unavailable. '
                    'Use the helper overlay for the next upgrade and talent picks.')
    patch = '' if route.demo else (route.patch_label or (patch_name(route.patch) if route.patch else ''))
    patch = patch if re.fullmatch(r'\d+\.\d+[a-z]?', patch) else ''
    pairs = [('Hero', hero_key(route)), ('Title', title(route)),
             ('Role', '#DOTA_HeroGuide_Role_Support' if route.role in (4, 5) else '#DOTA_HeroGuide_Role_Core'),
             ('GameplayVersion', patch), ('Overview', '\n'.join(overview)),
             ('GuideRevision', '1'), ('AssociatedWorkshopItemID', '0x0000000000000000'),
             ('OriginalCreatorID', '0x0000000000000000'), ('GuideFormatVersion', '2'),
             ('TimeUpdated', f'0x{int(time.time() if now is None else now):016X}'),
             ('TimePublished', '0x0000000000000000'),
             ('ItemBuild', [('Items', categories),
                            ('ItemTooltips', [('item_' + key, ' '.join(values)) for key, values in notes.items()])])]
    return '\n'.join(_block('guidedata', pairs)) + '\n'


def write_guide(route, path):
    path = Path(path)
    if path.suffix.lower() != '.build':
        raise ValueError('Save the guide with the .build extension.')
    content = build_text(route)
    path.parent.mkdir(parents=True, exist_ok=True)
    # An interrupted export must not damage an existing guide.
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                                     dir=path.parent, suffix='.tmp', delete=False) as stream:
        temp = Path(stream.name)
        try:
            stream.write(content)
            stream.close()
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
    return path


def fingerprint(route):
    """Stable across export times, but sensitive to quantities and guide contents."""
    return hashlib.sha256(build_text(route, now=0).encode('utf-8')).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export_file_matches(record):
    try:
        return bool(record.get('file_hash')) and file_hash(record['path']) == record['file_hash']
    except (OSError, KeyError):
        return False


def steam_roots():
    roots = []
    if os.name == 'nt':
        import winreg
        for hive, key, value in [(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                                  (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath')]:
            try:
                with winreg.OpenKey(hive, key) as registry:
                    roots.append(Path(winreg.QueryValueEx(registry, value)[0]))
            except OSError:
                pass
    roots.append(Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Steam')
    return list(dict.fromkeys(roots))


def guide_directories(roots=None):
    """Discover Dota accounts only; never pick one account on the user's behalf."""
    result = []
    for root in steam_roots() if roots is None else roots:
        try:
            accounts = sorted((Path(root) / 'userdata').iterdir())
        except OSError:
            continue
        for account in accounts:
            if account.name.isdecimal() and (account / '570').is_dir():
                path = account / '570' / 'remote' / 'guides'
                if path not in result:
                    result.append(path)
    return result
