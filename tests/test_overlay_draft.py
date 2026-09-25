import time
from PySide6.QtWidgets import QApplication
from dota_helper.app import MainWindow, Overlay


def test_talent_picks_are_visible_and_follow_selected_route(tmp_path,monkeypatch):
    from dota_helper.providers import Demo
    from dota_helper.catalog import ability_name
    monkeypatch.setattr('dota_helper.app.LOCAL',tmp_path)
    window=MainWindow(start_services=False)
    routes,_=Demo().routes(1,1,0)
    talent='special_bonus_unique_bounty_hunter'
    routes[0].skills+= [talent,talent,'special_bonus_attributes']
    window.routes=routes
    window.session.accept_routes(routes)
    window.tick()
    assert window.overlay.talents.text().count(ability_name(talent))==1
    assert 'Attributes' not in window.overlay.talents.text()
    window.session.learned[talent]=1
    window.tick()
    assert 'Done · '+ability_name(talent) in window.overlay.talents.text()
    window.session.choose(routes[1].id)
    window.tick()
    assert window.overlay.talents.text()=='Talent picks not recorded'
    window.routes=[]
    window.tick()
    assert window.overlay.talents.isHidden()
    window.close()


def test_build_summary_hides_consumables_recipes_and_upgrade_parts():
    from dota_helper.providers import Demo
    from dota_helper.models import Purchase
    from dota_helper.builds import overlay_build_purchases
    routes,_=Demo().routes(1,1,0)
    route=routes[0]
    keys=['tango','ward_observer','boots','magic_wand','blade_of_alacrity','yasha',
          'recipe_manta','manta','blink','aghanims_shard','clarity','ogre_axe',
          'black_king_bar','ultimate_scepter','ultimate_scepter_2']
    route.purchases=[Purchase(k,i*60,1) for i,k in enumerate(keys)]
    assert [p.key for p in overlay_build_purchases(route)]==[
        'boots','magic_wand','manta','blink','aghanims_shard','black_king_bar',
        'ultimate_scepter','ultimate_scepter_2']
    # Filtering presentation must not remove the exact source purchase history.
    assert [p.key for p in route.purchases]==keys


def test_full_build_keeps_completed_items_and_only_initial_wards(tmp_path,monkeypatch):
    from dota_helper.providers import Demo
    from dota_helper.models import Purchase
    monkeypatch.setattr('dota_helper.app.LOCAL',tmp_path)
    window=MainWindow(start_services=False)
    routes,_=Demo().routes(1,1,0)
    routes[0].purchases.insert(0,Purchase('ward_observer',-60,1))
    routes[0].purchases.append(Purchase('ward_observer',1800,2))
    routes[0].purchases.append(Purchase('ward_sentry',1900,1))
    window.routes=routes
    window.session.accept_routes(routes)
    window.tick()
    assert 'Boots of Speed' in window.overlay.items.text()
    assert 'Start' not in window.overlay.items.text()
    assert not window.overlay.initial_buy.isHidden()
    assert window.overlay.initial_buy.wordWrap()
    assert window.overlay.initial_buy.text()==window.overlay.initial_buy.toolTip()
    assert 'Tango' in window.overlay.initial_buy.toolTip()
    assert window.overlay.initial_buy.toolTip().count('Observer Ward')==1
    assert 'Observer Ward' not in window.overlay.items.text()
    assert 'Sentry Ward' not in window.overlay.items.text()
    assert 'Skull Basher' in window.overlay.items.text()
    assert not window.session.completed
    boots=next(p for p in routes[0].purchases if p.key=='boots')
    window.session.completed.add(boots.identity)
    window.tick()
    assert '✓ Boots of Speed' in window.overlay.items.text()
    assert 'Power Treads' in window.overlay.items.text()
    window.manual_second=59
    window.tick()
    assert not window.overlay.initial_buy.isHidden()
    window.manual_second=60
    window.tick()
    assert window.overlay.initial_buy.isHidden()
    assert 'Skull Basher' in window.overlay.items.text()
    window.manual_second=-30
    window.tick()
    assert not window.overlay.initial_buy.isHidden()
    window.close()


def test_overlay_migrates_to_narrow_right_and_keeps_custom_position():
    settings={'overlay_x':18,'overlay_y':18,'overlay_w':350}
    overlay=Overlay(settings)
    bounds=overlay.screen().availableGeometry()
    assert overlay.width()==270
    assert overlay.x()==bounds.right()-281
    assert overlay.y()==bounds.top()+160
    assert settings['overlay_layout_version']==3
    overlay.close()
    settings.update(overlay_x=50,overlay_y=70)
    overlay=Overlay(settings)
    assert (overlay.x(),overlay.y())==(50,70)
    overlay.close()


def test_bot_draft_reports_candidate_then_fetches_confirmed_hero(tmp_path,monkeypatch):
    monkeypatch.setattr('dota_helper.app.LOCAL',tmp_path)
    window=MainWindow(start_services=False)
    fetched=[]
    window.fetch=lambda:fetched.append(window.hero.currentData())
    payload={'hero':{'id':48,'level':1},'player':{'steamid':'test'},
             'map':{'matchid':'0','clock_time':-70,'game_state':'DOTA_GAMERULES_STATE_HERO_SELECTION'}}
    window.on_gsi(payload)
    assert 'Draft data received' in window.gsi_status and fetched==[]
    payload['map']['game_state']='DOTA_GAMERULES_STATE_STRATEGY_TIME'
    window.on_gsi(payload)
    assert window.hero.currentData()==48 and fetched==[48]
    window.close()
    QApplication.instance().processEvents()

def test_early_components_expire_but_full_build_stays():
    from dota_helper.providers import Demo
    from dota_helper.models import Purchase
    from dota_helper.builds import overlay_build_purchases
    routes,_=Demo().routes(1,1,0)
    route=routes[0]
    route.purchases=[Purchase(k,t,1) for k,t in [('branches',-60),('circlet',30),('gauntlets',90),('flask',120),('ward_observer',130),('black_king_bar',1500),('flask',1600)]]
    assert [p.key for p in overlay_build_purchases(route,299)]==['circlet','gauntlets','flask','black_king_bar']
    assert [p.key for p in overlay_build_purchases(route,300)]==['black_king_bar']


def test_optional_raindrops_uses_selected_enemy_and_hides_when_owned(tmp_path,monkeypatch):
    from dota_helper.providers import Demo
    monkeypatch.setattr('dota_helper.app.LOCAL',tmp_path)
    window=MainWindow(start_services=False)
    routes,_=Demo().routes(1,1,0)
    routes[0].demo=False
    window.routes=routes
    window.session.accept_routes(routes)
    window.tick()
    assert 'Optional' not in window.overlay.note.text()
    combo=window.draft.enemies[0]
    combo.setCurrentIndex(combo.findData(22))
    window.tick()
    assert 'Optional' not in window.overlay.note.text()  # Missing inventory is not an empty inventory.
    window.session.inventory_at = time.monotonic()
    window.tick()
    assert 'Infused Raindrops' in window.overlay.note.text()
    assert 'Example benchmarks' not in window.overlay.note.text()
    window.session.inventory['infused_raindrop']=1
    window.tick()
    assert 'Optional' not in window.overlay.note.text()
    window.session.inventory.clear()
    window.manual_second=600
    window.tick()
    assert 'Optional' not in window.overlay.note.text()
    window.close()

def test_stratz_starting_quantities_survive_same_second_and_display(tmp_path,monkeypatch):
    from test_stratz import match
    from dota_helper.stratz import normalize_stratz
    from dota_helper.catalog import ITEMS
    from dota_helper.builds import starting_buy_text
    m=match()
    player=m['players'][0]
    player['stats']['itemPurchases'] += [{'time':-89,'itemId':ITEMS['branches']['id']} for _ in range(5)]
    player['stats']['itemPurchases'].append({'time':100,'itemId':ITEMS['branches']['id']})
    route=normalize_stratz(m,player,{})
    assert 'Iron Branch ×5' in starting_buy_text(route)
    monkeypatch.setattr('dota_helper.app.LOCAL',tmp_path)
    window=MainWindow(start_services=False)
    window.routes=[route]
    window.session.accept_routes([route])
    window.render_routes()
    window.tick()
    assert 'Iron Branch ×5' in window.match_table.item(0,3).text()
    assert 'Iron Branch ×5' in window.overlay.initial_buy.text()
    assert 'Tango ×1' in window.overlay.initial_buy.text()
    window.close()
