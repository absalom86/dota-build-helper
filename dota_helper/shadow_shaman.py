"""Static Shadow Shaman tips; mechanics checked against Valve on 2026-09-29."""

HERO_ID = 27

DETAILS = (
    'Default QWER keys; Blink uses your item-slot binding. These are reference tips, '
    'not live health, mana or cooldown detection. No inputs are sent to Dota.\n'
    'Lane: use Q (Ether Shock) to secure a ranged creep your core cannot safely last-hit; '
    'aim to hit an enemy hero too. Let your core take the last hit when possible. '
    'Follow the selected build for skill upgrades; this does not require Q at level 1.\n'
    'Blink control: Blink into Hex and Shackles range, W (Hex), R (Mass Serpent Ward), '
    'then E (Shackles). Place wards in attack range of the target. '
    'Cast wards before channeling; do not move or issue another cast during Shackles. '
    'Check that all spells are ready and that you have mana for the whole sequence. '
    'Enemy allies can interrupt the channel.\n'
    'Low health: Shackles heals you during its channel, including on enemy or neutral creeps. '
    'Use a healthy creep that will survive the channel when safe from enemy interruption '
    'and attacks by the rest of the camp. Avoid taking your core\'s last hits. '
    'It costs substantial mana; preserve enough for a save or kill attempt.\n'
    'Use Tango or an available Stick/Wand before channeling, not during it. '
    'Eating a tree planted with Iron Branch doubles Tango regeneration duration, '
    'but consumes the branch. A Healing Salve is another option from safety. '
    'These item tips apply only if you have the item; they do not change your build.'
)


def reference_html():
    return '<br>'.join((
        '<b style="color:#dcaa63">SHADOW SHAMAN · QUICK TIPS</b>',
        '<b style="color:#dcaa63">LANE</b>',
        '<b>Q · Ether Shock</b><br>Secure ranged creep if core can’t. Hit hero too.',
        '<b style="color:#dcaa63">BLINK CONTROL</b>',
        '<b style="color:#92cbff">Blink → W → R → E</b>',
        'W Hex → R Mass Serpent Ward → E Shackles',
        'Get in range. Let Shackles channel.',
        '<b style="color:#dcaa63">LOW HEALTH</b>',
        '<b>E heals:</b> channel on a healthy creep when safe.',
        'Tango / Wand first, then E.',
        'Branch tree + Tango = longer regen.',
        'Salve from safety. Preserve mana.',
        '<span style="color:#97a6b7">Default keys · Blink = item slot<br>Reference · check spell readiness</span>',
    ))
