"""Live Qt/provider check using an isolated profile and user-encrypted key."""
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
profile = ROOT / '.local' / 'stratz-ui-check'
profile.mkdir(parents=True, exist_ok=True)
for name in ('stratz-key.bin', 'stratz-reference-matches.json'):
    shutil.copyfile(ROOT / '.local' / name, profile / name)
os.environ['DOTA_HELPER_HOME'] = str(profile)
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from dota_helper.app import MainWindow

app = QApplication([])
for font in ('segoeui.ttf','segoeuib.ttf'):
    QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR'])/'Fonts'/font))
window = MainWindow(start_services=False)
window.source.setCurrentIndex(4)
window.show()
started = time.monotonic()
window.fetch()
while window.fetching and time.monotonic()-started < 12:
    app.processEvents()
    time.sleep(.02)
assert not window.fetching, 'UI worker did not finish'
assert len(window.routes) >= 2, window.status.text()
ids = [r.match_ids[0] for r in window.routes]
assert 8987805727 in ids and 8987753263 in ids, ids
assert window.current_route().source == 'STRATZ'
assert 'STRATZ' in window.evidence.text()
assert 'unverified' in window.current_route().patch_label
window.route_choice.setCurrentIndex(1)
assert window.session.explicit_choice
app.processEvents()
window.grab().save(str(ROOT/'docs/screenshots/stratz-live.png'))
result = {'ok':True,'seconds':round(time.monotonic()-started,2),'games':len(ids),'reference_matches':ids[:2],
          'status':window.status.text(),'route_switch':True}
(profile/'report.json').write_text(json.dumps(result,indent=2))
window.close()
app.processEvents()
print(json.dumps(result,indent=2))
