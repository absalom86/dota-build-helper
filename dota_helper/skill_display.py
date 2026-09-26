"""Readable observed upgrades, without inventing hero levels or keyboard binds."""
from html import escape

from .catalog import ability_name


def overlay_skill_text(session, route):
    skill, warning = session.next_skill(route)
    if not skill:
        return warning
    pending = [(i, s) for i, (s, done) in enumerate(session.skill_progress(route), 1) if not done]
    lines = ['NEXT SKILL', ability_name(skill)]
    if len(pending) > 1:
        lines.append('Then: ' + ' → '.join(ability_name(s) for _, s in pending[1:3]))
    return '\n'.join(lines)


def skill_order_html(session, route):
    progress = session.skill_progress(route)
    next_skill, warning = session.next_skill(route)
    next_index = next((i for i, (_, done) in enumerate(progress) if not done), None) if next_skill else None
    heading = (f'<b style="color:#ffe0a3">NEXT SKILL · {escape(ability_name(next_skill))}</b>'
               if next_skill else escape(warning))
    rows = []
    for index, (skill, done) in enumerate(progress):
        name = escape(ability_name(skill))
        if done:
            text = f'<span style="color:#97a6b7">✓ {name}</span>'
        elif index == next_index:
            text = f'<b style="color:#ffe0a3">▶ {name} · next</b>'
        else:
            text = name
        rows.append(f'<li style="margin:5px 0">{text}</li>')
    talents = list(dict.fromkeys(s for s, _ in progress
                                if s.startswith('special_bonus_') and s != 'special_bonus_attributes'))
    talent_html = ('<p><b>TALENT PICKS · recorded order</b></p><ul>' +
                   ''.join(f'<li>{escape(ability_name(s))}</li>' for s in talents) + '</ul>'
                   if talents else '<p>Talent picks not recorded.</p>')
    return (f'<div style="font-size:15px">{heading}</div>'
            '<p><b>SKILL ORDER</b> · upgrade sequence, not hero levels</p>' +
            ('<ol>' + ''.join(rows) + '</ol>' if rows else '<p>Skill history unavailable.</p>') + talent_html)
