"""Render the reported Kez case as compact build and reference pages at 1080p scales."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtCore import QRect
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from test_kez import crowded_kez_overlay

app = QApplication([])
for name in ('segoeui.ttf', 'segoeuib.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + name)
app.setFont(QFont('Segoe UI', 10))
output = ROOT / '.local' / 'overlay-pages'
output.mkdir(parents=True, exist_ok=True)
overlay = crowded_kez_overlay(13)
overlay.set_compact(True)
overlay.route_label.setText('PRO · Example player · 40d ago\nPatch 7.41e')
overlay.clock.setText('02:29 · Game clock')
overlay.initial_buy.hide()
overlay.components.hide()
overlay.supplies.hide()
overlay.talents.hide()
overlay.note.setText('')
overlay.skill.setText('NEXT SKILL\nFalcon Rush\nThen: Kazurai Katana → Grappling Claw')
overlay.set_item_lines([(f'{minute} {item}', False) for minute, item in [
    ('06:26', 'Magic Wand'), ('06:26', 'Power Treads'), ('10:41', 'Mage Slayer'),
    ('16:38', 'Desolator'), ('23:05', 'Black King Bar'), ('29:11', "Aghanim's Scepter"),
    ('33:37', 'Daedalus'), ('38:35', 'Blink Dagger'), ('43:33', "Aghanim's Blessing")]])
overlay.lane_timers.setText('Radiant bottom · small camp · Approx.\nPull: 16s · ~2:45–2:47\nStack: 24s · ~2:53–2:55')
overlay.set_scroll_shortcuts_available(True)
overlay.show()
for scale, width, height in ((100, 1920, 1040), (125, 1536, 824), (150, 1280, 680)):
    for reference in (False, True):
        overlay.set_reference_page(reference)
        overlay.move(width-overlay.width()-12, 160)
        bounds = QRect(0, 0, width, height)
        overlay.fit_content(bounds)
        app.processEvents()
        assert bounds.contains(overlay.geometry())
        assert overlay.height() <= min(560, int(height*.62))
        page = 'reference' if reference else 'build'
        overlay.grab().save(str(output / f'kez-{scale}-{page}.png'))
        if overlay.overflow_bar.maximum():
            overlay.overflow_bar.setValue(overlay.overflow_bar.maximum())
            overlay.grab().save(str(output / f'kez-{scale}-{page}-bottom.png'))
        print(scale, page, overlay.fit_message)
overlay.close()
