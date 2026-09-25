"""Verify real cached premier Treant builds and selection without network."""
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['DOTA_HELPER_HOME']=str(ROOT/'.local/treant-ui')
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from dota_helper.history import SearchHistory,decode
from dota_helper.app import MainWindow
raw=json.loads((ROOT/'.local/cache/tournaments-v1-83-5.json').read_text())
routes=decode(dict(hero=83,role=5,source=0,routes=raw['routes']))
assert [r.match_ids[0] for r in routes[:5]]==[8947983249,8946996385,8946860406,8946343023,8946161784]
assert len(routes)==10
history=SearchHistory(Path(os.environ['DOTA_HELPER_HOME']))
history.save(83,5,0,routes,routes[0].id,'Verified tournament index')
app=QApplication([])
for font in ('segoeui.ttf','segoeuib.ttf'):
    QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR'])/'Fonts'/font))
window=MainWindow(start_services=False)
window.resize(1500,1000)
window.show()
window.hero.setCurrentIndex(window.hero.findData(83))
window.role.setCurrentIndex(window.role.findData(5))
window.launch_worker=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('Cached lookup must not fetch'))
window.fetch()
for index,route in enumerate(routes):
    window.route_choice.setCurrentIndex(index)
    assert window.current_route().id==route.id
    assert route.purchases and route.skills
window.route_choice.setCurrentIndex(0)
app.processEvents()
window.grab().save(str(ROOT/'docs/screenshots/treant-premier.png'))
window.tick()
window.overlay.place_top_right()
window.overlay.show()
app.processEvents()
assert 'Talent picks' in window.overlay.talents.text()
window.overlay.grab().save(str(ROOT/'docs/screenshots/treant-talents.png'))
window.close()
print('Ten selectable real Treant builds; first five match the screenshot; no network.')
