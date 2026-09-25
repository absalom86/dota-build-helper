"""Conservative OCR for a user-calibrated assigned-role label (English)."""
import csv
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def parse_role(tsv):
    lines={}
    for row in csv.DictReader(io.StringIO(tsv),delimiter='\t'):
        word=row.get('text','').strip().lower()
        if not word:continue
        try:confidence=float(row['conf'])
        except (ValueError,KeyError):continue
        key=tuple(row.get(k) for k in ('block_num','par_num','line_num'))
        lines.setdefault(key,[]).append((word,confidence))
    found=set()
    names={'safe lane':1,'safelane':1,'carry':1,'mid lane':2,'midlane':2,'mid':2,
           'off lane':3,'offlane':3,'soft support':4,'support':4,'hard support':5}
    for words in lines.values():
        text=' '.join(w for w,c in words).strip(' :.-')
        for prefix in ('your role: ','role: '):
            if text.startswith(prefix):text=text[len(prefix):]
        if text in names and min(c for w,c in words)>=80:found.add(names[text])
    return next(iter(found)) if len(found)==1 else None


def read_role(frame):
    executable=shutil.which('tesseract') or str(Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Tesseract-OCR/tesseract.exe')
    if not Path(executable).is_file():
        raise RuntimeError('Role OCR needs Tesseract with English language data installed. Manual position selection is available.')
    with tempfile.TemporaryDirectory(prefix='dota-role-') as folder:
        path=Path(folder)/'role.png'
        frame.save(path)
        result=subprocess.run([executable,str(path),'stdout','-l','eng','--psm','6','tsv'],
            capture_output=True,text=True,timeout=4,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError('Role OCR failed; check Tesseract English language data.')
    return parse_role(result.stdout)
