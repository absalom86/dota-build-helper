"""Render two real app panels with a synthetic route at common 1080p scales."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['DOTA_HELPER_HOME'] = str(ROOT / '.local' / 'two-panels-preview')

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect
from PySide6.QtGui import QFont, QFontDatabase
from dota_helper.app import MainWindow

app = QApplication([])
for font in ('segoeui.ttf', 'segoeuib.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
app.setFont(QFont('Segoe UI', 10))
window = MainWindow(start_services=False)
window.timer.stop()
window.capture_timer.stop()
window.draft.meta_active = False
window.hero.setCurrentIndex(window.hero.findData(145))
window.hero_references.setChecked(True)
window.preview.setChecked(True)
window.tick()
main, hero = window.overlay, window.hero_overlay
main.set_locked(True)
hero.set_locked(True)
main.route_label.setText('Synthetic layout example\nPatch unknown')
main.clock.setText('02:29 · Game clock')
main.note.setText('')
main.skill.setText('NEXT SKILL\nFalcon Rush\nThen: Kazurai Katana → Grappling Claw')
main.set_item_lines([(f'{time} {item}', False) for time, item in [
    ('06:26', 'Magic Wand'), ('06:26', 'Power Treads'), ('10:41', 'Mage Slayer'),
    ('16:38', 'Desolator'), ('23:05', 'Black King Bar'), ('29:11', "Aghanim's Scepter"),
    ('33:37', 'Daedalus'), ('38:35', 'Blink Dagger'), ('43:33', "Aghanim's Blessing")]])
main.lane_timers.setText('Radiant bottom · small camp · Approx.\nPull: 16s · ~2:45–2:47\nStack: 24s · ~2:53–2:55')
output = ROOT / '.local' / 'two-panels-preview'
output.mkdir(parents=True, exist_ok=True)
for scale, width, height in ((100, 1920, 1040), (125, 1536, 824), (150, 1280, 680)):
    bounds = QRect(0, 0, width, height)
    main.move(width-main.width()-12, 160)
    hero.move(main.x()-hero.width()-12, 160)
    for name, panel in (('build', main), ('hero', hero)):
        panel.set_scroll_shortcuts_available(True)
        panel.fit_content(bounds)
        panel.show()
        app.processEvents()
        assert bounds.contains(panel.geometry())
        panel.grab().save(str(output / f'{name}-{scale}.png'))
    assert not main.geometry().intersects(hero.geometry())
print('Two panels rendered at 100%, 125%, 150%; no overlap')
window.close()
