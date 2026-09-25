"""Publish the measured hero/position matrix without credentials or raw responses."""
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
rows = json.loads((ROOT / '.local/manual-coverage/results.json').read_text(encoding='utf-8'))
baseline = json.loads((ROOT / '.local/manual-coverage/baseline.json').read_text(encoding='utf-8'))
assert len(rows) == 635 and len({(r['hero_id'], r['role']) for r in rows}) == 635
times = sorted(r['seconds'] for r in rows)
summary = {
    'combinations': len(rows),
    'ten_distinct_builds': sum(r['distinct_sequences'] >= 10 for r in rows),
    'one_to_nine_builds': sum(0 < r['builds'] < 10 for r in rows),
    'zero_builds': sum(r['builds'] == 0 for r in rows),
    'selection_failures': sum(not r['selection_ok'] for r in rows),
    'selected_rows_tested': sum(r['builds'] for r in rows),
    'baseline_ten_distinct': sum(r['distinct_sequences'] >= 10 for r in baseline),
    'median_seconds': round(statistics.median(times), 3),
    'p95_seconds': times[int(.95 * (len(times)-1))],
    'max_seconds': max(times),
}
report = {'date': '2026-09-08', 'summary': summary, 'results': rows}
(ROOT / 'docs/manual-lookup-coverage.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
lines = ['# Manual lookup coverage — 2026-09-08', '',
    f"Tested **{len(rows)} hero/position combinations** using the actual Qt Find builds button and clicks on every returned match row.", '',
    f"**{summary['ten_distinct_builds']}** returned ten distinct purchase/skill sequences; **{summary['one_to_nine_builds']}** returned one to nine; **{summary['zero_builds']}** returned none.",
    f"**{summary['selected_rows_tested']}** result-row selections checked; **{summary['selection_failures']}** failures.", '',
    'First-page discovery came from a same-day live STRATZ census cached for this audit; additional pages and match details used the real provider. The final quota-bounded pass reused same-day raw responses while new queries went live. These are not fully cold lookup benchmarks. No demo data or reference-match overrides were used.', '',
    f"Measured UI completion: median {summary['median_seconds']}s, p95 {summary['p95_seconds']}s, maximum {summary['max_seconds']}s.", '',
    'The baseline found ten builds for '+str(summary['baseline_ten_distinct'])+' combinations. Retesting shortages added older dated examples and hero/position-filtered high-ranked player histories. A final quota-bounded pass broadened player discovery without relaxing match-role checks.', '',
    'The full baseline and the first shortage retest covered all required combinations. The final broader-player pass rechecked 95 of 223 remaining shortages, stopping with 23 hourly API requests left. Other rows retain their earlier verified results; they have not all been retested with the final broader-player fallback.', '',
    'Counts describe the available source sample, not every Dota match. Zero does not prove that the hero was never played in that position. The fallback checks up to 40 active leaderboard players and ten matching games per player. Games require matching hero/position, ranked Immortal bracket, usable purchases and skill sequence; identical purchase/skill sequences do not count twice.', '',
    'Recent games are preferred. Fallback games can extend to the bundled patch-date boundary and carry an older-example warning. STRATZ version metadata conflicts with bundled metadata, so these results are not certified current-patch or numeric-MMR top ten, and are not a reproduction of D2PT coverage.', '',
    '| Hero | Position 1 | Position 2 | Position 3 | Position 4 | Position 5 |',
    '|---|---:|---:|---:|---:|---:|']
for hero in sorted({r['hero'] for r in rows}):
    group = sorted((r for r in rows if r['hero'] == hero), key=lambda r: r['role'])
    lines.append('| ' + hero + ' | ' + ' | '.join(str(r['distinct_sequences']) for r in group) + ' |')
(ROOT / 'docs/MANUAL_LOOKUP_COVERAGE.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
print(json.dumps(summary, indent=2))
