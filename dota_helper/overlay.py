"""A screen-bounded overlay with responsive columns and a readable overflow fallback."""
from html import escape
import time

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QLabel, QSizeGrip, QScrollBar, QWidget

from . import invoker, kez
from .catalog import clock_text, item_name
from .recency import neutral_patch_label
from .ratings import rating_text


def route_identity(route, now=None):
    if route.demo:
        return 'OFFLINE DEMO · synthetic'
    source = (f'PRO · {route.player}' if route.tournament or route.pro_player else
              rating_text(route))
    source = ' '.join(source.split())
    if len(source) > 55:
        source = source[:52] + '…'
    age = max(0, int(((time.time() if now is None else now)-route.start_time)/86400))
    date = f' · {age}d ago' if route.start_time and age else ' · today' if route.start_time else ''
    patch = 'Patch ' + neutral_patch_label(route)
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
        self.preferred_y = self.y()
        self._fitted_y = None
        self.origin = None
        self.locked = False
        self.invoker_active = False
        self.kez_active = False
        self.fit_ok = True
        self.fit_message = ''
        self.item_lines = None
        self._fit_key = None
        self.effective_font_size = self.font_size
        self.viewport = QWidget(self)
        self.content = QWidget(self.viewport)
        self.overflow_bar = QScrollBar(Qt.Orientation.Vertical, self)
        self.overflow_bar.valueChanged.connect(lambda value: self.content.move(0, -value))
        self.overflow_bar.hide()
        self.overflow_hint = QLabel('More below · scroll in Preview', self)
        self.overflow_hint.setStyleSheet('font-size:11px; color:#ffe0a3; background:#263239; padding:3px;')
        self.overflow_hint.hide()

        def label(text='', muted=False):
            result = QLabel(text, self.content)
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
        self.kez_combos = label()
        self.kez_combos.setTextFormat(Qt.TextFormat.RichText)
        self.kez_combos.setToolTip(kez.DETAILS + '\n\nKatana / Sai:\n' + '\n'.join(
            f'{key}: {katana} / {sai}' for key, katana, sai in kez.KEYS))
        self.note = label('', True)
        self.lane_timers = label('', True)
        self.labels = [self.title, self.hero, self.route_label, self.clock, self.initial_buy,
                       self.components, self.supplies, self.items, self.skill, self.talents,
                       self.invoker_spells, self.kez_combos, self.note, self.lane_timers]
        for widget in self.labels:
            widget.setMinimumWidth(0)
        for widget in (self.initial_buy, self.components, self.supplies, self.talents,
                       self.invoker_spells, self.kez_combos):
            widget.hide()
        self.title.hide()
        self.grip = QSizeGrip(self)
        self._fitting = False

    def place_top_right(self):
        bounds = self.screen().availableGeometry()
        self.preferred_y = bounds.top()+160
        self._fitted_y = None
        self.move(bounds.right()-self.width()-11, bounds.top()+160)
        self.fit_content()

    def show_invoker(self, enabled):
        self.invoker_active = enabled
        self.invoker_spells.setVisible(enabled)
        if enabled:
            self.show_kez(False)

    def show_kez(self, enabled):
        self.kez_active = enabled
        self.kez_combos.setVisible(enabled)
        if enabled:
            self.show_invoker(False)

    def _reference_text(self, split):
        self.invoker_spells.setText(invoker.reference_html(columns=1 if split else 2))
        self.kez_combos.setText(kez.reference_html(columns=1 if split else 2))

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

    def _style_labels(self, size=None):
        size = self.font_size if size is None else size
        self.effective_font_size = size
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
        self.skill.setStyleSheet(f'font-size:{size+1}px; font-weight:600; color:#f0dcff; '
                                'background:#2a2638; padding:5px; border-left:3px solid #bda0df;')
        self.invoker_spells.setStyleSheet(f'font-size:{max(11,size-1)}px; background:#182630; padding:4px;')
        self.kez_combos.setStyleSheet(f'font-size:{max(11,size-1)}px; background:#182630; padding:4px;')
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
            middle = [self.initial_buy, self.components, self.supplies]
            references = [self.invoker_spells, self.kez_combos]
            # Kez has three combo stages. Give that reference its own column
            # and use the spare space below early purchases for talent picks.
            if self.kez_active:
                middle.append(self.talents)
            else:
                references.insert(0, self.talents)
            y = max(stack([self.skill, self.items], margin, y, column),
                    stack(middle, margin+column+gap, y, column),
                    stack(references,
                          margin+2*(column+gap), y, right))
        elif split:
            left = (inner-gap)//2
            right = inner-gap-left
            y = max(stack([self.components, self.supplies, self.items], margin, y, left),
                    stack([self.initial_buy, self.skill, self.talents, self.invoker_spells, self.kez_combos],
                          margin+left+gap, y, right))
        else:
            y = stack([self.skill, self.components, self.supplies, self.items, self.talents,
                       self.invoker_spells, self.kez_combos], margin, y, inner)
        y = stack([self.note, self.lane_timers], margin, y, inner)
        return placements, y + margin + (0 if self.locked else 12)

    def fit_content(self, bounds=None):
        """Fit within logical screen bounds, including Windows display scaling.

        Keep the preferred font when possible. Reclaim a low saved position,
        then temporarily compact text before moving above the usual HUD margin.
        Exceptionally large data uses an explicit Preview scrollbar, never a
        window extending below the monitor.
        """
        bounds = bounds or self.screen().availableGeometry()
        if self._fitted_y is None or self.y() != self._fitted_y:
            self.preferred_y = self.y()
        y = max(bounds.top()+8, min(self.preferred_y, bounds.bottom()-180))
        anchor = min(y, bounds.top()+160)
        max_width = min(bounds.width()-16, 600)
        preferred = min(self.preferred_width, max_width)
        key = (preferred, self.font_size, bounds.x(), bounds.y(), bounds.width(), bounds.height(),
               y, self.locked, self.invoker_active, self.kez_active,
               tuple((widget.text(), widget.isHidden()) for widget in self.labels
                     if widget not in (self.invoker_spells, self.kez_combos)))
        if key == self._fit_key:
            return
        # Draft suggestions live in one label. Narrowing that label into a build
        # column merely adds wrapping while leaving the other columns empty.
        auxiliary = any(not w.isHidden() and w.text() for w in
                        (self.initial_buy, self.components, self.supplies, self.talents,
                         self.invoker_spells, self.kez_combos))
        widths = list(range(preferred, max_width+1, 30))
        if max_width not in widths:
            widths.append(max_width)
        candidates = [(w, False) for w in widths if w <= 390]
        if auxiliary:
            candidates += [(w, True) for w in widths if w >= 420]
            if max_width >= 540:
                candidates.append((max_width, 3))
        candidates += [(w, False) for w in widths if w > 390]
        layouts = []
        selected = None
        for size in range(self.font_size, 10, -1):
            self._style_labels(size)
            measured = []
            for width, split in candidates:
                self._reference_text(split)
                placements, height = self._arrange(width, split)
                measured.append((width, height, placements, split, size))
            layouts.extend(measured)
            selected = next((layout for layout in measured if layout[1] <= bounds.bottom()-anchor-8), None)
            if selected:
                break
        if selected is None:
            # On very short logical displays use the rest of the screen. Prefer
            # the user's font, then a smaller width, among layouts that fit.
            fitting = [layout for layout in layouts if layout[1] <= bounds.height()-16]
            selected = min(fitting, key=lambda v: (-v[4], v[0], v[1])) if fitting else min(layouts, key=lambda v: v[1])
        width, content_height, placements, split, size = selected
        self._style_labels(size)
        self._reference_text(split)
        height = min(content_height, bounds.height()-16)
        y = max(bounds.top()+8, min(y, bounds.bottom()-height-8))
        self.fit_ok = content_height <= height
        if not self.fit_ok:
            # Reserve actual space for the scrollbar and notice, then remeasure
            # the full content at its real viewport width rather than clipping it.
            placements, content_height = self._arrange(width-18, split)
        compact = f' · auto-fit {size}px (preferred {self.font_size}px)' if size != self.font_size else ''
        self.fit_message = (f'{width} × {height}px · all sections visible{compact}' if self.fit_ok else
                            f'{width} × {height}px · scroll in Preview for remaining content{compact}')
        right = min(bounds.right()-8, max(bounds.left()+width+8, self.x()+self.width()))
        self._fitting = True
        self.resize(width, height)
        self.move(right-width, y)
        self._fitted_y = y
        viewport_height = height if self.fit_ok else height-28
        self.viewport.setGeometry(0, 0, width if self.fit_ok else width-18, viewport_height)
        self.content.resize(self.viewport.width(), content_height)
        self.overflow_bar.setVisible(not self.fit_ok)
        self.overflow_hint.setVisible(not self.fit_ok)
        self.overflow_bar.setGeometry(width-18, 0, 18, viewport_height)
        self.overflow_hint.setGeometry(0, height-28, width, 28)
        self.overflow_bar.setRange(0, max(0, content_height-viewport_height) if not self.fit_ok else 0)
        self.overflow_bar.setPageStep(viewport_height)
        self.content.move(0, -self.overflow_bar.value())
        for widget, rect in placements:
            widget.setGeometry(rect)
        self.grip.setGeometry(width-20, height-16, 12, 12)
        self._fitting = False
        self._fit_key = key

    def wheelEvent(self, event):
        if not self.locked and self.overflow_bar.maximum():
            self.overflow_bar.setValue(self.overflow_bar.value()-event.angleDelta().y()//3)
            event.accept()
        else:
            super().wheelEvent(event)

    def set_locked(self, locked):
        if self.locked == locked:
            return
        self.locked = locked
        if locked:
            self.overflow_bar.setValue(0)
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
