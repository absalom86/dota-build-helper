"""Verify real cached premier Bounty Hunter builds and selection without network."""
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['DOTA_HELPER_HOME']=str(ROOT/'.local/bounty-ui')
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from dota_helper.history import SearchHistory,decode
from dota_helper.app import MainWindow
raw=json.loads((ROOT/'.local/cache/tournaments-v1-62-4.json').read_text())
routes=decode(dict(hero=62,role=4,source=0,routes=raw['routes']))
assert [r.match_ids[0] for r in routes[:5]]==[8958950792,8956943534,8956821666,8956096810,8955934230]
assert len(routes)==10
history=SearchHistory(Path(os.environ['DOTA_HELPER_HOME']))
history.save(62,4,0,routes,routes[0].id,'Verified tournament index')
app=QApplication([])
for font in ('segoeui.ttf','segoeuib.ttf'):
    QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR'])/'Fonts'/font))
window=MainWindow(start_services=False)
window.resize(1500,1000)
window.show()
window.hero.setCurrentIndex(window.hero.findData(62))
window.role.setCurrentIndex(window.role.findData(4))
window.launch_worker=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('Cached lookup must not fetch'))
window.fetch()
for index,route in enumerate(routes):
    window.route_choice.setCurrentIndex(index)
    assert window.current_route().id==route.id
    assert route.purchases and route.skills
window.route_choice.setCurrentIndex(0)
app.processEvents()
window.grab().save(str(ROOT/'docs/screenshots/bounty-ti.png'))
window.tick()
window.overlay.place_top_right()
window.overlay.show()
app.processEvents()
assert 'Talent picks' in window.overlay.talents.text()
window.overlay.grab().save(str(ROOT/'docs/screenshots/bounty-talents.png'))
window.close()
print('Ten selectable real Bounty Hunter builds; TI games lead the list; no network.')
