"""Adjustable practice cues, not certified current-map camp timings."""
from PySide6.QtWidgets import QGroupBox, QFormLayout, QCheckBox, QComboBox, QSpinBox, QLabel


def next_window(second, starts, width=2, first=60):
    for minute in range(max(0, second//60-1), second//60+3):
        for offset in sorted(starts):
            start=minute*60+offset
            if start>=first and second<=start+width:
                return start,start+width


def cue(name, second, starts):
    start,end=next_window(second,starts)
    window=f'{start//60}:{start%60:02d}–{end//60}:{end%60:02d}'
    return f'{name}: {"NOW" if second>=start else str(start-second)+"s"} · ~{window}'


class LaneTimers(QGroupBox):
    def __init__(self, settings):
        super().__init__('Lane timers · selected position')
        self.settings=settings
        self.game_team=None
        saved=settings.get('lane_timers',{})
        form=QFormLayout(self)
        self.enabled=QCheckBox('Show lane pull / stack cues in overlay')
        self.enabled.setChecked(saved.get('enabled',True))
        self.side=QComboBox()
        self.side.addItems(['Auto from game','Radiant','Dire'])
        self.side.setCurrentIndex(saved.get('side',0))
        self.safe=QSpinBox(); self.safe.setRange(0,27); self.safe.setValue(saved.get('safe_pull',15))
        self.off=QSpinBox(); self.off.setRange(0,27); self.off.setValue(saved.get('off_pull',18))
        self.stack=QSpinBox(); self.stack.setRange(45,57); self.stack.setValue(saved.get('stack_start',53))
        self.adjust=QSpinBox(); self.adjust.setRange(-3,3); self.adjust.setSuffix(' sec')
        self.adjust.setValue(saved.get('adjust',0))
        form.addRow(self.enabled)
        form.addRow('Your side',self.side)
        note=QLabel('Positions 1 / 5: safe lane small camp. Positions 3 / 4: offlane large camp.\n'
                    'Position 2: no lane timers. Uses the position selected in Builds. No calibration needed.')
        note.setWordWrap(True); form.addRow(note)
        form.addRow('Safe-lane pull starts at :ss and :ss+30',self.safe)
        form.addRow('Offlane pull starts at :ss and :ss+30',self.off)
        form.addRow('Stack window starts at :ss',self.stack)
        form.addRow('Personal timing adjustment',self.adjust)
        note=QLabel('Approximate two-second practice windows; not verified for the current map.\n'
                    'Pull cues stop at 10:00; stack cues continue. Camp availability is unknown.\n'
                    'Pull toward your lane; stack out of the spawn box.\n'
                    'Melee: be in reach before the cue. Ranged: allow for attack / projectile travel.')
        note.setWordWrap(True); form.addRow(note)
        for spin in (self.safe,self.off,self.stack,self.adjust):spin.valueChanged.connect(self.persist)
        self.side.currentIndexChanged.connect(self.persist)
        self.enabled.toggled.connect(self.persist)
        self.persist()

    def ingest(self,payload):
        team=str((payload.get('player') or {}).get('team_name','')).capitalize()
        if team in ('Radiant','Dire'):self.game_team=team
        if (payload.get('map') or {}).get('game_state') in ('DOTA_GAMERULES_STATE_DISCONNECT','DOTA_GAMERULES_STATE_WAIT_FOR_PLAYERS_TO_LOAD'):
            self.game_team=None

    def persist(self,*_):
        self.settings['lane_timers']=dict(enabled=self.enabled.isChecked(),side=self.side.currentIndex(),
            safe_pull=self.safe.value(),off_pull=self.off.value(),stack_start=self.stack.value(),adjust=self.adjust.value())

    def text(self,second,status,role,hero,drafting=False):
        if not self.enabled.isChecked() or role not in (1,3,4,5) or drafting:return ''
        if second is None or second<0:return 'LANE TIMERS · waiting for game start'
        if status not in ('Game clock','Manual estimate'):
            return 'LANE TIMERS · '+status+' · countdown held'
        side=self.side.currentText() if self.side.currentIndex() else self.game_team
        safe=role in (1,5)
        lane=('bottom' if side=='Radiant' else 'top') if safe else ('top' if side=='Radiant' else 'bottom')
        camp='small' if safe else 'large'
        location=f'{side} {lane}' if side else 'Safe lane' if safe else 'Offlane'
        pull=max(0,min(27,(self.safe.value() if safe else self.off.value())+self.adjust.value()))
        stack=max(45,min(57,self.stack.value()+self.adjust.value()))
        lines=[f'{location} · {camp} camp · Approx.']
        if second<600:lines.append(cue('Pull',second,[pull,pull+30]))
        lines.append(cue('Stack',second,[stack]))
        return '\n'.join(lines)
