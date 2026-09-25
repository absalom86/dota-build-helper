"""Invoker's ten orb recipes; these are the default, non-legacy hotkeys."""
from html import escape

HERO_ID = 74
SPELLS = (
    ('Cold Snap', 'QQQ'),
    ('Ghost Walk', 'QQW'),
    ('Ice Wall', 'QQE'),
    ('EMP', 'WWW'),
    ('Tornado', 'WWQ'),
    ('Alacrity', 'WWE'),
    ('Sun Strike', 'EEE'),
    ('Forge Spirit', 'EEQ'),
    ('Chaos Meteor', 'EEW'),
    ('Deafening Blast', 'QWE'),
)


def reference_html(columns=2):
    if columns not in (1, 2):
        raise ValueError('Invoker reference supports one or two columns')
    colors = {'Q': '#92cbff', 'W': '#d2a1ff', 'E': '#ffbd74'}
    cells = []
    rows = []
    for name, recipe in SPELLS:
        keys = ''.join(f'<span style="color:{colors[key]}">{key}</span>' for key in recipe)
        separator = '<br>' if columns == 2 else ' — '
        cells.append(f'<td width="{100 // columns}%" valign="top"><b>{keys}</b>{separator}{escape(name)}</td>')
    for start in range(0, len(cells), columns):
        rows.append('<tr>' + ''.join(cells[start:start + columns]) + '</tr>')
    return ('<b style="color:#dcaa63">INVOKER · SPELL KEYS</b><br>'
            '<span style="color:#97a6b7">Default: Q Quas · W Wex · E Exort</span>'
            '<table width="100%" cellspacing="0" cellpadding="1">' + ''.join(rows) + '</table>'
            '<span style="color:#97a6b7">Press recipe → R (Invoke) → D / F cast.<br>'
            'Choose a target when needed.</span>')
