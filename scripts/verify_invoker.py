"""Offline UI/export acceptance, with deliberately synthetic Invoker data."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['DOTA_HELPER_HOME'] = str(ROOT / '.local' / 'invoker-verification')

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect
from PySide6.QtGui import QFontDatabase
from dota_helper.app import MainWindow
from dota_helper.catalog import ABILITIES
from dota_helper.models import Purchase
from dota_helper.providers import Demo
from dota_helper import guides

app = QApplication([])
for name in ['segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf']:
    QFontDatabase.addApplicationFont(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / name))
window = MainWindow(start_services=False)
window.draft.meta_active = False
window.hero.setCurrentIndex(window.hero.findData(74))
window.role.setCurrentIndex(window.role.findData(2))
route = Demo().routes(1, 1, 0)[0][0]
route.hero_id, route.role = 74, 2
route.title = 'Synthetic Invoker UI fixture'
route.skills = ['invoker_quas', 'invoker_wex'] + [key for key in ABILITIES if key.startswith('special_bonus_unique_invoker')][:4]
route.purchases = [Purchase(key, second) for key, second in [
    ('tango', -60), ('branches', -60), ('branches', -60), ('circlet', -60), ('faerie_fire', -60),
    ('ward_observer', -60), ('boots', 140), ('magic_wand', 200), ('urn_of_shadows', 310),
    ('circlet', 120), ('gauntlets', 210), ('flask', 240), ('clarity', 270),
    ('clarity', 480), ('infused_raindrop', 420),
    ('power_treads', 430), ('spirit_vessel', 800), ('witch_blade', 1000),
    ('black_king_bar', 1500), ('sheepstick', 2000), ('refresher', 2500)]]
window.routes = [route]
window.session.accept_routes(window.routes)
window.render_routes()
window.preview.setChecked(True)
window.tick()
# Test available space below the stats, including a short display.
output = ROOT / 'docs' / 'screenshots'
output.mkdir(parents=True, exist_ok=True)
window.overlay.move(980, 160)
window.overlay.fit_content(QRect(0, 0, 1280, 1080))
app.processEvents()
assert window.overlay.fit_ok
assert window.overlay.invoker_spells.geometry().bottom() < window.overlay.height()
window.overlay.grab().save(str(output / 'invoker-start.png'))
window.manual_second = 420
window.tick()
window.overlay.move(980, 160)
window.overlay.fit_content(QRect(0, 0, 1280, 760))
app.processEvents()
assert window.overlay.fit_ok
assert window.overlay.initial_buy.isHidden() and window.overlay.components.isHidden()
assert not window.overlay.supplies.isHidden()
assert 'Clarity ×2' in window.overlay.supplies.text()
window.overlay.grab().save(str(output / 'invoker-laning.png'))
window.manual_second = 900
window.tick()
window.overlay.move(980, 160)
window.overlay.fit_content(QRect(0, 0, 1280, 1080))
app.processEvents()
window.overlay.grab().save(str(output / 'invoker-game.png'))
window.overlay.move(980, 160)
window.overlay.fit_content(QRect(0, 0, 1280, 760))
app.processEvents()
assert window.overlay.fit_ok
assert window.overlay.invoker_spells.geometry().bottom() < window.overlay.height()
assert window.overlay.talents.geometry().bottom() < window.overlay.height()
assert window.overlay.height() <= 592
window.overlay.grab().save(str(output / 'invoker-compact.png'))
window.resize(900, 750)
window.more_button.setChecked(True)
window.show()
app.processEvents()
window.grab().save(str(output / 'shop-export-controls.png'))
path = guides.write_guide(route, ROOT / '.local' / 'invoker-verification' / guides.filename(route))
print(f'Invoker overlay fits tall and short displays without scrolling. Synthetic guide exported: {path}')
window.close()
app.processEvents()
