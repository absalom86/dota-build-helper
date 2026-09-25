"""Reopen real saved Luna results without credentials or network access."""
import os
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
profile=ROOT/'.local/history-ui'
(profile/'cache').mkdir(parents=True,exist_ok=True)
shutil.copyfile(ROOT/'.local/luna-ui/cache/tournaments-v1-48-1.json',profile/'cache/tournaments-v1-48-1.json')
os.environ['DOTA_HELPER_HOME']=str(profile)
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from dota_helper.app import MainWindow
from dota_helper.stratz import Stratz
Stratz.query=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('History must not access network'))
app=QApplication([])
for font in ('segoeui.ttf','segoeuib.ttf'):
    QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR'])/'Fonts'/font))
window=MainWindow(start_services=False)
window.resize(1500,1000)
window.show()
window.open_saved_search()
assert window.hero.currentData()==48 and len(window.routes)==5
window.route_choice.setCurrentIndex(2)
selected=window.current_route().id
window.close()
app.processEvents()
window=MainWindow(start_services=False)
window.resize(1500,1000)
window.show()
window.open_saved_search()
assert window.current_route().id==selected
app.processEvents()
window.grab().save(str(ROOT/'docs/screenshots/search-history.png'))
window.close()
app.processEvents()
print('Five real tournament builds reopened without network; selected build survived restart.')
