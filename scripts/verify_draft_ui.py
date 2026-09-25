"""Render actual draft widgets with conspicuously labeled synthetic test data."""
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["DOTA_HELPER_HOME"] = str(ROOT / ".local" / "draft-ui-verification")
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtGui import QFontDatabase
from dota_helper.app import MainWindow
from dota_helper.draft import rank_picks

app = QApplication([])
for font in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font))
window = MainWindow(start_services=False)
window.show()
panel = window.draft
class FixtureProvider:
    def suggestions(self, enemies, excluded, pool, progress, cancel):
        tables = {enemy: [{"hero_id": hero, "games_played": 200 + hero,
                           "wins": 85 + (hero * enemy) % 40} for hero in (3, 5, 20, 26, 27, 30, 31, 50)]
                  for enemy in enemies}
        return rank_picks(enemies, tables, excluded, pool), "SYNTHETIC UI FIXTURE · Counts and scores are test data, not live recommendations."

panel.provider_factory = FixtureProvider
window.setWindowTitle("Draft helper · synthetic UI verification")
window.findChild(QLabel, "heading").setText("Draft preview · synthetic test data")
panel.auto.setChecked(False)
panel.pool.setCurrentText("Support")
for combo, hero in zip(panel.enemies, (2, 14)):
    combo.setCurrentIndex(combo.findData(hero))
window.tabs.setCurrentIndex(1)
panel.search()
deadline = time.monotonic() + 10
while panel.busy and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(.02)
assert panel.picks, panel.status.text()
out = ROOT / "docs" / "screenshots"
app.processEvents()
window.grab().save(str(out / "draft-demo.png"))
panel.overlay_enabled.setChecked(True)
window.tick()
window.overlay.title.setText("DRAFT HELPER · SYNTHETIC TEST DATA")
window.overlay.note.setText("Synthetic test scores · not recommendations")
window.overlay.resize(390, 390)
window.overlay.show()
app.processEvents()
window.overlay.grab().save(str(out / "draft-overlay-demo.png"))
window.resize(900, 700)
app.processEvents()
window.grab().save(str(out / "draft-compact-demo.png"))
window.close()
app.processEvents()
print("Synthetic draft UI rendered: desktop, compact and overlay. No live recommendation verification claimed.")
