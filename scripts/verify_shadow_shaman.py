"""Render the real Shadow Shaman overlay with an isolated synthetic build."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['DOTA_HELPER_HOME'] = str(ROOT / '.local' / 'shaman-preview-profile')

from PySide6.QtCore import QRect
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from dota_helper.app import MainWindow
from dota_helper.models import Purchase
from dota_helper.providers import Demo


def main():
    app = QApplication([])
    # The Windows offscreen backend may not discover the system fonts itself.
    for name in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf'):
        font = Path('C:/Windows/Fonts') / name
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont('Segoe UI', 10))
    window = MainWindow(start_services=False)
    try:
        window.timer.stop()
        window.capture_timer.stop()
        window.draft.meta_active = False
        window.hero.setCurrentIndex(window.hero.findData(27))
        window.role.setCurrentIndex(window.role.findData(4))
        route = Demo().routes(1, 1, 0)[0][0]
        route.hero_id, route.role = 27, 4
        route.title = 'Synthetic Shadow Shaman layout fixture'
        route.skills = ['shadow_shaman_shackles', 'shadow_shaman_ether_shock',
                        'shadow_shaman_voodoo', 'shadow_shaman_shackles',
                        'shadow_shaman_shackles', 'shadow_shaman_mass_serpent_ward']
        route.purchases = [Purchase(key, second) for key, second in [
            ('tango', -60), ('branches', -60), ('branches', -60),
            ('ward_observer', -60), ('blood_grenade', -60),
            ('boots', 130), ('magic_stick', 60), ('flask', 150), ('clarity', 120), ('tango', 180),
            ('magic_wand', 220), ('arcane_boots', 430), ('blink', 880), ('aether_lens', 1110),
            ('glimmer_cape', 1470), ('ultimate_scepter', 1780), ('black_king_bar', 2090), ('refresher', 2450)]]
        window.routes = [route]
        window.session.accept_routes(window.routes)
        window.render_routes()
        window.preview.setChecked(True)
        for name, second, bounds, font_size in [
                ('start', 0, QRect(0, 0, 1280, 720), 13),
                ('game', 900, QRect(0, 0, 2560, 1440), 13),
                ('compact', 0, QRect(0, 0, 1024, 576), 16)]:
            window.manual_second = second
            window.overlay.font_size = font_size
            window.tick()
            window.overlay.move(bounds.right()-window.overlay.width()-8, 160)
            window.overlay.fit_content(bounds)
            app.processEvents()
            assert window.overlay.fit_ok and bounds.contains(window.overlay.geometry())
            if bounds.height() >= 720:
                assert window.overlay.y() == 160
            assert not window.overlay.shadow_shaman_tips.isHidden()
            path = ROOT / '.local' / f'shadow-shaman-{name}.png'
            assert window.overlay.grab().save(str(path))
            print(f'{path}: {window.overlay.fit_message}')
    finally:
        window.close()
        app.processEvents()


if __name__ == '__main__':
    main()
