"""Render actual Qt widgets offscreen and exercise route switching; no game required."""
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["DOTA_HELPER_HOME"] = str(ROOT / ".local" / "ui-verification")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from dota_helper.app import MainWindow

app = QApplication([])
for font in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
    QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font))
window = MainWindow(demo=True, start_services=False)
window.show()
deadline = time.monotonic() + 10
while window.fetching and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(.02)
assert len(window.routes) == 3
assert window.session.selected == "demo:0"
window.purchases.item(6, 0).setCheckState(Qt.CheckState.Checked)
window.route_choice.setCurrentIndex(1)
assert ("bfury", 1) in window.session.completed
assert window.session.selected == "demo:1"
window.manual_time.setValue(500)
window.sync_clock()
window.tick()
assert "Manual estimate" in window.overlay.clock.text()
# Make the overlay preview show remaining purchases rather than already-bought starting items.
for row in range(6):
    window.purchases.item(row, 0).setCheckState(Qt.CheckState.Checked)
window.tick()
out = ROOT / "docs" / "screenshots"
out.mkdir(parents=True, exist_ok=True)
app.processEvents()
window.grab().save(str(out / "desktop-demo.png"))
window.overlay.place_top_right()
window.overlay.show()
app.processEvents()
assert window.overlay.width() == 270
window.overlay.grab().save(str(out / "overlay-demo.png"))
window.tabs.setCurrentIndex(2)
app.processEvents()
window.grab().save(str(out / "settings.png"))
# Exercise a smaller desktop window as well.
window.tabs.setCurrentIndex(0)
window.resize(900, 700)
app.processEvents()
window.grab().save(str(out / "compact-demo.png"))
window.close()
app.processEvents()
print("UI smoke passed: default route, switching, purchase progress, manual clock, and 4 screenshots.")
