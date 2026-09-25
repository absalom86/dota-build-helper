"""A content-sized, click-through overlay with no hidden scrollable sections."""
from html import escape
import time

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QLabel, QSizeGrip, QWidget

from . import invoker
from .catalog import clock_text, item_name, patch_name
from .ranking import patch_group


def route_identity(route, now=None):
    if route.demo:
        return 'OFFLINE DEMO · synthetic'
    source = (f'PRO · {route.player}' if route.tournament or route.pro_player else
              f'{route.average_mmr:,} MMR' if route.average_mmr else 'Ranked pub · MMR unknown')
    source = ' '.join(source.split())
    if len(source) > 55:
        source = source[:52] + '…'
    age = max(0, int(((time.time() if now is None else now)-route.start_time)/86400))
    date = f' · {age}d ago' if route.start_time and age else ' · today' if route.start_time else ''
    patch = route.patch_label or (patch_name(route.patch) if route.patch else '')
    if not patch or patch_group(route) == 1:
        patch = 'Patch unverified'
    else:
        patch = 'Patch ' + patch
        if patch_group(route) == 0:
            patch += ' · older'
    return source + date + '\n' + patch


def purchase_summary(purchases):
    """Group quantities without pretending separate purchases happened together."""
    groups = {}
    for purchase in purchases:
        groups.setdefault(purchase.key, []).append(purchase)
    lines = []
    for key, values in groups.items():
        times = sorted(p.time for p in values)
        timing = clock_text(times[0])
        if times[-1] != times[0]:
            timing += '–' + clock_text(times[-1])
        count = f' ×{len(values)}' if len(values) > 1 else ''
        lines.append(f'{timing} {item_name(key)}{count}')
    return ' · '.join(lines)


class Overlay(QWidget):
    def __init__(self, settings, stylesheet=''):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(stylesheet)
        screen = QApplication.screenAt(QPoint(settings.get('overlay_x', 18), settings.get('overlay_y', 18))) or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        if settings.get('overlay_layout_version') != 3:
            settings.update(overlay_w=270, overlay_h=600, overlay_x=bounds.right()-281,
                            overlay_y=bounds.top()+160, overlay_layout_version=3)
        self.preferred_width = max(270, min(600, settings.get('overlay_w', 270)))
        self.font_size = max(11, min(16, settings.get('overlay_font', 13)))
        self._fitting = True
        self.resize(self.preferred_width, settings.get('overlay_h', 600))
        self.move(settings['overlay_x'], settings['overlay_y'])
        self.origin = None
        self.locked = False
        self.invoker_active = False
        self.fit_ok = True
        self.fit_message = ''
        self.item_lines = None
        self._fit_key = None

        def label(text='', muted=False):
            result = QLabel(text, self)
            result.setWordWrap(True)
            result.setTextFormat(Qt.TextFormat.PlainText)
            result.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            if muted:
                result.setObjectName('muted')
            return result

        self.title = label('BUILD COMPANION')
        self.hero = label('Choose your hero')
        self.route_label = label('', True)
        self.clock = label('--:-- · Waiting for game clock', True)
        self.initial_buy = label()
        self.components = label()
        self.supplies = label()
        self.items = label('Choose a hero and find a build route.')
        self.skill = label()
        self.talents = label()
        self.invoker_spells = label()
        self.invoker_spells.setTextFormat(Qt.TextFormat.RichText)
        self.note = label('', True)
        self.lane_timers = label('', True)
        self.labels = [self.title, self.hero, self.route_label, self.clock, self.initial_buy,
                       self.components, self.supplies, self.items, self.skill, self.talents,
                       self.invoker_spells, self.note, self.lane_timers]
        for widget in self.labels:
            widget.setMinimumWidth(0)
        for widget in (self.initial_buy, self.components, self.supplies, self.talents, self.invoker_spells):
            widget.hide()
        self.title.hide()
        self.grip = QSizeGrip(self)
        self._fitting = False

    def place_top_right(self):
        bounds = self.screen().availableGeometry()
        self.move(bounds.right()-self.width()-11, bounds.top()+160)
        self.fit_content()

    def show_invoker(self, enabled):
        self.invoker_active = enabled
        self.invoker_spells.setVisible(enabled)

    def set_item_lines(self, lines):
        """Rows are (plain text, completed); markup never comes from a provider."""
        self.item_lines = lines
        self.items.setTextFormat(Qt.TextFormat.RichText)
        rows = ['<b style="color:#dcaa63">ITEM BUILD</b>']
        rows.extend(f'<span style="color:{"#91a0ae" if done else "#e5eaf0"}">{escape(text)}</span>'
                    for text, done in lines)
        self.items.setText('<br>'.join(rows))

    def set_message(self, text):
        self.item_lines = None
        self.items.setTextFormat(Qt.TextFormat.PlainText)
        self.items.setText(text)

    def _style_labels(self):
        size = self.font_size
        for widget in self.labels:
            widget.setStyleSheet(f'font-size:{size}px;')
        self.hero.setStyleSheet(f'font-size:{size+2}px; font-weight:600; color:#f6f1e8;')
        self.title.setStyleSheet(f'font-size:{max(11,size-2)}px; font-weight:700; color:#dcaa63;')
        for widget in (self.clock, self.route_label, self.note, self.lane_timers):
            widget.setStyleSheet(f'font-size:{max(11,size-1)}px; color:#a1b0be;')
        self.initial_buy.setStyleSheet(f'font-size:{size}px; color:#ffe0a3; background:#303829; '
                                      'font-weight:600; padding:6px; border-left:3px solid #d4a15c;')
        for widget in (self.components, self.supplies):
            widget.setStyleSheet(f'font-size:{max(11,size-1)}px; color:#b6d8d2; background:#192932; padding:4px;')
        self.skill.setStyleSheet(f'font-size:{size}px; font-weight:600; color:#d9c4ed;')
        self.invoker_spells.setStyleSheet(f'font-size:{max(11,size-1)}px; background:#182630; padding:4px;')
        for widget in self.labels:
            widget.ensurePolished()

    @staticmethod
    def _height(widget, width):
        height = widget.heightForWidth(width)
        return max(widget.fontMetrics().height(), height if height >= 0 else widget.sizeHint().height()) + 1

    def _arrange(self, width, split=False):
        """Return explicit rectangles, so Qt cannot allocate stretch gaps or clip labels."""
        margin, gap = 8, 4
        inner = width - margin*2
        visible = lambda widget: not widget.isHidden() and bool(widget.text())
        placements = []

        def stack(widgets, x, y, column_width):
            for widget in widgets:
                if visible(widget):
                    height = self._height(widget, column_width)
                    placements.append((widget, QRect(x, y, column_width, height)))
                    y += height + gap
            return y

        top = [self.title, self.hero, self.route_label, self.clock]
        if not split:
            top.append(self.initial_buy)
        y = stack(top, margin, margin, inner)
        if split == 3:
            column = (inner-2*gap)//3
            right = inner-2*gap-2*column
            y = max(stack([self.items], margin, y, column),
                    stack([self.initial_buy, self.components, self.supplies], margin+column+gap, y, column),
                    stack([self.skill, self.talents, self.invoker_spells],
                          margin+2*(column+gap), y, right))
        elif split:
            left = (inner-gap)//2
            right = inner-gap-left
            y = max(stack([self.components, self.supplies, self.items], margin, y, left),
                    stack([self.initial_buy, self.skill, self.talents, self.invoker_spells],
                          margin+left+gap, y, right))
        else:
            y = stack([self.components, self.supplies, self.items, self.skill, self.talents,
                       self.invoker_spells], margin, y, inner)
        y = stack([self.note, self.lane_timers], margin, y, inner)
        return placements, y + margin + (0 if self.locked else 12)

    def fit_content(self, bounds=None):
        """Prefer narrow/tall; widen and place build beside skills only when needed."""
        bounds = bounds or self.screen().availableGeometry()
        y = max(bounds.top()+8, min(self.y(), bounds.bottom()-180))
        max_height = bounds.bottom()-y-8
        max_width = min(bounds.width()-16, 600)
        preferred = min(self.preferred_width, max_width)
        key = (preferred, self.font_size, bounds.x(), bounds.y(), bounds.width(), bounds.height(),
               y, self.locked, self.invoker_active,
               tuple((widget.text(), widget.isHidden()) for widget in self.labels if widget is not self.invoker_spells))
        if key == self._fit_key:
            return
        self._style_labels()
        # Normal windows stay narrow; short displays can use a two-column body.
        candidates = [(preferred, False)]
        candidates += [(w, False) for w in range(preferred+30, min(390, max_width)+1, 30)]
        candidates += [(w, True) for w in range(max(420, preferred), max_width+1, 30)]
        if candidates[-1][0] != max_width:
            candidates.append((max_width, max_width >= 420))
        if max_width >= 540:
            # Exceptionally crowded pregame on a short display: keep every section
            # visible by giving temporary purchases their own middle column.
            candidates.append((max_width, 3))
        selected = None
        for width, split in candidates:
            self.invoker_spells.setText(invoker.reference_html(columns=1 if split else 2))
            placements, height = self._arrange(width, split)
            selected = (width, height, placements, split)
            if height <= max_height:
                break
        width, height, placements, split = selected
        # A preview explicitly reports oversized content; never silently elide an item/talent.
        self.fit_ok = height <= max_height
        self.fit_message = (f'{width} × {height}px · all sections visible' if self.fit_ok else
                            'More room needed: move overlay up or reduce text size in Preview.')
        right = min(bounds.right()-8, max(bounds.left()+width+8, self.x()+self.width()))
        self._fitting = True
        self.resize(width, height)
        self.move(right-width, y)
        for widget, rect in placements:
            widget.setGeometry(rect)
        self.grip.setGeometry(width-20, height-16, 12, 12)
        self._fitting = False
        self._fit_key = key

    def set_locked(self, locked):
        if self.locked == locked:
            return
        self.locked = locked
        self.grip.setVisible(not locked)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, locked)

    def resizeEvent(self, event):
        if not self._fitting and event.oldSize().isValid() and event.size() != event.oldSize():
            if event.size().width() != event.oldSize().width():
                self.preferred_width = max(270, min(600, event.size().width()))
            self._fit_key = None
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.locked:
            self.origin = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self.origin is not None and not self.locked:
            self.move(event.globalPosition().toPoint() - self.origin)

    def mouseReleaseEvent(self, event):
        self.origin = None
        self._fit_key = None
