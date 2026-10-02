"""Replay the reported starting-buy cases from a saved profile without network.

The input profile is read-only. Settings, screenshots and the report use an
isolated output profile. Run with --data pointing to the installed app's data.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('.local/starting-items-verification'))
    args = parser.parse_args()
    source, output = args.data.resolve(), args.output.resolve()
    if output == source or source in output.parents:
        raise ValueError('Verification output must be outside the source profile.')
    output.mkdir(parents=True, exist_ok=True)
    os.environ['DOTA_HELPER_HOME'] = str(output / 'profile')
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication
    from dota_helper import starting_items, quantity_evidence
    from dota_helper.app import MainWindow
    from dota_helper.builds import starting_buy_text
    from dota_helper.guides import build_text
    from dota_helper.history import decode

    files = [source / name for name in ('search-history.json', 'quantity-evidence.json', 'starting-items.json')]
    def fingerprints():
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.exists()}
    before = fingerprints()
    entries = json.loads((source / 'search-history.json').read_text(encoding='utf-8'))
    routes = {(r.match_ids[0], r.hero_id): r for entry in entries for r in decode(entry) if r.match_ids}
    starting_items.user_data_dir = lambda: source
    quantity_evidence.user_data_dir = lambda: source
    starting_items.load.cache_clear()
    quantity_evidence._load.cache_clear()
    cases = [
        (8957749452, 145, {'quelling_blade': 1, 'tango': 1, 'branches': 2, 'magic_stick': 1, 'faerie_fire': 1}),
        (8944602781, 32, {'branches': 5, 'ward_observer': 1, 'tango': 1}),
        (8955197224, 145, {'magic_wand': 1, 'faerie_fire': 2}),
    ]
    app = QApplication([])
    for name in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf'):
        font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / name
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont('Segoe UI', 10))
    window = MainWindow(start_services=False)
    window.timer.stop()
    window.capture_timer.stop()
    window.draft.meta_active = False
    window.draft.overlay_enabled.setChecked(False)
    results = []
    try:
        for match, hero, expected in cases:
            route = routes[(match, hero)]
            original = [vars(p).copy() for p in route.purchases]
            evidence = starting_items.summary(route)
            assert evidence['counts'] == expected, (match, evidence)
            assert evidence['provenance'] == 'recovered'
            window.routes = [route]
            window.session.reset(hero)
            window.session.choose(route.id)
            window.manual_second = 0
            window.render_routes()
            window.tick()
            window.overlay.fit_content(QRect(0, 0, 1280, 720))
            assert 'OpenDota quantities' in window.overlay.initial_buy.text()
            assert 'estimated' not in window.overlay.initial_buy.text()
            image = output / f'{match}-starting-buy.png'
            window.overlay.initial_buy.grab().save(str(image))
            guide = output / f'{match}.build'
            guide.write_text(build_text(route), encoding='utf-8')
            assert [vars(p) for p in route.purchases] == original
            results.append({'match_id': match, 'hero_id': hero,
                            'recorded': starting_items.recorded_counts(route),
                            'recovered': evidence['counts'], 'source': evidence['source'],
                            'display': starting_buy_text(route), 'image': str(image), 'guide': str(guide)})
    finally:
        window.close()
        app.processEvents()
    assert fingerprints() == before, 'Input profile was changed'
    report = {'ok': True, 'source_profile_unchanged': True, 'cases': results}
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    main()
