"""Offline Kez overlay screenshots with synthetic build data and no user profile."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['DOTA_HELPER_HOME'] = str(ROOT / '.local' / 'kez-verification')

from PySide6.QtCore import QRect
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from dota_helper.app import MainWindow
from dota_helper.models import Purchase
from dota_helper.providers import Demo


def main():
    app = QApplication.instance() or QApplication([])
    for name in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf'):
        font_path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / name
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont('Segoe UI', 10))
    window = MainWindow(start_services=False)
    try:
        window.timer.stop()
        window.capture_timer.stop()
        window.draft.meta_active = False
        window.hero.setCurrentIndex(window.hero.findData(145))
        window.role.setCurrentIndex(window.role.findData(1))
        route = Demo().routes(1, 1, 0)[0][0]
        route.hero_id, route.role = 145, 1
        route.title = 'Synthetic Kez overlay fixture'
        route.skills = ['kez_echo_slash', 'kez_grappling_claw', 'kez_kazurai_katana',
                        'kez_echo_slash', 'kez_echo_slash', 'kez_raptor_dance',
                        'special_bonus_unique_kez_falcon_rush_duration',
                        'special_bonus_unique_kez_kazura_katana_bleed_damage',
                        'special_bonus_unique_kez_echo_slash_strike_count',
                        'special_bonus_unique_kez_mark_damage']
        route.purchases = [Purchase(key, second) for key, second in [
            ('tango', -60), ('branches', -60), ('branches', -60), ('branches', -60),
            ('quelling_blade', -60), ('slippers', -60), ('ward_observer', -60),
            ('circlet', 75), ('magic_stick', 120), ('boots', 180), ('gloves', 230),
            ('flask', 150), ('tango', 210), ('infused_raindrop', 420),
            ('wraith_band', 150), ('magic_wand', 320), ('power_treads', 460),
            ('bfury', 810), ('sange_and_yasha', 1130), ('black_king_bar', 1510),
            ('ultimate_scepter', 1780), ('satanic', 2090), ('butterfly', 2500),
            ('abyssal_blade', 2800), ('nullifier', 3100), ('moon_shard', 3400)]]
        window.routes = [route]
        window.session.accept_routes(window.routes)
        window.render_routes()
        window.preview.setChecked(True)
        output = ROOT / 'docs' / 'screenshots'
        output.mkdir(parents=True, exist_ok=True)
        for name, second, bounds, font_size in [
                ('kez-start', 0, QRect(0, 0, 1280, 720), 13),
                ('kez-game', 1800, QRect(0, 0, 2560, 1440), 13),
                ('kez-compact', 0, QRect(0, 0, 1024, 576), 16)]:
            window.manual_second = second
            window.overlay.font_size = font_size
            window.tick()
            window.overlay.move(bounds.right()-window.overlay.width()-8, 160)
            window.overlay.fit_content(bounds)
            app.processEvents()
            assert window.overlay.fit_ok, window.overlay.fit_message
            assert bounds.contains(window.overlay.geometry())
            if bounds.height() >= 720:
                assert window.overlay.y() == 160, 'Normal displays should retain the HUD margin'
            assert not window.overlay.kez_combos.isHidden()
            for label in window.overlay.labels:
                if not label.isHidden() and label.text():
                    assert window.overlay.rect().contains(label.geometry()), label.text()
                    assert label.height() >= label.heightForWidth(label.width()), label.text()
            path = output / (name + '.png')
            assert window.overlay.grab().save(str(path))
            print(f'{path}: {window.overlay.fit_message}')
    finally:
        window.close()
        app.processEvents()


if __name__ == '__main__':
    main()
