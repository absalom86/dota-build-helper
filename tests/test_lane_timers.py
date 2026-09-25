from dota_helper.lane_timers import next_window, LaneTimers
from PySide6.QtWidgets import QLabel

def test_window_boundaries_and_first_spawn():
    assert next_window(0,[15,45])==(75,77)
    assert next_window(77,[15,45])==(75,77)
    assert next_window(78,[15,45])==(105,107)

def test_role_mapping_without_coordinates_and_old_settings(qt_application):
    t=LaneTimers({'lane_timers':{'auto_camp':True,'supports':True}})
    for role in (1,5):
        assert 'Safe lane' in t.text(75,'Game clock',role,{})
        assert 'NOW' in t.text(75,'Game clock',role,{})
    for role in (3,4):
        assert 'Offlane' in t.text(78,'Game clock',role,{})
        assert 'NOW' in t.text(78,'Game clock',role,{})
    assert t.text(75,'Game clock',2,{})==''
    t.ingest({'player':{'team_name':'dire'}})
    assert 'Dire top' in t.text(75,'Game clock',5,{})
    assert 'Dire bottom' in t.text(78,'Game clock',4,{})
    assert 'countdown held' in t.text(75,'Paused',5,{})
    assert 'Pull:' not in t.text(600,'Game clock',5,{})
    t.close()


def test_compact_cues_retain_times_and_keep_instructions_in_settings(qt_application):
    t=LaneTimers({})
    t.ingest({'player':{'team_name':'radiant'}})
    assert t.text(74,'Game clock',5,{'attack_type':'Melee'}).splitlines()==[
        'Radiant bottom · small camp · Approx.',
        'Pull: 1s · ~1:15–1:17',
        'Stack: 39s · ~1:53–1:55',
    ]
    assert t.text(600,'Game clock',4,{}).splitlines()==[
        'Radiant top · large camp · Approx.',
        'Stack: 53s · ~10:53–10:55',
    ]
    assert len(t.text(75,'Manual estimate',1,{}).splitlines())==3
    help_text='\n'.join(label.text() for label in t.findChildren(QLabel))
    assert 'Camp availability is unknown' in help_text
    assert 'Melee: be in reach' in help_text
    assert 'Ranged: allow for attack / projectile travel' in help_text
    assert 'stack out of the spawn box' in help_text
    t.close()


def test_compact_cues_preserve_guards_and_adjustments(qt_application):
    t=LaneTimers({})
    for second in (None,-1):
        assert t.text(second,'Game clock',5,{})=='LANE TIMERS · waiting for game start'
    for status in ('Paused','Stale game clock'):
        assert 'countdown held' in t.text(75,status,5,{})
        assert 'Pull:' not in t.text(75,status,5,{})
    assert t.text(75,'Game clock',5,{},drafting=True)==''
    t.side.setCurrentText('Dire')
    t.adjust.setValue(2)
    lines=t.text(75,'Game clock',5,{}).splitlines()
    assert lines[0]=='Dire top · small camp · Approx.'
    assert lines[1]=='Pull: 2s · ~1:17–1:19'
    assert lines[2]=='Stack: 40s · ~1:55–1:57'
    t.enabled.setChecked(False)
    assert t.text(75,'Game clock',5,{})==''
    t.close()
