"""Render crowded synthetic overlays with and without optional hero references."""
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
from test_overlay_layout import crowded_overlay, assert_visible_geometry


def main():
    app = QApplication([])
    for name in ('segoeui.ttf', 'segoeuib.ttf'):
        path = Path('C:/Windows/Fonts') / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    app.setFont(QFont('Segoe UI', 10))
    output = ROOT / '.local' / 'overlay-sizes'
    output.mkdir(parents=True, exist_ok=True)
    for hero in ('invoker', 'kez', 'shaman'):
        for references in (True, False):
            overlay = crowded_overlay() if hero == 'invoker' else crowded_kez_overlay(13)
            try:
                if hero == 'shaman':
                    overlay.hero.setText('Shadow Shaman · Soft support')
                    overlay.skill.setText('NEXT SKILL\nShackles\nThen: Ether Shock → Hex')
                    overlay.talents.setText('Talent picks · synthetic layout fixture')
                    overlay.show_shadow_shaman(True)
                if not references:
                    overlay.show_invoker(False)
                    overlay.show_kez(False)
                    overlay.show_shadow_shaman(False)
                overlay.show()
                for scale, width, height in ((100, 1920, 1040), (125, 1536, 824), (150, 1280, 680)):
                    bounds = QRect(0, 0, width, height)
                    overlay.move(width-overlay.width()-12, 160)
                    overlay.fit_content(bounds)
                    app.processEvents()
                    assert_visible_geometry(overlay, bounds)
                    assert overlay.y() == 160
                    name = f'{hero}-{scale}-reference-{int(references)}'
                    assert overlay.grab().save(str(output / f'{name}.png'))
                    print(f'{name}: {overlay.fit_message}')
            finally:
                overlay.close()


if __name__ == '__main__':
    main()
