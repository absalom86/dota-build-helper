"""A compact visual upgrade sequence; sequence indices are never hero levels."""
from PySide6.QtCore import QEvent, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QLabel, QToolTip

from .catalog import ability_name
from .talents import talent_branches


class SkillStrip(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.icons = None
        self.progress = None
        self.next_index = None
        self.warning = ''
        self.hitboxes = []
        self.hero_id = None

    def set_icon_cache(self, icons):
        self.icons = icons
        icons.changed.connect(self.update)

    def setText(self, text):
        self.progress = None
        super().setText(text)
        self.updateGeometry()

    def set_route(self, session, route):
        from .skill_display import overlay_skill_text
        progress = session.skill_progress(route)
        next_skill, warning = session.next_skill(route)
        next_index = next((i for i, (_, done) in enumerate(progress) if not done), None) if next_skill else None
        if (progress, next_index, warning, route.hero_id) == (self.progress, self.next_index, self.warning, self.hero_id):
            return
        self.hero_id = route.hero_id
        self.progress, self.next_index, self.warning = progress, next_index, warning
        # Text is retained for accessibility, offline diagnostics and missing histories.
        super().setText(overlay_skill_text(session, route))
        self.setAccessibleName('Recorded skill upgrade sequence')
        self.setAccessibleDescription('\n'.join(f'{i+1}. {ability_name(key)}' for i, (key, _) in enumerate(progress)))
        if self.icons:
            for key, _ in progress:
                self.icons.get(key)
        self.updateGeometry()
        self.update()

    def window_indices(self, width):
        capacity = max(1, min(10, (width - 8 - 38 + 2) // 22))
        index = self.next_index if self.next_index is not None else max(0, len(self.progress or [])-1)
        start = (index // capacity) * capacity
        return start, min(start + capacity, len(self.progress or []))

    def heightForWidth(self, width):
        if self.progress is None:
            return super().heightForWidth(width)
        return 62 if self.progress and self.next_index is None and 'differ' in self.warning else 48

    def sizeHint(self):
        return QSize(240, self.heightForWidth(240)) if self.progress is not None else super().sizeHint()

    @staticmethod
    def _tree(painter, rect, branches=()):
        painter.save()
        painter.translate(rect.left(), rect.top())
        painter.scale(rect.width()/40, rect.height()/40)
        gradient = QRadialGradient(17, 12, 30)
        gradient.setColorAt(0, QColor('#303841'))
        gradient.setColorAt(1, QColor('#171e24'))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor('#47505a'), 1))
        painter.drawEllipse(QRectF(1, 1, 38, 38))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('#68727b'), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(20, 8, 20, 36)
        levels = {25:(12,8,7), 20:(20,7,15), 15:(27,8,24), 10:(33,11,31)}
        if branches:
            painter.setPen(QPen(QColor('#e8b36d'), 2.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(20, min(levels[level][0] for level, _ in branches), 20, 36)
        for level, (y, end_x, end_y) in levels.items():
            for side in ('left', 'right'):
                x = end_x if side == 'left' else 40-end_x
                selected = (level, side) in branches
                painter.setPen(QPen(QColor('#efbd78' if selected else '#59636d'), 2.4 if selected else 1.5,
                                    Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                path = QPainterPath()
                path.moveTo(20, y)
                path.quadTo(x, y, x, end_y)
                painter.drawPath(path)
        painter.restore()

    def paintEvent(self, event):
        if self.progress is None:
            return super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor('#182630'))
        font = self.font()
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(QColor('#dcaa63'))
        self.hitboxes = []
        if not self.progress:
            painter.drawText(self.rect().adjusted(5, 0, -5, 0), Qt.AlignmentFlag.AlignVCenter,
                             'Skill order not recorded')
            painter.end()
            return
        start, end = self.window_indices(self.width())
        painter.drawText(5, 13, f'SKILLS · upgrades {start+1}–{end}/{len(self.progress)}')
        for column, index in enumerate(range(start, end)):
            key, done = self.progress[index]
            rect = QRect(4+column*22, 20, 20, 20)
            painter.fillRect(rect, QColor('#344856'))
            pixmap = self.icons.get(key) if self.icons else None
            if pixmap is not None and not pixmap.isNull():
                painter.drawPixmap(rect, pixmap)
            elif key.startswith('special_bonus_') and key != 'special_bonus_attributes':
                self._tree(painter, rect, talent_branches(self.hero_id, [key])[0])
            else:
                painter.setPen(QColor('#f1f5f7'))
                name = ('?' if key in ('0', 'dota_base_ability') else '+' if key == 'special_bonus_attributes'
                        else ''.join(word[0] for word in ability_name(key).split())[:2])
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, name)
            if done:
                painter.fillRect(rect, QColor(10, 20, 30, 100))
                painter.setPen(QColor('#9ae0b0'))
                painter.drawText(rect.adjusted(1, 0, -1, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom, '✓')
            if index == self.next_index:
                painter.setPen(QPen(QColor('#ffd078'), 2))
                painter.drawRect(rect.adjusted(-1, -1, 1, 1))
            status = 'learned' if done else 'next upgrade' if index == self.next_index else 'pending'
            self.hitboxes.append((rect, f'Upgrade {index+1}: {ability_name(key)} · {status}\n'
                                   'Recorded sequence, not hero level.'))
        talents = list(dict.fromkeys(key for key, _ in self.progress
                                   if key.startswith('special_bonus_') and key != 'special_bonus_attributes'))
        tree = QRect(self.width()-36, 15, 32, 32)
        branches, unmapped = talent_branches(self.hero_id, talents)
        self._tree(painter, tree, branches)
        if not talents or unmapped:
            painter.setPen(QColor('#ffe0a3'))
            painter.drawText(tree, Qt.AlignmentFlag.AlignCenter, '?')
        self.hitboxes.append((tree, 'Recorded talent picks\n' + ('\n'.join(ability_name(key) for key in talents)
                              if talents else 'Not available from this source') +
                              '\nGold = first recorded pick per tier; grey = unselected or unknown.\nCurrent hero tree: bottom 10, then 15, 20, top 25.' +
                              ('\nSome historical talents are not on the current tree; branch sides are not inferred.' if unmapped else '')))
        if self.next_index is None and 'differ' in self.warning:
            painter.setPen(QColor('#ffe0a3'))
            painter.drawText(5, 57, 'Skills differ · review build')
        painter.end()

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip and self.progress is not None:
            for rect, text in self.hitboxes:
                if rect.contains(event.pos()):
                    QToolTip.showText(event.globalPos(), text, self)
                    return True
            QToolTip.hideText()
            return True
        return super().event(event)
