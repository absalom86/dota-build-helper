"""Inspect opening-buy and automatic draft views using saved real role data."""
import os,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['DOTA_HELPER_HOME']=str(ROOT/'.local/draft-start-ui')
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from dota_helper.app import MainWindow
from dota_helper.providers import Demo
from dota_helper.draft_meta import role_meta
app=QApplication([])
for font in ('segoeui.ttf','segoeuib.ttf'):
    QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR'])/'Fonts'/font))
w=MainWindow(start_services=False)
w.routes=Demo().routes(1,1,0)[0]
w.session.accept_routes(w.routes)
w.preview.setChecked(True)
w.tick()
w.overlay.place_top_right()
app.processEvents()
assert w.overlay.initial_buy.text()==w.overlay.initial_buy.toolTip()
assert w.overlay.initial_buy.height()>=w.overlay.initial_buy.fontMetrics().height()*2
w.overlay.grab().save(str(ROOT/'docs/screenshots/initial-buy-highlight.png'))
class SavedClient:
    def query(self,*args,**kwargs):
        return json.loads((ROOT/'.local/stratz-inspection/draft-day-probe.json').read_text())['data']
w.role.setCurrentIndex(w.role.findData(2))
w.draft.meta_rows,w.draft.meta_status=role_meta(2,SavedClient())
w.draft.meta_active=True
w.draft.render_meta()
w.tick()
app.processEvents()
assert 'MOST PLAYED' in w.overlay.items.text()
assert w.overlay.initial_buy.isHidden()
w.overlay.grab().save(str(ROOT/'docs/screenshots/draft-role-meta.png'))
w.close()
print('Opening buy and real mid-role draft overlay rendered successfully.')
