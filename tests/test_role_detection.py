from dota_helper.role_detection import parse_role
from dota_helper.app import MainWindow

def tsv(words):
    return 'block_num\tpar_num\tline_num\tconf\ttext\n'+''.join(f'1\t1\t1\t{conf}\t{word}\n' for word,conf in words)

def test_exact_label_and_confidence():
    assert parse_role(tsv([('Hard',95),('Support',92)]))==5
    assert parse_role(tsv([('Support',95)]))==4
    assert parse_role(tsv([('Hard',45),('Support',95)])) is None
    assert parse_role(tsv([('Player',95),('Support',95)])) is None

def test_manual_override_blocks_pending_role_result(tmp_path,monkeypatch):
    monkeypatch.setattr('dota_helper.app.LOCAL',tmp_path)
    monkeypatch.setattr('dota_helper.app.dota_active',lambda:True)
    w=MainWindow(start_services=False)
    w.fetch=lambda:None
    w.settings['role_region']={'left':0,'top':0,'width':100,'height':30}
    w.role_ocr.setChecked(True)
    w.draft_phase=True
    w.role_state_at=__import__('time').monotonic()
    jobs=[]
    w.launch_worker=lambda *a:jobs.append(a)
    for _ in range(2):
        w.detect_role();jobs[-1][1](5)
    assert w.role.currentData()==1
    w.detect_role()
    w.role.setCurrentIndex(w.role.findData(3))
    w.role.activated.emit(w.role.currentIndex())
    jobs[-1][1](5)
    assert w.role.currentData()==3 and w.role_manual
    w.close()
