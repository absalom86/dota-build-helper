"""Curated Kez sequences, checked against Valve's live abilities on 2026-09-27.

These are a key reference, not cooldown tracking or measured popularity ranks.
See docs/USER_GUIDE.md for the firsthand guides and mechanics sources.
"""
from dataclasses import dataclass
from html import escape

HERO_ID = 145


@dataclass(frozen=True)
class Combo:
    stance: str
    keys: str
    purpose: str


STAGES = (
    ('EARLY GAME', (
        Combo('Sai', 'E → parry → D → Q', 'Parry trade'),
        Combo('Sai', 'Q → D → W → attack', 'Chase'),
    )),
    ('MID GAME', (
        Combo('Sai', 'R → mark → D → Q → W → attack', 'Marked burst'),
        Combo('Katana', 'Q → W → R', 'Fight / heal'),
    )),
    ("AFTER AGHANIM’S SCEPTER", (
        Combo('Katana', 'D → Q → D → Q → attack', 'Rush + Echo'),
        Combo('Katana', 'D → W → D → W → D → Q → D → Q', 'Silence engage'),
    )),
)

KEYS = (
    ('Q', 'Echo Slash', 'Falcon Rush'),
    ('W', 'Grappling Claw', 'Talon Toss'),
    ('E', 'Kazurai Katana', 'Shodo Sai / parry'),
    ('R', 'Raptor Dance', 'Raven’s Veil'),
)

DETAILS = (
    'Default QWER keys; D = Switch Discipline; attack = right-click the target. '
    'Start in the stated stance with the required abilities learned and ready.\n'
    'Parry trade: face the attacker, wait for a successful parry, then switch and Echo Slash.\n'
    'Marked burst: let Raven’s Veil mark reach the target before attacking.\n'
    'Fight / heal: start within Echo Slash range; Grapple after the first slash, '
    'then use Raptor Dance for its area damage and heal.\n'
    'Scepter combos: after each switch, cast the first spell within 3 seconds. '
    'This preserves its paired cooldown; casting a weapon spell refreshes Switch Discipline. '
    'Abilities already on cooldown are not refreshed.\n'
    'These are practice sequences, not live cooldown or target detection. '
    'No inputs are sent to Dota. Mechanics checked 27 September 2026.'
)


def reference_html(columns=2):
    if columns not in (1, 2):
        raise ValueError('Kez reference supports one or two columns')
    rows = ['<b style="color:#dcaa63">KEZ · COMBO KEYS</b>',
            '<span style="color:#97a6b7">Default keys · D swap · attack = right-click</span>']
    for heading, combos in STAGES:
        rows.append(f'<b style="color:#dcaa63">{escape(heading)}</b>')
        for combo in combos:
            rows.append(f'<b>Start in {escape(combo.stance)}</b>: '
                        f'<span style="color:#92cbff">{escape(combo.keys)}</span>')
    rows.append('<span style="color:#97a6b7">Requires learned, ready skills. '
                'Parry / mark = wait for success.<br>'
                'Scepter: first spell within 3s of D; each spell refreshes D.</span>')
    rows.append('<b>Katana / Sai</b><br>'
                'Q Echo / Rush · W Claw / Toss<br>'
                'E Impale / Parry · R Dance / Veil')
    return '<br>'.join(rows)
