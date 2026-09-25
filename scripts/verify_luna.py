"""Compare browser-observed Luna reference IDs using independent STRATZ records."""
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
IDS=[8973859403,8972773416,8958950792,8946860406,8944752572,
     8988176344,8988159352,8988114560,8988103578,8988044068]
profile=ROOT/'.local/luna-ui'
profile.mkdir(exist_ok=True)
shutil.copyfile(ROOT/'.local/stratz-key.bin',profile/'stratz-key.bin')
os.environ['DOTA_HELPER_HOME']=str(profile)
os.environ['QT_QPA_PLATFORM']='offscreen'
(profile/'stratz-reference-matches.json').write_text(json.dumps({'48':IDS}))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from dota_helper.app import MainWindow
from dota_helper.catalog import ability_name, item_name

app=QApplication([])
for font in ('segoeui.ttf','segoeuib.ttf'):
    QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR'])/'Fonts'/font))
window=MainWindow(start_services=False)
window.resize(1500,1000)
window.hero.setCurrentIndex(window.hero.findData(48))
window.role.setCurrentIndex(window.role.findData(1))
window.show()
start=time.monotonic()
window.find_button.click()
while window.fetching and time.monotonic()-start<12:
    app.processEvents()
    time.sleep(.01)
assert not window.fetching and len(window.routes)>=5,window.status.text()
assert all(r.tournament for r in window.routes)
rows=[]
for i,r in enumerate(window.routes):
    item=window.match_table.item(i,0)
    window.match_table.scrollToItem(item)
    app.processEvents()
    QTest.mouseClick(window.match_table.viewport(),Qt.MouseButton.LeftButton,pos=window.match_table.visualItemRect(item).center())
    assert window.current_route().id==r.id
    rows.append({'match_id':r.match_ids[0],'player':r.player,'reference':r.match_ids[0] in IDS,
                 'starting':[item_name(p.key) for p in r.purchases if p.time<0],
                 'purchases':[{'item':item_name(p.key),'seconds':p.time} for p in r.purchases if p.time>=0],
                 'first_ten_skills':[ability_name(s) for s in r.skills[:10]],'patch':r.patch_label})
assert [r['match_id'] for r in rows[:5]]==IDS[:5]
window.route_choice.setCurrentIndex(0)
app.processEvents()
window.grab().save(str(ROOT/'docs/screenshots/luna-reference.png'))
report={'seconds':round(time.monotonic()-start,3),'status':window.status.text(),'selected_rows':len(rows),'rows':rows}
(ROOT/'docs/luna-comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'seconds':report['seconds'],'status':report['status'],'games':[(r['match_id'],r['player']) for r in rows],'first_skills':rows[0]['first_ten_skills']}))
window.close()
app.processEvents()
