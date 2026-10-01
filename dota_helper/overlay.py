"""A screen-bounded overlay with responsive columns and a readable overflow fallback."""
from html import escape
import time

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QSizeGrip, QScrollBar, QWidget

from . import invoker, kez, shadow_shaman
from .catalog import clock_text, item_name
from .recency import neutral_patch_label
from .ratings import rating_text
from .skill_strip import SkillStrip


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
    def __init__(self, settings, stylesheet='', *, detached_references=False, reference_only=False):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName('buildOverlay')
        self.setStyleSheet(stylesheet + '\nQWidget#buildOverlay { background:#111820; border:1px solid #394956; }')
        self.compact = settings.get('overlay_compact_pages', True)
        self.detached_references = detached_references
        self.reference_only = reference_only
        if reference_only:
            self.compact = True
        self.reference_page = False
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
        self.shadow_shaman_active = False
        self.fit_ok = True
        self.fit_message = ''
        self.scroll_shortcuts_available = False
        self.item_lines = None
        self._fit_key = None
        self.effective_font_size = self.font_size
        self.viewport = QWidget(self)
        self.content = QWidget(self.viewport)
        self.overflow_bar = QScrollBar(Qt.Orientation.Vertical, self)
        self.overflow_bar.setStyleSheet('QScrollBar:vertical { background:#182630; width:12px; margin:0; } '
                                       'QScrollBar::handle:vertical { background:#607786; min-height:24px; } '
                                       'QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; } '
                                       'QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:none; }')
        self.overflow_bar.valueChanged.connect(self._scroll_content)
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
        self.skill = SkillStrip(self.content)
        self.skill.setWordWrap(True)
        self.talents = label()
        self.invoker_spells = label()
        self.invoker_spells.setTextFormat(Qt.TextFormat.RichText)
        self.kez_combos = label()
        self.kez_combos.setTextFormat(Qt.TextFormat.RichText)
        self.kez_combos.setToolTip(kez.DETAILS + '\n\nKatana / Sai:\n' + '\n'.join(
            f'{key}: {katana} / {sai}' for key, katana, sai in kez.KEYS))
        self.shadow_shaman_tips = label()
        self.shadow_shaman_tips.setTextFormat(Qt.TextFormat.RichText)
        self.shadow_shaman_tips.setToolTip(shadow_shaman.DETAILS)
        self.references = [self.invoker_spells, self.kez_combos, self.shadow_shaman_tips]
        self.note = label('', True)
        self.lane_timers = label('', True)
        self.labels = [self.title, self.hero, self.route_label, self.clock, self.initial_buy,
                       self.components, self.supplies, self.items, self.skill, self.talents,
                       *self.references, self.note, self.lane_timers]
        for widget in self.labels:
            widget.setMinimumWidth(0)
        for widget in (self.initial_buy, self.components, self.supplies, self.talents,
                       *self.references):
            widget.hide()
        self.title.hide()
        self.grip = QSizeGrip(self)
        self.header = QWidget(self)
        self.reference_content = QWidget(self.viewport)
        self.build_tab = QPushButton('Build', self)
        self.reference_tab = QPushButton('Hero keys', self)
        for tab in (self.build_tab, self.reference_tab):
            tab.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            tab.setCheckable(True)
            tab.setStyleSheet('QPushButton { padding:3px; background:#1c2732; border:0; font-size:12px; } '
                             'QPushButton:checked { color:#ffe0a3; border-bottom:2px solid #d4a15c; }')
            tab.setToolTip('Ctrl + Alt + F9 switches pages during play. Click here in Preview.')
        self.build_tab.clicked.connect(lambda: self.set_reference_page(False))
        self.reference_tab.clicked.connect(lambda: self.set_reference_page(True))
        self.set_compact(self.compact)
        if self.reference_only:
            for widget in self.labels:
                if widget is not self.hero and widget not in self.references:
                    widget.hide()
        self._fitting = False

    def _scroll_content(self, value):
        target = self.reference_content if self.reference_only or (self.compact and self.reference_page) else self.content
        target.move(0, -value)

    def set_compact(self, enabled):
        self.compact = enabled or self.reference_only
        enabled = self.compact
        self.reference_page = False
        self._fit_key = None
        for widget in self.labels:
            hidden = widget.isHidden()
            parent = (self.header if widget in (self.title, self.hero, self.route_label, self.clock) else
                      self.reference_content if widget in self.references else
                      self if widget is self.lane_timers else self.content) if enabled else self.content
            if self.detached_references and widget in self.references:
                parent = self.reference_content
            widget.setParent(parent)
            widget.setVisible(not hidden)
        self.header.setVisible(enabled)
        self.reference_content.hide()
        self.content.show()
        self.build_tab.hide()
        self.reference_tab.hide()
        self.overflow_bar.setValue(0)

    def set_reference_page(self, enabled):
        enabled = bool(enabled and not self.detached_references and self.compact and any(
            (self.invoker_active, self.kez_active, self.shadow_shaman_active)))
        if self.reference_page != enabled:
            self.reference_page = enabled
            self.overflow_bar.setValue(0)
            self._fit_key = None
        self.fit_content()

    def toggle_page(self):
        self.set_reference_page(not self.reference_page)

    def _fit_compact(self, bounds):
        """Keep font/width stable; scroll the body, with header and timers pinned."""
        self._style_labels()
        self._reference_text(True)
        has_reference = (not self.detached_references and not self.reference_only and
                         any((self.invoker_active, self.kez_active, self.shadow_shaman_active)))
        if self.reference_page and not has_reference:
            self.reference_page = False
            self.overflow_bar.setValue(0)
        if self._fitted_y is None or self.y() != self._fitted_y:
            self.preferred_y = self.y()
        width = min(self.preferred_width, bounds.width()-16)
        cap = min(560, int(bounds.height() * .62))
        y = max(bounds.top()+8, min(self.preferred_y, bounds.bottom()-cap-8))

        def stack(widgets, usable_width, top=8):
            placements = []
            for widget in widgets:
                if not widget.isHidden() and widget.text():
                    height = self._height(widget, usable_width-16)
                    placements.append((widget, QRect(8, top, usable_width-16, height)))
                    top += height + 5
            return placements, top + 3

        header_rects, header_h = stack([self.hero] if self.reference_only else
                                      [self.title, self.hero, self.route_label, self.clock], width)
        body = self.references if self.reference_only or self.reference_page else [self.initial_buy, self.skill,
                self.components, self.supplies, self.items, self.talents, self.note]
        lane_h = (self._height(self.lane_timers, width-16)+8
                  if not self.reference_only and not self.lane_timers.isHidden() and self.lane_timers.text() else 0)
        footer_h = lane_h + (28 if has_reference else 0) + 32
        body_rects, content_h = stack(body, width)
        height = min(cap, header_h + content_h + footer_h)
        viewport_h = max(40, height-header_h-footer_h)
        overflow = content_h > viewport_h
        if overflow:
            body_rects, content_h = stack(body, width-16)
        self._fitting = True
        right = min(bounds.right()-8, max(bounds.left()+width+8, self.x()+self.width()))
        self.resize(width, height)
        self.move(right-width, y)
        self._fitted_y = y
        self.header.setGeometry(0, 0, width, header_h)
        self.viewport.setGeometry(0, header_h, width-16 if overflow else width, viewport_h)
        show_reference = self.reference_only or self.reference_page
        active = self.reference_content if show_reference else self.content
        self.content.setVisible(not show_reference)
        self.reference_content.setVisible(show_reference)
        active.resize(self.viewport.width(), content_h)
        placed = {widget for widget, _ in header_rects + body_rects}
        for widget in self.labels:
            if widget.parentWidget() in (self.header, active) and widget not in placed:
                # Empty QLabels still paint their stylesheet background. Keep
                # unplaced labels from covering content with stale rectangles.
                widget.setGeometry(0, 0, 0, 0)
        for widget, rect in header_rects + body_rects:
            widget.setGeometry(rect)
        self.overflow_bar.setGeometry(width-16, header_h, 16, viewport_h)
        self.overflow_bar.setVisible(overflow)
        self.overflow_bar.setRange(0, max(0, content_h-viewport_h))
        self.overflow_bar.setPageStep(viewport_h)
        self._scroll_content(self.overflow_bar.value())
        footer_y = header_h + viewport_h
        if lane_h:
            self.lane_timers.setGeometry(8, footer_y+4, width-16, lane_h-8)
        footer_y += lane_h
        for index, tab in enumerate((self.build_tab, self.reference_tab)):
            tab.setVisible(has_reference)
            tab.setGeometry(8+index*((width-16)//2), footer_y, (width-16)//2, 26)
        self.build_tab.setChecked(not self.reference_page)
        self.reference_tab.setChecked(self.reference_page)
        hint = (('Ctrl+Alt+F9: switch page' if self.scroll_shortcuts_available else
                 'Preview: click Build / Hero keys') if has_reference else '')
        if overflow:
            shortcut = 'Ctrl+Alt+Shift+PgUp/PgDn' if self.reference_only else 'Ctrl+Alt+PgUp/PgDn'
            hint += ('\n' if hint else '') + (shortcut + ': scroll' if self.scroll_shortcuts_available else 'Scroll in Preview')
        elif not hint:
            hint = 'Ctrl+Alt+F9: hide hero tips' if self.reference_only and self.scroll_shortcuts_available else (
                'Hero tips' if self.reference_only else 'Build · all items visible')
        self.overflow_hint.setText(hint)
        self.overflow_hint.setGeometry(0, height-32, width, 32)
        self.overflow_hint.show()
        self.grip.setGeometry(width-16, height-14, 12, 12)
        self.fit_ok = not overflow
        page = 'Hero tips' if self.reference_only else 'Hero keys' if self.reference_page else 'Build'
        self.fit_message = f'{width} × {height}px · {page} · ' + ('scroll for more' if overflow else 'all page content visible')
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
            self.show_shadow_shaman(False)

    def show_kez(self, enabled):
        self.kez_active = enabled
        self.kez_combos.setVisible(enabled)
        if enabled:
            self.show_invoker(False)
            self.show_shadow_shaman(False)

    def show_shadow_shaman(self, enabled):
        self.shadow_shaman_active = enabled
        self.shadow_shaman_tips.setVisible(enabled)
        if enabled:
            self.show_invoker(False)
            self.show_kez(False)

    def _reference_text(self, split):
        self.invoker_spells.setText(invoker.reference_html(columns=1 if split else 2))
        self.kez_combos.setText(kez.reference_html(columns=1 if split else 2))
        self.shadow_shaman_tips.setText(shadow_shaman.reference_html())

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
                                'background:#182630;')
        for widget in self.references:
            widget.setStyleSheet(f'font-size:{max(11,size-1)}px; background:#182630; padding:4px;')
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
        visible = lambda widget: (not widget.isHidden() and bool(widget.text()) and
                                  not (self.detached_references and widget in self.references))
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
        elif split == 2:
            top.extend([self.initial_buy, self.components, self.supplies])
        y = stack(top, margin, margin, inner)
        if split == 3:
            column = (inner-2*gap)//3
            right = inner-2*gap-2*column
            middle = [self.initial_buy, self.components, self.supplies]
            references = list(self.references)
            # Longer hero references need their own column;
            # and use the spare space below early purchases for talent picks.
            if self.kez_active or self.shadow_shaman_active:
                middle.append(self.talents)
            else:
                references.insert(0, self.talents)
            y = max(stack([self.skill, self.items], margin, y, column),
                    stack(middle, margin+column+gap, y, column),
                    stack(references,
                          margin+2*(column+gap), y, right))
        elif split == 2:
            # Keep the optional reference beside the build rather than piling
            # starting purchases, skills and talents above it on short screens.
            left = (inner-gap)//2
            right = inner-gap-left
            y = max(stack([self.skill, self.items, self.talents], margin, y, left),
                    stack(self.references, margin+left+gap, y, right))
        elif split:
            left = (inner-gap)//2
            right = inner-gap-left
            y = max(stack([self.components, self.supplies, self.items], margin, y, left),
                    stack([self.initial_buy, self.skill, self.talents, *self.references],
                          margin+left+gap, y, right))
        else:
            y = stack([self.skill, self.components, self.supplies, self.items, self.talents,
                       *self.references], margin, y, inner)
        y = stack([self.note, self.lane_timers], margin, y, inner)
        return placements, y + margin + (0 if self.locked else 12)

    def fit_content(self, bounds=None):
        """Fit within logical screen bounds, including Windows display scaling.

        Keep the preferred font when possible. Reclaim a low saved position,
        then temporarily compact text before moving above the usual HUD margin.
        Exceptionally large data uses a scrollbar and optional global shortcuts, never a
        window extending below the monitor.
        """
        bounds = bounds or self.screen().availableGeometry()
        if self.compact:
            self._fit_compact(bounds)
            return
        if self._fitted_y is None or self.y() != self._fitted_y:
            self.preferred_y = self.y()
        y = max(bounds.top()+8, min(self.preferred_y, bounds.bottom()-180))
        anchor = min(y, bounds.top()+160)
        max_width = min(bounds.width()-16, 600)
        preferred = min(self.preferred_width, max_width)
        key = (preferred, self.font_size, bounds.x(), bounds.y(), bounds.width(), bounds.height(),
               y, self.locked, self.invoker_active, self.kez_active, self.shadow_shaman_active,
               tuple((widget.text(), widget.isHidden()) for widget in self.labels
                     if widget not in self.references))
        if key == self._fit_key:
            return
        # Draft suggestions live in one label. Narrowing that label into a build
        # column merely adds wrapping while leaving the other columns empty.
        auxiliary = any(not w.isHidden() and w.text() for w in
                        (self.initial_buy, self.components, self.supplies, self.talents,
                         *self.references))
        widths = list(range(preferred, max_width+1, 30))
        if max_width not in widths:
            widths.append(max_width)
        candidates = [(w, False) for w in widths if w <= 390]
        if auxiliary:
            candidates += [(w, True) for w in widths if w >= 420]
            if any(not w.isHidden() for w in self.references):
                candidates += [(w, 2) for w in widths if w >= 420]
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
            fitting = [layout for layout in measured if layout[1] <= bounds.bottom()-anchor-8]
            # Prefer a thin overlay; at equal width choose the shorter layout
            # so a long reference cannot leave a mostly empty adjacent column.
            selected = min(fitting, key=lambda v: (v[0], v[1])) if fitting else None
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
                            f'{width} × {height}px · scroll with shortcuts or in Preview{compact}')
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
        placed = {widget for widget, _ in placements}
        for widget in self.labels:
            if widget not in placed:
                widget.setGeometry(0, 0, 0, 0)
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

    def scroll_page(self, direction):
        """Move without taking focus, including while the overlay is click-through."""
        bar = self.overflow_bar
        if direction == 0:
            bar.setValue(0)
        else:
            bar.setValue(bar.value() + direction * max(1, bar.pageStep() - 40))

    def set_scroll_shortcuts_available(self, available):
        self.scroll_shortcuts_available = available
        self.overflow_hint.setText('Ctrl+Alt: PgUp / PgDn / Home' if available else
                                   'More below · scroll in Preview')

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
