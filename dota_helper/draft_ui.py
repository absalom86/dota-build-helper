from html import escape
import threading

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QGridLayout, QLayout, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QTextBrowser,
)

from .catalog import HEROES, ROLES
from .draft_meta import role_meta, leaders
from .draft import DraftProvider


def hero_name(hero_id):
    return HEROES[str(hero_id)]["localized_name"]


def hero_combo(empty):
    combo = QComboBox()
    combo.addItem(empty, None)
    for key, hero in sorted(HEROES.items(), key=lambda kv: kv[1]["localized_name"]):
        combo.addItem(hero["localized_name"], int(key))
    return combo


class DraftPanel(QWidget):
    use_hero = Signal(int)

    def __init__(self, launch_worker, parent=None):
        super().__init__(parent)
        self.launch_worker = launch_worker
        self.cancel = threading.Event()
        self.revision = 0
        self.busy = False
        self.picks = []
        self.result_stale = False
        self.blocked = set()
        self.provider_factory = DraftProvider
        self.meta_role=1
        self.meta_rows=[]
        self.meta_status='Loading role statistics…'
        self.meta_active=True
        self.meta_busy=False
        self.meta_requested_role=None
        self.meta_provider=role_meta
        self.auto_meta=True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.meta_label=QTextBrowser()
        self.meta_label.setMinimumHeight(220)
        self.meta_label.setMaximumHeight(260)
        layout.addWidget(self.meta_label)
        self.sync_status = QLabel("Waiting for game draft data · manual picks available below")
        self.sync_status.setWordWrap(True)
        layout.addWidget(self.sync_status)
        title = QLabel("ENEMY PICKS")
        title.setObjectName("eyebrow")
        layout.addWidget(title)
        row = QGridLayout()
        self.enemies = [hero_combo(f"Enemy {i + 1} — empty") for i in range(5)]
        for i, combo in enumerate(self.enemies):
            combo.currentIndexChanged.connect(self.changed)
            row.addWidget(combo, i // 3, i % 3)
        layout.addLayout(row)
        controls = QGridLayout()
        self.pool = QComboBox()
        self.pool.addItems(["Any hero", "Carry", "Support"])
        self.pool.setToolTip("Broad hero tags from metadata, not measured position-specific matchups.")
        self.pool.currentIndexChanged.connect(self.changed)
        controls.addWidget(QLabel("Hero pool"),0,0)
        controls.addWidget(self.pool,0,1)
        self.auto = QCheckBox("Update when picks change")
        self.auto.setChecked(True)
        controls.addWidget(self.auto,0,2)
        self.refresh = QPushButton("Suggest picks")
        self.refresh.setObjectName("primary")
        self.refresh.clicked.connect(self.search)
        controls.addWidget(self.refresh,1,0)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.stop)
        controls.addWidget(cancel,1,1)
        clear = QPushButton("Clear draft")
        clear.clicked.connect(self.clear)
        controls.addWidget(clear,1,2)
        layout.addLayout(controls)
        unavailable = QGridLayout()
        self.exclude = hero_combo("Ally pick / banned hero…")
        unavailable.addWidget(self.exclude,0,0)
        add = QPushButton("Exclude hero")
        add.clicked.connect(self.add_excluded)
        unavailable.addWidget(add,0,1)
        self.exclusions = QComboBox()
        self.exclusions.setMinimumWidth(170)
        unavailable.addWidget(self.exclusions,1,0)
        remove = QPushButton("Remove exclusion")
        remove.clicked.connect(self.remove_excluded)
        unavailable.addWidget(remove,1,1)
        layout.addLayout(unavailable)
        note = QLabel("Historical tracked matches · rolling year · mixed patches/ranks. Carry/Support are broad hero tags.\n"
                      "Scores summarize separate matchups, not your chance of winning this draft. Ally synergy is not modeled.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout.addWidget(note)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Suggested hero", "Matchup score", "Strongest vs", "Weakest vs", "Min. games / pair"])
        self.table.horizontalHeaderItem(1).setToolTip(
            "Each pair: (candidate wins + 50) / (games + 100). Average equally across selected enemies, times 100. "
            "Not a draft win probability; pair samples may overlap.")
        self.table.setMinimumHeight(130)
        self.table.setStyleSheet("QTableWidget { selection-background-color: #345463; }")
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.show_details)
        layout.addWidget(self.table, 1)
        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(True)
        self.details.setMaximumHeight(105)
        self.details.setMinimumHeight(65)
        layout.addWidget(self.details)
        actions = QHBoxLayout()
        self.choose = QPushButton("Use selected hero in Builds")
        self.choose.setEnabled(False)
        self.choose.clicked.connect(self.choose_hero)
        actions.addWidget(self.choose)
        self.overlay_enabled = QCheckBox("Show suggestions in overlay")
        actions.addWidget(self.overlay_enabled)
        actions.addStretch()
        layout.addLayout(actions)
        self.status = QLabel("Role rankings load automatically. Enemy picks are optional for historical matchup suggestions; enter them manually.")
        self.status.setWordWrap(True)
        self.status.setObjectName("status")
        layout.addWidget(self.status)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(700)
        self.debounce.timeout.connect(self.search)

    def set_role(self,role):
        self.meta_role=role
        self.meta_rows=[]
        self.meta_status='Loading role statistics…'
        self.render_meta()
        if self.auto_meta:
            self.refresh_meta()

    def ingest_draft(self, payload):
        draft = payload.get('draft')
        team = (payload.get('player') or {}).get('team_name')
        own = {'radiant': 'team2', 'dire': 'team3'}.get(str(team).lower())
        if not isinstance(draft, dict) or not draft or not own:
            self.sync_status.setText('Game draft picks unavailable · enter visible picks manually')
            return
        enemy = 'team3' if own == 'team2' else 'team2'
        if not isinstance(draft.get(enemy), dict):
            return
        def ids(data, prefix):
            return [data.get(f'{prefix}{i}_id') for i in range(10)
                    if type(data.get(f'{prefix}{i}_id')) is int
                    and str(data[f'{prefix}{i}_id']) in HEROES]
        enemies = list(dict.fromkeys(ids(draft[enemy], 'pick')))[:5]
        blocked = set()
        for key in ('team2', 'team3'):
            data = draft.get(key)
            if isinstance(data, dict):
                blocked.update(ids(data, 'ban'))
                if key == own:
                    blocked.update(ids(data, 'pick'))
        changed = False
        for i, combo in enumerate(self.enemies):
            hero = enemies[i] if i < len(enemies) else None
            if combo.currentData() != hero:
                combo.blockSignals(True)
                combo.setCurrentIndex(max(0, combo.findData(hero)))
                combo.blockSignals(False)
                changed = True
        previous = getattr(self, '_game_blocked', set())
        if previous != blocked:
            self.blocked = (self.blocked - previous) | blocked
            self._game_blocked = blocked
            self.exclusions.clear()
            for hero in sorted(self.blocked):
                self.exclusions.addItem(hero_name(hero), hero)
            changed = True
        self.sync_status.setText(f'Game draft synced · {len(enemies)} enemy picks · {len(blocked)} allies / bans')
        if changed:
            self.render_meta()
            self.changed()

    def refresh_meta(self):
        if self.meta_busy:
            return
        role=self.meta_role
        self.meta_busy=True
        self.meta_requested_role=role
        def done(result):
            self.meta_busy=False
            if role!=self.meta_role:
                self.refresh_meta()
                return
            self.meta_rows,self.meta_status=result
            self.render_meta()
        def failed(message):
            self.meta_busy=False
            if role!=self.meta_role:
                self.refresh_meta()
                return
            self.meta_status='Role stats unavailable: '+message
            self.render_meta()
        self.launch_worker(lambda _:self.meta_provider(role),done,failed)

    def meta_text(self):
        blocked=self.blocked | {c.currentData() for c in self.enemies if c.currentData()}
        wins,played=leaders(self.meta_rows,blocked)
        def rows(values):
            return '\n'.join(f"{hero_name(r['hero_id'])} · {r['rate']:.1%} · {r['games']:,} games" for r in values)
        if not self.meta_rows:
            return self.meta_status
        return ('TOP WIN RATE · 100+ games\n'+(rows(wins) or 'Not enough games')+
                '\n\nMOST PLAYED\n'+rows(played))

    def render_meta(self):
        wins, played = leaders(self.meta_rows, self.blocked | {c.currentData() for c in self.enemies})
        def column(title, rows):
            lines = [escape(f"{hero_name(r['hero_id'])} · {r['rate']:.1%} · {r['games']:,} games") for r in rows]
            return '<td width="50%" valign="top"><b>'+title+'</b><br>'+'<br>'.join(lines)+'</td>'
        self.meta_label.setHtml(escape(f'{ROLES[self.meta_role]} · {self.meta_status}')+
                                '<br><br><table width="100%"><tr>'+column('TOP WIN RATE · 100+ games',wins)+
                                column('MOST PLAYED',played)+'</tr></table>')

    def changed(self):
        self.revision += 1
        self.cancel.set()
        self.picks = []
        self.result_stale = False
        self.table.setRowCount(0)
        self.details.clear()
        self.choose.setEnabled(False)
        self.status.setText("Draft changed. Updating suggestions…" if self.auto.isChecked() else "Draft changed. Click Suggest picks.")
        self.debounce.stop()
        if self.auto.isChecked():
            self.debounce.start()

    def add_excluded(self):
        hero_id = self.exclude.currentData()
        if hero_id and hero_id not in self.blocked:
            self.blocked.add(hero_id)
            self.exclusions.addItem(hero_name(hero_id), hero_id)
            self.changed()

    def remove_excluded(self):
        hero_id = self.exclusions.currentData()
        if hero_id:
            self.blocked.discard(hero_id)
            self.exclusions.removeItem(self.exclusions.currentIndex())
            self.changed()

    def clear(self):
        for combo in self.enemies:
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self.blocked.clear()
        self.exclusions.clear()
        self.changed()

    def stop(self):
        self.revision += 1
        self.cancel.set()
        self.debounce.stop()
        self.status.setText("Draft search cancelled.")

    def search(self):
        self.debounce.stop()
        if self.busy:
            # Wait for the cancelled request to finish before starting another.
            self.debounce.start()
            return
        enemies = [c.currentData() for c in self.enemies if c.currentData()]
        if not enemies:
            self.refresh_meta()
            self.status.setText("Showing role stats. Add enemy picks for historical matchup suggestions.")
            return
        if len(enemies) != len(set(enemies)):
            self.status.setText("An enemy hero is selected twice. Choose different heroes.")
            return
        if set(enemies) & self.blocked:
            self.status.setText("A hero cannot be both an enemy pick and an ally/ban exclusion. Remove the conflict.")
            return
        self.busy = True
        self.picks = []
        self.table.setRowCount(0)
        self.details.clear()
        self.choose.setEnabled(False)
        self.refresh.setEnabled(False)
        self.cancel = threading.Event()
        cancel, revision = self.cancel, self.revision
        excluded, pool = set(self.blocked), self.pool.currentText()
        provider = self.provider_factory()

        def done(result):
            self.busy = False
            self.refresh.setEnabled(True)
            if revision != self.revision:
                return
            self.picks, status = result
            self.result_stale = "STALE CACHE" in status
            self.status.setText(status)
            self.table.setRowCount(len(self.picks))
            for row, pick in enumerate(self.picks):
                best = max(pick.matchups, key=lambda p: p.adjusted)
                worst = min(pick.matchups, key=lambda p: p.adjusted)
                values = [hero_name(pick.hero_id), f"{pick.score:.1f} / 100", hero_name(best.enemy_id),
                          hero_name(worst.enemy_id), str(min(p.games for p in pick.matchups))]
                for col, value in enumerate(values):
                    self.table.setItem(row, col, QTableWidgetItem(value))
            if self.picks:
                self.table.selectRow(0)

        def failed(message):
            self.busy = False
            self.refresh.setEnabled(True)
            if revision == self.revision:
                self.picks = []
                self.table.setRowCount(0)
                self.details.clear()
                self.choose.setEnabled(False)
                self.status.setText(message + " · No complete draft recommendation available.")
        self.launch_worker(lambda progress: provider.suggestions(enemies, excluded, pool, progress, cancel), done, failed,
                           lambda msg: self.status.setText(msg) if revision == self.revision else None)

    def selected(self):
        row = self.table.currentRow()
        return self.picks[row] if 0 <= row < len(self.picks) else None

    def show_details(self):
        pick = self.selected()
        self.choose.setEnabled(pick is not None)
        if not pick:
            self.details.clear()
            return
        rows = []
        for pair in pick.matchups:
            rows.append(f"vs <b>{escape(hero_name(pair.enemy_id))}</b>: {pair.rate:.1%} observed wins "
                        f"({pair.wins:,}/{pair.games:,} games); {100 * pair.adjusted:.1f} adjusted. "
                        f'<a style="color:#d4a15c" href="https://www.opendota.com/heroes/{pair.enemy_id}/matchups">Source</a>')
        self.details.setHtml("<br>".join(rows) + "<p>Small samples have less influence. Below 50 is an unfavorable historical signal. "
                             "Hover the Matchup score heading for the formula.</p>")

    def choose_hero(self):
        pick = self.selected()
        if pick:
            self.meta_active=False
            self.overlay_enabled.setChecked(False)
            self.use_hero.emit(pick.hero_id)

    def overlay_text(self):
        if self.meta_active and not (self.overlay_enabled.isChecked() and self.picks):
            return (ROLES[self.meta_role],self.meta_text(),self.meta_status)
        if not self.overlay_enabled.isChecked():
            return None
        enemies = [hero_name(c.currentData()) for c in self.enemies if c.currentData()]
        lines = [f"{hero_name(p.hero_id)} · {p.score:.1f}" for p in self.picks[:8]]
        return (", ".join(enemies) or "No enemy picks", "\n\n".join(lines) or "Waiting for complete matchup data",
                "Historical matchup scores · mixed patches/ranks" + (" · STALE CACHE" if self.result_stale else ""))
