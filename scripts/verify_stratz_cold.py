"""Real manual lookups from a fresh profile: all five roles plus sparse-guide heroes."""
import json
import os
from pathlib import Path
import shutil
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
profile = ROOT / '.local' / ('stratz-cold-' + uuid.uuid4().hex[:8])
profile.mkdir()
shutil.copyfile(ROOT / '.local/stratz-key.bin', profile / 'stratz-key.bin')
os.environ['DOTA_HELPER_HOME'] = str(profile)
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from dota_helper.app import MainWindow

app = QApplication([])
window = MainWindow(start_services=False)
window.source.setCurrentIndex(4)
window.resize(1280, 1000)
window.show()
results = []
for hero_id, role in [(1,1), (13,2), (2,3), (86,4), (5,5), (34,2), (66,5), (145,1), (155,5)]:
    window.hero.setCurrentIndex(window.hero.findData(hero_id))
    window.role.setCurrentIndex(window.role.findData(role))
    window.new_match()
    start = time.monotonic()
    window.find_button.click()
    while window.fetching and time.monotonic() - start < 12:
        app.processEvents()
        time.sleep(.01)
    seconds = time.monotonic() - start
    assert not window.fetching, 'Lookup did not finish'
    distinct = len({(tuple(p.key for p in r.purchases), tuple(r.skills)) for r in window.routes})
    assert distinct == 10, window.status.text()
    for i, route in enumerate(window.routes):
        item = window.match_table.item(i, 0)
        window.match_table.scrollToItem(item)
        app.processEvents()
        QTest.mouseClick(window.match_table.viewport(), Qt.MouseButton.LeftButton,
                        pos=window.match_table.visualItemRect(item).center())
        assert window.current_route().id == route.id
        assert window.purchases.rowCount() == len(route.purchases)
    result = {'hero': window.hero.currentText(), 'role': role, 'distinct': distinct,
              'seconds': round(seconds, 3), 'selection_ok': True, 'status': window.status.text()}
    results.append(result)
    print(json.dumps(result), flush=True)
    time.sleep(1)
(ROOT / 'docs/stratz-cold-lookups.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
window.close()
app.processEvents()
