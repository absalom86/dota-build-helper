"""Render a synthetic Kez skill sequence using bundled real ability artwork."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['DOTA_HELPER_HOME'] = str(ROOT / '.local' / 'skill-icons-preview')

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect
from PySide6.QtGui import QFont, QFontDatabase
from dota_helper.app import MainWindow
from dota_helper.providers import Demo

app = QApplication([])
for font in ('segoeui.ttf', 'segoeuib.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
app.setFont(QFont('Segoe UI', 10))
window = MainWindow(start_services=False)
window.timer.stop()
window.capture_timer.stop()
window.draft.meta_active = False
window.hero.setCurrentIndex(window.hero.findData(145))
window.preview.setChecked(True)
route = Demo().routes(1, 1, 0)[0][0]
route.hero_id = 145
route.skills = ['kez_echo_slash', 'kez_grappling_claw', 'kez_kazurai_katana', 'kez_echo_slash',
    'kez_echo_slash', 'kez_raptor_dance', 'kez_echo_slash', 'kez_kazurai_katana', 'kez_kazurai_katana',
    'special_bonus_unique_kez_falcon_rush_duration', 'kez_kazurai_katana', 'kez_raptor_dance',
    'special_bonus_unique_kez_kazura_katana_bleed_damage', 'special_bonus_unique_kez_echo_slash_strike_count',
    'special_bonus_unique_kez_mark_damage']
window.routes = [route]
window.session.accept_routes([route])
window.render_routes()
window.tick()
output = ROOT / '.local' / 'skill-icons-preview'
output.mkdir(parents=True, exist_ok=True)
for scale, width, height in ((100, 1920, 1040), (150, 1280, 680)):
    window.overlay.fit_content(QRect(0, 0, width, height))
    app.processEvents()
    window.overlay.grab().save(str(output / f'overlay-{scale}.png'))
    window.overlay.skill.grab().save(str(output / f'skill-row-{scale}.png'))
    assert window.overlay.skill.progress == window.session.skill_progress(route)
window.close()
print('Icon rows rendered with real ability images at 100% and 150% scaling')
