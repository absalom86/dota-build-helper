import argparse
from collections import Counter
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys
import threading
import time

from PySide6.QtCore import Qt, QTimer, QThread, Signal, QObject, QAbstractNativeEventFilter, QRect, QPoint, QUrl, QLockFile
from PySide6.QtGui import QColor, QPainter, QPixmap, QImage, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QCheckBox, QSlider, QSpinBox, QTabWidget, QTextBrowser, QTableWidget,
    QTableWidgetItem, QHeaderView, QGroupBox, QFormLayout, QSplitter, QMessageBox,
    QFileDialog, QDialog, QRubberBand, QSizeGrip, QScrollArea, QLineEdit, QFrame, QInputDialog,
)

from .catalog import HEROES, ROLES, PATCHES, ability_name, item_name, patch_name, clock_text
from .detection import Detector, capture
from .draft_ui import DraftPanel
from .gsi import Receiver, config_text
from .models import Session
from .history import SearchHistory, decode as history_routes, patch_key, SEARCH_TTL, DISCOVERY_VERSION
from .ranking import ranked
from .builds import overlay_sections, starting_buy_text
from . import starting_items
from . import guides, invoker
from .overlay import Overlay, route_identity, purchase_summary
from .lane_timers import LaneTimers
from .providers import LOCAL, OpenDota, Demo
from . import profile
from .windows import dota_active, register_hotkey, unregister_hotkey, IS_WINDOWS


STYLE = """
QWidget { background: #111820; color: #e5eaf0; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow { background: #111820; }
QLabel#eyebrow { color: #dcaa63; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#heading { font-size: 30px; font-weight: 650; color: #f6f1e8; }
QLabel#muted { color: #97a6b7; }
QLabel#status { background: #1d2c36; color: #a9d9cb; padding: 12px; border-radius: 8px; }
QPushButton { background: #253441; border: 1px solid #394956; border-radius: 6px; padding: 9px 14px; }
QPushButton:hover { background: #354857; }
QPushButton:disabled { color: #6f7b88; background: #1b242e; }
QPushButton#primary { background: #d4a15c; color: #151c23; border: none; font-weight: 700; }
QComboBox, QSpinBox { background: #1c2732; border: 1px solid #3a4856; border-radius: 5px; padding: 8px; }
QComboBox QAbstractItemView { background: #1c2732; selection-background-color: #415364; }
QGroupBox { border: 1px solid #30404d; border-radius: 8px; margin-top: 16px; padding: 18px 12px 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #c7d5df; }
QTableWidget, QTextBrowser { background: #151f29; border: 1px solid #2c3b48; border-radius: 6px; gridline-color: #253442; }
QHeaderView::section { background: #23313e; color: #aebdca; border: none; padding: 10px; }
QTableWidget::item { padding: 6px; }
QTabWidget::pane { border: 0; }
QTabBar::tab { padding: 12px 20px; color: #a6b5c3; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #e5ba7a; border-bottom: 2px solid #d4a15c; }
QCheckBox { spacing: 8px; padding: 5px 0; }
QSlider::groove:horizontal { height: 5px; background: #344451; }
QSlider::handle:horizontal { background: #d4a15c; width: 14px; margin: -4px 0; border-radius: 7px; }
"""


def label(text, name=None):
    result = QLabel(text)
    result.setWordWrap(True)
    result.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        result.setObjectName(name)
    return result


def button(text, callback, primary=False):
    result = QPushButton(text)
    result.clicked.connect(callback)
    if primary:
        result.setObjectName("primary")
    return result


class Worker(QThread):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(str)
    partial = Signal(object)

    def __init__(self, fn, parent=None, streaming=False):
        super().__init__(parent)
        self.fn = fn
        self.streaming = streaming

    def run(self):
        try:
            self.done.emit(self.fn(self.progress.emit, self.partial.emit) if self.streaming else self.fn(self.progress.emit))
        except Exception as exc:
            # No URLs/tokens from network exceptions should reach the interface.
            from .providers import DataError
            self.failed.emit(str(exc) if isinstance(exc, DataError) else f"{type(exc).__name__}: operation failed; check configuration.")


class Bridge(QObject):
    state = Signal(dict)


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        if IS_WINDOWS:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == 1:
                self.callback()
                return True, 0
        return False, 0


class CropDialog(QDialog):
    def __init__(self, frame, monitor, parent):
        super().__init__(parent)
        self.setWindowTitle("Drag around YOUR selected-hero portrait, then release")
        self.monitor = monitor
        self.frame = frame
        self.region = None
        scale = min(1100 / frame.width, 700 / frame.height, 1)
        self.view_w, self.view_h = int(frame.width * scale), int(frame.height * scale)
        self.setFixedSize(self.view_w, self.view_h)
        data = frame.convert("RGB").tobytes()
        self.pixmap = QPixmap.fromImage(QImage(data, frame.width, frame.height, frame.width * 3, QImage.Format.Format_RGB888).copy())
        self.band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.start = QPoint()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.pixmap)

    def mousePressEvent(self, event):
        self.start = event.position().toPoint()
        self.band.setGeometry(QRect(self.start, self.start))
        self.band.show()

    def mouseMoveEvent(self, event):
        self.band.setGeometry(QRect(self.start, event.position().toPoint()).normalized())

    def mouseReleaseEvent(self, event):
        rect = self.band.geometry().intersected(self.rect())
        if rect.width() < 10 or rect.height() < 10:
            return
        sx, sy = self.frame.width / self.width(), self.frame.height / self.height()
        self.region = {"left": self.monitor["left"] + int(rect.left() * sx),
                       "top": self.monitor["top"] + int(rect.top() * sy),
                       "width": int(rect.width() * sx), "height": int(rect.height() * sy)}
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, demo=False, start_services=True):
        super().__init__()
        LOCAL.mkdir(parents=True, exist_ok=True)
        self.settings_file = LOCAL / "settings.json"
        self.history = SearchHistory(LOCAL)
        self.history_key = None
        self.settings = profile.load_settings(self.settings_file)
        self.existing_profile = bool(self.settings)
        self.session = Session(hero_id=self.settings.get("hero_id", 1))
        self.routes = []
        self.services_started = start_services
        self.quantity_busy = False
        self.quantity_cancel = threading.Event()
        self.quantity_results = {}
        self.quantity_attempted = set()
        self.closing = False
        self.workers = set()
        self.fetching = False
        self.pending_auto_fetch = False
        self.capture_busy = False
        self.role_busy=False
        self.role_manual=False
        self.hero_manual=False
        self.observed_match_id=''
        self.observed_game_state=None
        self.observed_clock=None
        self.draft_candidate=None
        self.draft_candidate_at=0
        self.draft_candidate_seen=0
        self.draft_candidate_reads=0
        self.draft_preview_hero=None
        self.last_draft_lookup=None
        self.role_applied=False
        self.role_candidate=None
        self.role_streak=0
        self.role_epoch=0
        self.draft_phase=False
        self.role_state_at=0
        self.cancel = threading.Event()
        self.generation = 0
        self.manual_running = False
        self.manual_anchor = time.monotonic()
        self.manual_second = 0
        self.detected = None
        self.detected_at = 0
        self.detector = Detector(LOCAL / "portraits")
        self.gsi_status = "Waiting for local game state"
        self.api_status = "Choose a hero and find builds, or explore the offline demo."
        self.overlay = Overlay(self.settings, STYLE)
        self.setWindowTitle("Dota Build Helper")
        self.setWindowIcon(QIcon(str(Path(__file__).parent / 'data' / 'app-icon.ico')))
        self.resize(1180, 880)
        self.setMinimumSize(880, 640)
        self.setStyleSheet(STYLE)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        app_title = label("DOTA BUILD HELPER", "eyebrow")
        app_title.setWordWrap(False)
        header.addWidget(app_title)
        header.addStretch()
        header.addWidget(button('Quick setup', self.quick_setup))
        self.connection_summary = label('Game data · waiting for Dota', 'muted')
        self.connection_summary.setWordWrap(False)
        header.addWidget(self.connection_summary)
        layout.addLayout(header)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.build_page(demo)
        self.draft = DraftPanel(self.launch_worker, self)
        self.draft.auto_meta=start_services
        self.draft.meta_active=start_services and not demo
        self.draft.meta_role=self.role.currentData()
        self.role.currentIndexChanged.connect(lambda _:self.draft.set_role(self.role.currentData()))
        self.role.activated.connect(self.override_role)
        self.hero.activated.connect(self.override_hero)
        self.draft.use_hero.connect(self.use_draft_hero)
        self.draft_scroll = QScrollArea()
        self.draft_scroll.setWidgetResizable(True)
        self.draft_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.draft_scroll.setWidget(self.draft)
        self.tabs.addTab(self.draft_scroll, "Draft helper")
        self.setup_page()
        self.status = label(self.api_status, "status")
        layout.addWidget(self.status)
        self.tabs.currentChanged.connect(lambda _: self.status.setVisible(self.tabs.currentWidget() is not self.draft_scroll))
        self.bridge = Bridge()
        self.bridge.state.connect(self.on_gsi)
        self.receiver = None
        token = self.settings.setdefault("gsi_token", secrets.token_urlsafe(32))
        if start_services:
            try:
                self.receiver = Receiver(self.bridge.state.emit, token)
                self.receiver.start()
                self.gsi_status = "Listening on 127.0.0.1:38765 · waiting for Dota"
            except OSError:
                self.gsi_status = "Port 38765 unavailable. Another copy may be running."
        self.hotkey_filter = HotkeyFilter(lambda: self.overlay_enabled.setChecked(not self.overlay_enabled.isChecked()))
        self.hotkey_ok = register_hotkey(self.settings.get("hotkey", 0x77)) if start_services else False
        QApplication.instance().installNativeEventFilter(self.hotkey_filter)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(500)
        self.capture_timer = QTimer(self)
        self.capture_timer.timeout.connect(self.detect_frame)
        self.capture_timer.start(1500)
        self.save_settings()
        if start_services and not demo:
            QTimer.singleShot(0,self.draft.refresh_meta)
            if not self.existing_profile and not self.settings.get('quick_setup_seen'):
                QTimer.singleShot(0,self.quick_setup)
        if demo:
            self.draft.meta_active=False
        if demo:
            self.hero.setCurrentIndex(self.hero.findData(1))
            self.role.setCurrentIndex(self.role.findData(1))
            self.fetch()

    def quick_setup(self):
        from .setup_ui import SetupDialog
        self.settings['quick_setup_seen']=True
        self.save_settings()
        SetupDialog(self).exec()

    def build_page(self, demo):
        from PySide6.QtWidgets import QSizePolicy

        # Default scroll-area size hints inflate the outer page. Use readable
        # minima as the preferred height, then share spare height by stretch.
        class CompactTable(QTableWidget):
            def sizeHint(self):
                size = super().sizeHint()
                size.setHeight(self.minimumHeight())
                return size

        class ContentSplitter(QSplitter):
            def sizeHint(self):
                return self.minimumSizeHint()

        page = QWidget()
        self.builds_page = page
        page.setStyleSheet('QComboBox, QSpinBox { padding:5px 7px; } '
                           'QPushButton { padding:5px 10px; } '
                           'QHeaderView::section { padding:4px 6px; } '
                           'QTableWidget::item { padding:3px 5px; }')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(4)
        selectors = QHBoxLayout()
        self.hero = QComboBox()
        for key, value in sorted(HEROES.items(), key=lambda kv: kv[1]["localized_name"]):
            self.hero.addItem(value["localized_name"], int(key))
        self.hero.setCurrentIndex(max(0, self.hero.findData(self.session.hero_id)))
        self.hero.setMinimumWidth(200)
        self.role = QComboBox()
        for key, value in ROLES.items():
            self.role.addItem(f"{key} · {value}", key)
        self.role.setCurrentIndex(self.role.findData(self.settings.get("role", 1)))
        self.source = QComboBox()
        self.source.addItems(["Recommended builds", "Offline demo", "Legacy league examples", "OpenDota · recent pubs", "STRATZ · ranked pubs"])
        for index in (2,3,4):
            self.source.view().setRowHidden(index,True)
        self.source.setCurrentIndex(1 if demo else 0)
        for widget in (self.hero, self.role, self.source):
            selectors.addWidget(widget)
            widget.currentIndexChanged.connect(self.context_changed)
        self.find_button = button("Find builds", self.find_or_cancel, True)
        selectors.addWidget(self.find_button)
        layout.addLayout(selectors)
        detection_bar = QHBoxLayout()
        self.selection_status = label('Hero: waiting for game · Position: saved selection', 'muted')
        detection_bar.addWidget(self.selection_status, 1)
        self.resume_detection_button = button('Resume detection', self.resume_detection)
        self.resume_detection_button.setToolTip('Release manual hero and position overrides for this match')
        detection_bar.addWidget(self.resume_detection_button)
        layout.addLayout(detection_bar)
        history_bar = QHBoxLayout()
        self.history_choice = QComboBox()
        self.history_choice.setMinimumWidth(240)
        history_bar.addWidget(self.history_choice,1)
        self.history_choice.setToolTip("Choose a saved search to restore its builds")
        self.history_choice.activated.connect(lambda _: self.open_saved_search())
        layout.addLayout(history_bar)
        self.refresh_history_list()
        self.auto_hero = QCheckBox("Use confirmed hero from game state")
        self.auto_hero.setChecked(True)
        self.more_button = button("More options", lambda: None)
        self.more_button.setCheckable(True)
        history_bar.addWidget(self.more_button)
        self.more_options = QWidget()
        options_layout = QVBoxLayout(self.more_options)
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.addWidget(self.auto_hero)
        self.preview_draft_hero = QCheckBox('Preview stable draft hero before lock-in is confirmed')
        self.preview_draft_hero.setChecked(self.settings.get('preview_draft_hero', True))
        self.preview_draft_hero.toggled.connect(lambda value: self.settings.update(preview_draft_hero=value))
        options_layout.addWidget(self.preview_draft_hero)
        imports = QHBoxLayout()
        options_layout.addLayout(imports)
        self.match_input = QLineEdit()
        self.match_input.setPlaceholderText("Chosen match ID, D2PT link or OpenDota link")
        imports.addWidget(self.match_input, 1)
        self.import_button = button("Follow this game", self.import_match)
        imports.addWidget(self.import_button)
        imports.addWidget(button("Browse D2PT", self.browse_d2pt))
        actions = QHBoxLayout()
        actions.addWidget(button("New match", self.new_match))
        actions.addStretch()
        options_layout.addLayout(actions)
        self.more_options.setVisible(False)
        self.more_button.toggled.connect(self.more_options.setVisible)
        layout.addWidget(self.more_options)
        ranking_help = label("Current patch → unverified patch → older patch. Within each group: premier events, other pro games, then ranked pubs; newest first.", "muted")
        ranking_help.setToolTip('Current patch means the match agrees with bundled patch metadata. '
                               'Missing or conflicting versions remain unverified; match date alone does not verify a patch. '
                               'Event and pro labels use provider metadata, without a team-strength ranking.')
        layout.addWidget(ranking_help)
        self.match_table = CompactTable(0, 5)
        self.match_table.setHorizontalHeaderLabels(["MMR / PRO", "Player / result / match", "Date", "Starting purchases", "Item timings"])
        self.match_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.match_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.match_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.match_table.setMinimumHeight(104)
        self.match_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.match_table.verticalHeader().setDefaultSectionSize(25)
        self.match_table.verticalHeader().hide()
        self.match_table.setWordWrap(False)
        for column, width in ((0, 98), (1, 205), (2, 90)):
            self.match_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
            self.match_table.setColumnWidth(column, width)
        for column in (3, 4):
            self.match_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        self.match_table.cellClicked.connect(lambda row, col: self.route_choice.setCurrentIndex(row))
        self.match_table.currentCellChanged.connect(lambda row, *_: self.route_choice.setCurrentIndex(row) if row >= 0 else None)
        layout.addWidget(self.match_table, 2)
        self.route_choice = QComboBox()
        self.route_choice.addItem("No route loaded")
        self.route_choice.currentIndexChanged.connect(self.select_route)
        self.route_choice.hide()  # The match list is the route selector, including keyboard selection.
        self.evidence = label("A matching route is selected automatically. You can switch at any time.", "muted")
        layout.addWidget(self.evidence)
        self.quantity_preview = label('Starting buy appears here after selecting a game.')
        self.quantity_preview.setStyleSheet('background:#1d2c36; padding:6px 8px; color:#ffe0a3;')
        layout.addWidget(self.quantity_preview)
        selected_actions = QHBoxLayout()
        self.edit_starting_button = button('Edit quantities', self.edit_starting_buy)
        selected_actions.addWidget(self.edit_starting_button)
        self.verify_quantities_button = button('Check quantities', self.verify_starting_quantities)
        self.verify_quantities_button.setToolTip('Check the selected match against a second purchase log in the background.')
        selected_actions.addWidget(self.verify_quantities_button)
        self.export_guide_button = button('Export to Dota shop…', self.export_shop_guide)
        self.export_guide_button.setEnabled(False)
        selected_actions.addWidget(self.export_guide_button)
        selected_actions.addStretch()
        layout.addLayout(selected_actions)
        self.guide_status = label('Shop guide · not exported', 'muted')
        selected_actions.addWidget(self.guide_status, 1)
        splitter = ContentSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        items_panel = QWidget()
        items_layout = QVBoxLayout(items_panel)
        items_layout.setContentsMargins(0, 0, 8, 0)
        items_layout.setSpacing(4)
        items_layout.addWidget(label("PURCHASE ROUTE", "eyebrow"))
        self.purchases = CompactTable(0, 4)
        self.purchases.setHorizontalHeaderLabels(["Done", "Item / purchase event", "Reference time", "Evidence"])
        self.purchases.verticalHeader().hide()
        self.purchases.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.purchases.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.purchases.setColumnWidth(0, 46)
        self.purchases.setColumnWidth(2, 128)
        self.purchases.setColumnWidth(3, 148)
        self.purchases.verticalHeader().setDefaultSectionSize(25)
        self.purchases.setMinimumHeight(104)
        self.purchases.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.purchases.itemChanged.connect(self.mark_purchase)
        items_layout.addWidget(self.purchases, 1)
        purchase_help = label("Tick completed purchases · timings are reference points.", "muted")
        purchase_help.setToolTip("Components and recipes are separate observed purchase events. Benchmarks are reference points, not deadlines.")
        items_layout.addWidget(purchase_help)
        skills_panel = QWidget()
        skills_layout = QVBoxLayout(skills_panel)
        skills_layout.setContentsMargins(8, 0, 0, 0)
        skills_layout.setSpacing(4)
        skill_tabs = QTabWidget()
        skill_tabs.setStyleSheet('QTabBar::tab { padding:4px 8px; }')
        skill_page = QWidget()
        skill_page_layout = QVBoxLayout(skill_page)
        skill_page_layout.setContentsMargins(0, 4, 0, 0)
        skill_page_layout.setSpacing(4)
        self.skills = QTextBrowser()
        self.skills.setOpenExternalLinks(True)
        self.skills.setMinimumHeight(64)
        self.skills.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        skill_page_layout.addWidget(self.skills, 1)
        skill_actions = QHBoxLayout()
        skill_actions.addWidget(button("Mark next skill", self.mark_skill))
        skill_actions.addWidget(button("Undo", self.undo_skill))
        skill_page_layout.addLayout(skill_actions)
        self.manual_skill_history = []
        self.route_notes = QTextBrowser()
        self.route_notes.setOpenExternalLinks(True)
        self.route_notes.setMinimumHeight(64)
        self.route_notes.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        skill_tabs.addTab(skill_page, 'Skills && talents')
        skill_tabs.addTab(self.route_notes, 'Source notes')
        skills_layout.addWidget(skill_tabs)
        splitter.addWidget(items_panel)
        splitter.addWidget(skills_panel)
        splitter.setSizes([680, 300])
        layout.addWidget(splitter, 3)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        self.tabs.addTab(scroll, "Builds")

    def setup_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        overlay_group = QGroupBox("In-game overlay")
        form = QFormLayout(overlay_group)
        self.overlay_enabled = QCheckBox("Show overlay when Dota is active")
        self.overlay_enabled.setChecked(True)
        self.preview = QCheckBox("Preview / reposition overlay outside Dota")
        self.preview.setChecked(False)
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(35, 100)
        self.opacity.setValue(self.settings.get("opacity", 94))
        self.hotkey = QComboBox()
        for key in range(0x75, 0x7C):
            self.hotkey.addItem(f"Ctrl + F{key - 0x6F}", key)
        self.hotkey.setCurrentIndex(max(0, self.hotkey.findData(self.settings.get("hotkey", 0x77))))
        self.hotkey.currentIndexChanged.connect(self.change_hotkey)
        form.addRow(self.overlay_enabled)
        form.addRow(self.preview)
        form.addRow(button("Position below top-right game stats", self.overlay.place_top_right))
        form.addRow("Opacity", self.opacity)
        form.addRow("Toggle shortcut", self.hotkey)
        self.overlay_width = QSpinBox()
        self.overlay_width.setRange(270, 600)
        self.overlay_width.setSingleStep(30)
        self.overlay_width.setSuffix(' px')
        self.overlay_width.setValue(self.overlay.preferred_width)
        self.overlay_width.valueChanged.connect(lambda value: setattr(self.overlay, 'preferred_width', value))
        self.overlay_font = QSpinBox()
        self.overlay_font.setRange(11, 16)
        self.overlay_font.setSuffix(' px')
        self.overlay_font.setValue(self.overlay.font_size)
        self.overlay_font.valueChanged.connect(lambda value: setattr(self.overlay, 'font_size', value))
        self.supply_minutes = QSpinBox()
        self.supply_minutes.setRange(5, 15)
        self.supply_minutes.setSuffix(' min')
        self.supply_minutes.setValue(self.settings.get('supply_minutes', 10))
        form.addRow('Preferred width', self.overlay_width)
        form.addRow('Overlay text size', self.overlay_font)
        form.addRow('Laning supplies until', self.supply_minutes)
        self.overlay_fit_status = label('', 'muted')
        form.addRow(self.overlay_fit_status)
        form.addRow(label("Preview lets you drag or change width. Height fits the content automatically; short screens may use a wider layout. During play the overlay is click-through.\nBorderless fullscreen is the target mode; exclusive fullscreen needs live verification.", "muted"))
        layout.addWidget(overlay_group)
        role_group=QGroupBox('Draft role recognition · experimental')
        role_form=QFormLayout(role_group)
        self.role_ocr=QCheckBox('Read my assigned role during draft')
        self.role_ocr.setChecked(self.settings.get('role_ocr',False))
        self.role_ocr.toggled.connect(lambda value:self.settings.update(role_ocr=value))
        role_form.addRow(self.role_ocr)
        role_form.addRow(button('Calibrate my role label…',self.calibrate_role))
        self.role_status=label('Requires Tesseract OCR with English data. Crop only YOUR assigned-role label.\nThree agreeing reads required. Changing position manually overrides detection for this match.','muted')
        role_form.addRow(self.role_status)
        layout.addWidget(role_group)
        self.lane_timers=LaneTimers(self.settings)
        layout.addWidget(self.lane_timers)
        api_group = QGroupBox("STRATZ connection")
        api_form = QFormLayout(api_group)
        self.stratz_key = QLineEdit()
        self.stratz_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.stratz_key.setPlaceholderText("Paste a new API key to replace the saved credential")
        api_form.addRow(self.stratz_key)
        api_form.addRow(button("Save STRATZ key", self.save_stratz_key))
        api_form.addRow(label("Stored with Windows user-account encryption. The key is not included in app settings or the EXE.", "muted"))
        layout.addWidget(api_group)
        gsi_group = QGroupBox("Game connection && clock")
        gsi_form = QFormLayout(gsi_group)
        self.prefer_gsi_clock = QCheckBox("Use game clock when connected (freeze if connection is lost)")
        self.prefer_gsi_clock.setChecked(True)
        gsi_form.addRow(self.prefer_gsi_clock)
        gsi_form.addRow(button("Export Dota game-state config…", self.export_gsi))
        gsi_form.addRow(label("Copy the exported file into Dota's game/dota/cfg/gamestate_integration folder and add\n-gamestateintegration to Dota's Steam launch options, then restart Dota. No game settings are changed by this app.", "muted"))
        row = QHBoxLayout()
        self.manual_time = QSpinBox()
        self.manual_time.setRange(-900, 10800)
        self.manual_time.setSuffix(" sec")
        row.addWidget(self.manual_time)
        row.addWidget(button("Sync manual clock", self.sync_clock))
        self.pause_button = button("Start / pause manual clock", self.pause_clock)
        row.addWidget(self.pause_button)
        gsi_form.addRow("Fallback clock", row)
        layout.addWidget(gsi_group)
        detect_group = QGroupBox("Screen recognition · calibrated portrait candidates")
        detect_form = QFormLayout(detect_group)
        self.capture_enabled = QCheckBox("Enable local capture while Dota is foreground")
        self.monitor = QSpinBox()
        self.monitor.setRange(1, 16)
        self.monitor.setValue(self.settings.get("monitor", 1))
        detect_form.addRow(self.capture_enabled)
        detect_form.addRow("Monitor number", self.monitor)
        detect_form.addRow(button("Calibrate region (capture in 5 seconds)", self.calibrate))
        detect_form.addRow(button("Save selected hero's reference (in 5 seconds)", self.save_portrait))
        detect_form.addRow(label("Select your hero in Builds first. During the countdown, Alt-Tab to Dota.\nCalibrate to your own locked portrait, then save a reference for each hero you want recognized.\nA portrait match alone cannot prove lock-in; confirm the candidate or use game state.", "muted"))
        self.detection_status = label("Capture paused", "muted")
        detect_form.addRow(self.detection_status)
        self.accept_candidate = button("Use detected hero", self.use_candidate)
        self.accept_candidate.setEnabled(False)
        detect_form.addRow(self.accept_candidate)
        layout.addWidget(detect_group)
        self.diagnostics = label("", "status")
        layout.addWidget(self.diagnostics)
        layout.addStretch()
        scroll.setWidget(page)
        self.tabs.addTab(scroll, "Overlay && connection")

    def launch_worker(self, fn, callback, fail=None, progress=None, partial=None):
        worker = Worker(fn, self, streaming=partial is not None)
        self.workers.add(worker)
        worker.done.connect(callback)
        worker.failed.connect(fail or self.show_error)
        if progress:
            worker.progress.connect(progress)
        if partial:
            worker.partial.connect(partial)
        worker.finished.connect(lambda: self.workers.discard(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def show_error(self, message):
        self.status.setText(message)

    def context_changed(self):
        self.auto_fetch_attempted = False
        self.quantity_cancel.set()
        self.quantity_attempted.clear()
        if not hasattr(self, "route_choice"):
            return
        self.generation += 1
        self.history_key = None
        self.pending_auto_fetch = False
        self.cancel.set()
        if self.session.hero_id != self.hero.currentData() or self.sender() is self.source:
            self.session.reset(self.hero.currentData())
            self.manual_skill_history = []
        self.session.selected = None
        self.session.explicit_choice = False
        self.routes = []
        self.render_routes()
        self.api_status = "Selection changed. Find builds for this hero and role."
        self.status.setText(self.api_status)
        self.save_settings()

    def refresh_history_list(self):
        selected=self.history_choice.currentData()
        self.history_choice.clear()
        for entry in sorted(self.history.entries,key=lambda e:e['used'],reverse=True):
            hero=HEROES.get(str(entry['hero']),{}).get('localized_name',str(entry['hero']))
            date=datetime.fromtimestamp(entry['updated']).strftime('%d %b %H:%M')
            source=self.source.itemText(entry['source'])
            self.history_choice.addItem(f"{hero} · {entry['role']} · {source} · patch {entry.get('patch_name','?')} · {date}",entry['key'])
        if not self.history.entries:
            self.history_choice.addItem('No saved searches yet',None)
        if selected:
            self.history_choice.setCurrentIndex(max(0,self.history_choice.findData(selected)))

    def show_saved_search(self, entry):
        self.draft.meta_active=False
        self.history_key=entry['key']
        routes=history_routes(entry)
        if self.session.explicit_choice and self.current_route() and self.session.selected not in {r.id for r in routes}:
            routes=ranked([self.current_route()]+routes[:9])
        self.routes=routes
        if not self.session.explicit_choice:
            self.session.selected=entry.get('selected') if entry.get('selected') in {r.id for r in routes} else None
        self.session.accept_routes(routes)
        date=datetime.fromtimestamp(entry['updated']).strftime('%d %b %H:%M')
        older=' · Older bundled patch — refresh recommended' if entry['patch']!=patch_key() else ''
        self.api_status=f"Saved search · {date} · {len(routes)} builds · no network needed{older}. Source patch warnings still apply."
        if entry.get('cached_origin'):
            self.api_status+=' Saved from cached source data.'
        self.status.setText(self.api_status)
        self.render_routes()

    def open_saved_search(self):
        if self.fetching:
            self.status.setText('Finish or cancel the current search before opening history.')
            return
        entry=next((e for e in self.history.entries if e['key']==self.history_choice.currentData()),None)
        if not entry:
            return
        self.hero_manual=True
        self.role_manual=True
        self.role_epoch+=1
        self.draft_preview_hero=None
        self.hero.setCurrentIndex(self.hero.findData(entry['hero']))
        self.role.setCurrentIndex(self.role.findData(entry['role']))
        self.source.setCurrentIndex(entry['source'])
        self.session.explicit_choice=False
        self.show_saved_search(entry)
        self.history.choose(entry['key'],self.session.selected)

    def find_or_cancel(self):
        if self.fetching:
            self.cancel.set()
            self.find_button.setText("Cancelling…")
            self.find_button.setEnabled(False)
        else:
            self.fetch(force=True)

    def search_controls(self, busy):
        self.find_button.setText("Cancel" if busy else "Find builds")
        self.find_button.setEnabled(True)

    def fetch(self, *, force=False):
        if self.fetching:
            self.status.setText("Search already running. Cancel it before starting another.")
            return
        entry=self.history.find(self.hero.currentData(),self.role.currentData(),self.source.currentIndex())
        if entry:
            self.show_saved_search(entry)
            if (not force and entry['patch']==patch_key() and time.time()-entry['updated']<SEARCH_TTL
                    and (entry['source']!=0 or entry.get('discovery_version')==DISCOVERY_VERSION)):
                return
        self.fetching = True
        self.search_controls(True)
        self.cancel = threading.Event()
        generation = self.generation
        context = (self.hero.currentData(), self.role.currentData(), 0)
        provider = Demo() if self.source.currentIndex() == 1 else OpenDota()
        if isinstance(provider,OpenDota):
            provider.force_refresh=force
        source_index = self.source.currentIndex()
        cancel = self.cancel

        def done(result):
            self.fetching = False
            self.search_controls(False)
            if self.pending_auto_fetch:
                self.pending_auto_fetch = False
                QTimer.singleShot(0, self.fetch)
            publish(result)
            if generation==self.generation and result[0]:
                self.history.save(context[0],context[1],source_index,self.routes,self.session.selected,result[1])
                saved=self.history.find(context[0],context[1],source_index)
                self.history_key=saved['key'] if saved else None
                self.refresh_history_list()

        def publish(result):
            if generation != self.generation:
                return
            routes, status = result
            if not routes and entry and self.routes:
                routes=self.routes
                status+=' Saved builds retained; no new results.'
            old = self.current_route()
            if self.session.explicit_choice and old and old.id not in {r.id for r in routes}:
                routes = ranked([old] + routes[:9])
                status += " Your selected route was retained."
            self.routes = routes
            if routes:
                self.draft.meta_active=False
            self.session.accept_routes(routes)
            self.api_status = status
            self.status.setText(status)
            self.render_routes()

        def failed(message):
            self.fetching = False
            self.search_controls(False)
            if self.pending_auto_fetch:
                self.pending_auto_fetch = False
                QTimer.singleShot(0, self.fetch)
            if generation == self.generation:
                self.api_status = message + (" · Current route retained." if self.routes else "")
                self.status.setText(self.api_status)

        from .pub_lookup import recent_pubs
        from .stratz import Stratz
        def lookup(progress, update):
            if source_index == 0:
                from .recommendations import recommended_routes
                return recommended_routes(Stratz(refresh=force), context[0], context[1], progress, cancel, update)
            if source_index == 4:
                return Stratz(refresh=force).routes(context[0], context[1], progress, cancel, update)
            if source_index == 3:
                return recent_pubs(provider, context[0], context[1], progress, cancel, update)
            if isinstance(provider, OpenDota):
                return provider.routes(*context, progress, cancel, on_update=update)
            return provider.routes(*context, progress, cancel)
        self.launch_worker(lookup, done, failed,
                           lambda message: self.status.setText(message) if generation == self.generation else None,
                           partial=publish)

    def current_route(self):
        return next((r for r in self.routes if r.id == self.session.selected), None)

    def save_stratz_key(self):
        from .credentials import save_token
        try:
            save_token(self.stratz_key.text())
            self.draft.refresh_meta()
            self.stratz_key.clear()
            QMessageBox.information(self, "STRATZ", "API key saved with Windows encryption.")
        except (ValueError, RuntimeError, OSError) as error:
            QMessageBox.warning(self, "STRATZ", str(error))

    def browse_d2pt(self):
        from urllib.parse import quote
        name = self.hero.currentText()
        roles = {1: "carry", 2: "mid", 3: "offlane", 4: "support", 5: "hard-support"}
        QDesktopServices.openUrl(QUrl(f"https://dota2protracker.com/hero/{quote(name, safe='')}?role={roles[self.role.currentData()]}&section=matches"))

    def import_match(self):
        from .match_import import match_id, load_match
        from .providers import DataError
        if self.fetching:
            self.status.setText("Wait for the current lookup to finish, or cancel it first.")
            return
        try:
            mid = match_id(self.match_input.text())
        except DataError as exc:
            self.status.setText(str(exc))
            return
        if self.source.currentIndex() == 1:
            self.source.setCurrentIndex(0)
        self.cancel = threading.Event()
        cancel, generation = self.cancel, self.generation
        context = (self.hero.currentData(), self.role.currentData(), 0)
        self.fetching = True
        self.search_controls(True)
        self.import_button.setEnabled(False)
        self.status.setText(f"Loading game {mid} directly · 8-second limit…")
        def finish():
            self.fetching = False
            self.search_controls(False)
            self.import_button.setEnabled(True)
            if self.pending_auto_fetch:
                self.pending_auto_fetch = False
                QTimer.singleShot(0, self.fetch)
        def done(route):
            finish()
            if generation != self.generation:
                return
            self.routes = [route] + [r for r in self.routes if r.id != route.id and not r.demo][:9]
            self.session.choose(route.id)
            self.render_routes()
            self.status.setText(f"Following game {mid}: exact observed purchases and skill sequence. Match MMR unverified.")
        def failed(message):
            finish()
            if generation == self.generation:
                self.status.setText(message)
        from .stratz import Stratz
        stratz_source = self.source.currentIndex() in (0,4)
        self.launch_worker(lambda progress: Stratz().load_match(mid, context[0], context[1], cancel) if stratz_source else load_match(OpenDota(), mid, *context, cancel), done, failed)

    def use_draft_hero(self, hero_id):
        self.source.setCurrentIndex(0)
        self.hero.setCurrentIndex(self.hero.findData(hero_id))
        self.tabs.setCurrentIndex(0)
        self.hero_manual = True
        self.draft_preview_hero = None
        # Select in the assistant only; never issue a pick to the game.
        if self.fetching:
            self.cancel.set()
            self.pending_auto_fetch = True
        else:
            self.fetch()

    def edit_starting_buy(self):
        route=self.current_route()
        if not route:
            self.status.setText('Select a build before editing its starting buy.')
            return
        dialog=QDialog(self)
        dialog.setWindowTitle('Starting buy quantities')
        layout=QVBoxLayout(dialog)
        layout.addWidget(label('Saved for this match and hero. Tango quantity counts packs, not charges.\nSet 0 to remove an item. Original purchase records remain unchanged.'))
        form=QFormLayout()
        layout.addLayout(form)
        fields={}
        def add_field(key, count=1):
            if key in fields:
                return
            spin=QSpinBox()
            spin.setRange(0,30)
            spin.setValue(count)
            fields[key]=spin
            form.addRow(item_name(key),spin)
        for key,count in starting_items.counts(route).items():
            add_field(key,count)
        from .catalog import ITEMS
        choice=QComboBox()
        for key in sorted(ITEMS,key=item_name):
            choice.addItem(item_name(key),key)
        layout.addWidget(choice)
        layout.addWidget(button('Add item',lambda:add_field(choice.currentData())))
        def accept():
            try:
                starting_items.save(route,{k:s.value() for k,s in fields.items() if s.value()})
            except OSError:
                QMessageBox.warning(dialog,'Starting buy','Could not save starting quantities.')
                return
            dialog.accept()
            self.render_routes()
            self.tick()
        layout.addWidget(button('Save quantities',accept,True))
        def reset():
            try:
                starting_items.reset(route)
            except OSError:
                QMessageBox.warning(dialog, 'Starting buy', 'Could not reset starting quantities.')
                return
            dialog.accept()
            self.render_routes()
            self.tick()
        layout.addWidget(button('Reset to source', reset))
        layout.addWidget(button('Cancel',dialog.reject))
        dialog.exec()

    def refresh_quantity_preview(self):
        route = self.current_route()
        self.edit_starting_button.setEnabled(route is not None)
        self.verify_quantities_button.setEnabled(bool(route and not route.demo and route.source == 'STRATZ' and not self.quantity_busy))
        if route is None:
            self.quantity_preview.setText('Select a game to preview its starting quantities.')
            self.guide_status.setText('Shop guide · no build selected')
            return
        details = starting_items.details(route)
        text = ' · '.join(f"{item_name(value['key'])} ×{value['count']} ({value['provenance']})" for value in details)
        from .quantity_evidence import get_saved
        result = self.quantity_results.get(starting_items.key(route)) or get_saved(route)
        suffix = '\n' + result['message'] if result else ''
        self.quantity_preview.setText('STARTING BUY · Tango quantities are packs\n' + (text or 'No pregame purchases recorded.') + suffix)
        self.quantity_preview.setToolTip('\n'.join(f"{item_name(value['key'])}: {value['source']}. {value['note']}" for value in details))
        self.refresh_guide_status()

    def schedule_quantity_check(self):
        route = self.current_route()
        if (not self.services_started or self.closing or self.fetching or self.quantity_busy or route is None
                or route.demo or route.source != 'STRATZ' or starting_items.correction(route) is not None
                or starting_items.key(route) in self.quantity_attempted):
            return
        route_id, generation = route.id, self.generation
        def check():
            current = self.current_route()
            if (current and current.id == route_id and generation == self.generation and not self.closing
                    and not self.fetching and starting_items.key(current) not in self.quantity_attempted):
                self.verify_starting_quantities(False)
        QTimer.singleShot(600, check)

    def verify_starting_quantities(self, interactive=True):
        from .quantity_evidence import verify_selected
        route = self.current_route()
        if route is None or self.quantity_busy:
            return
        self.quantity_busy = True
        self.quantity_cancel = threading.Event()
        cancel = self.quantity_cancel
        route_key = starting_items.key(route)
        player_identity = (route.id, route.account_id, route.player_slot)
        self.quantity_attempted.add(route_key)
        generation = self.generation
        self.verify_quantities_button.setText('Checking…')
        self.refresh_quantity_preview()
        def finish(result):
            self.quantity_busy = False
            self.verify_quantities_button.setText('Check quantities')
            self.quantity_results[route_key] = result
            current = self.current_route()
            if (generation != self.generation or current is None or
                    (current.id, current.account_id, current.player_slot) != player_identity):
                self.refresh_quantity_preview()
                self.schedule_quantity_check()
                return
            if (interactive and result['status'] == 'conflict' and result.get('counts') is not None
                    and starting_items.correction(current) is None):
                current_text = starting_buy_text(current) or 'No pregame purchases'
                other_text = ', '.join(f'{item_name(key)} ×{count}' for key, count in result['counts'].items()) or 'No pregame purchases'
                choice = QMessageBox.question(self, 'Starting purchase logs disagree',
                    f'Current guide:\n{current_text}\n\nOpenDota log for the same player/game:\n{other_text}\n\n'
                    'Neither log proves a complete starting inventory. Use the OpenDota counts as a saved correction?\n'
                    'Choose No to keep the current quantities.',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if choice == QMessageBox.StandardButton.Yes:
                    try:
                        starting_items.save(current, result['counts'], source='OpenDota log accepted by user', note=result['message'])
                    except OSError:
                        self.show_error('Could not save the quantity correction.')
                    self.render_routes()
            self.refresh_quantity_preview()
        def failed(message):
            finish({'status': 'unavailable', 'message': message, 'counts': None})
        self.launch_worker(lambda _: verify_selected(route, OpenDota(), cancel), finish, failed)

    def refresh_guide_status(self):
        route = self.current_route()
        if route is None:
            self.guide_status.setText('Shop guide · no build selected')
            return
        record = self.settings.get('guide_exports', {}).get(guides.filename(route))
        if not record:
            state = 'not exported'
        elif not Path(record['path']).is_file():
            state = 'exported file missing · export again'
        elif record.get('fingerprint') != guides.fingerprint(route):
            state = 'build or quantities changed · export again'
        elif not guides.export_file_matches(record):
            state = 'exported file changed · review or export again'
        else:
            state = 'export is up to date · select it manually in Dota'
        match = route.match_ids[0] if route.match_ids else 'demo'
        self.guide_status.setText(f'Match {match} · Shop guide · {state}')
        self.guide_status.setToolTip(record['path'] if record else 'Export the selected build to create a local shop guide.')

    def render_routes(self):
        self.match_table.blockSignals(True)
        self.route_choice.blockSignals(True)
        self.route_choice.clear()
        self.match_table.setRowCount(len(self.routes))
        for i, route in enumerate(self.routes):
            rating = ('PRO' if route.tournament or route.pro_player else
                      'DEMO' if route.demo else
                      f'{route.average_mmr:,} MMR' if route.average_mmr else 'MMR unavailable')
            display_player = (f"PRO · {route.player}" if route.tournament else
                              f"PRO · {route.player}" if route.pro_player else
                              route.player if route.demo else rating)
            self.route_choice.addItem(f"{display_player} · {route.result} · {route.title}", route.id)
            date = datetime.fromtimestamp(route.start_time, timezone.utc).strftime("%d %b %H:%M") if route.start_time else "Demo"
            starting = starting_buy_text(route) or "Not recorded"
            if route.source == 'STRATZ' and starting_items.correction(route) is None:
                starting += ' (recorded counts; may be incomplete)'
            timings = " → ".join(f"{item_name(p.key)} {clock_text(p.time)}" for p in route.purchases if p.time >= 0)
            match_id = route.match_ids[0] if route.match_ids else 'Synthetic'
            player = route.player if route.tournament or route.pro_player or route.demo else 'Pub'
            values = [rating, f"{player} · {route.result} · {match_id}", date, starting, timings]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip((value + '\n' + route.evidence) if col == 0 else value)
                self.match_table.setItem(i, col, cell)
        if not self.routes:
            self.route_choice.addItem("No route loaded")
        self.route_choice.setCurrentIndex(max(0, self.route_choice.findData(self.session.selected)))
        self.route_choice.blockSignals(False)
        self.match_table.selectRow(self.route_choice.currentIndex())
        self.match_table.blockSignals(False)
        self.render_route()

    def select_route(self):
        route_id = self.route_choice.currentData()
        if route_id:
            self.session.choose(route_id)
            if self.history_key:
                self.history.choose(self.history_key,route_id)
            self.match_table.selectRow(self.route_choice.currentIndex())
        self.render_route()
        self.schedule_quantity_check()

    def render_route(self):
        route = self.current_route()
        self.refresh_quantity_preview()
        self.purchases.blockSignals(True)
        self.purchases.setRowCount(0)
        if not route:
            self.evidence.setText("No reliable route loaded. Choose a hero and role, then find builds.")
            self.skills.clear()
            self.route_notes.clear()
            self.purchases.blockSignals(False)
            return
        date = datetime.fromtimestamp(route.start_time, timezone.utc).strftime("%d %b %Y") if route.start_time else "Synthetic"
        identity = route_identity(route).replace('\n', ' · ')
        match = route.match_ids[0] if route.match_ids else 'synthetic'
        self.evidence.setText(f'{identity} · Match {match}')
        self.evidence.setToolTip(f'{route.source} · {date}\n{route.evidence}\nFacet variant {route.facet or "unavailable"}')
        self.purchases.setRowCount(len(route.purchases))
        for row, purchase in enumerate(route.purchases):
            tick = QTableWidgetItem()
            tick.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            tick.setCheckState(Qt.CheckState.Checked if self.session.is_complete(purchase) else Qt.CheckState.Unchecked)
            self.purchases.setItem(row, 0, tick)
            name = item_name(purchase.key)
            if purchase.occurrence > 1:
                name += f" (purchase {purchase.occurrence})"
            self.purchases.setItem(row, 1, QTableWidgetItem(name))
            timing = "Starting purchase" if purchase.time < 0 else clock_text(purchase.time)
            if purchase.low is not None and purchase.time >= 0:
                timing = f"{clock_text(purchase.low)}–{clock_text(purchase.high)}"
            self.purchases.setItem(row, 2, QTableWidgetItem(timing))
            evidence = QTableWidgetItem("Synthetic demo" if route.demo else "Observed purchase")
            evidence.setToolTip("Synthetic test data." if route.demo else "Recorded in the selected game's purchase log. This describes the purchase source, not lookup success or verified match MMR.")
            self.purchases.setItem(row, 3, evidence)
        self.purchases.blockSignals(False)
        from html import escape
        talents=list(dict.fromkeys(s for s in route.skills if s.startswith('special_bonus_') and s!='special_bonus_attributes'))
        talent_html=("<b>Talent picks · recorded order</b><ul>"+
                     "".join(f"<li>{escape(ability_name(s))}</li>" for s in talents)+"</ul>"
                     if talents else "<p>Talent picks not recorded for this game.</p>")
        self.skills.setHtml(talent_html + "<p style='color:#97a6b7'>Exact hero levels are unavailable. Follow the observed upgrade sequence; check in-game availability.</p>" +
                            ("<ol>" + "".join(f"<li style='margin:6px'>{escape(ability_name(s))}</li>" for s in route.skills) + "</ol>" if route.skills else "Skill history unavailable."))
        domain = 'stratz.com' if route.source == 'STRATZ' else 'www.opendota.com'
        links = " · ".join(f'<a href="https://{domain}/matches/{m}" style="color:#d4a15c">Match {m}</a>' for m in route.match_ids)
        self.route_notes.setHtml("<br>".join(escape(w) for w in route.warnings) + "<p>" + links + "</p>")
        self.schedule_quantity_check()

    def mark_purchase(self, item):
        route = self.current_route()
        if not route or item.column() != 0:
            return
        key = route.purchases[item.row()].identity
        if item.checkState() == Qt.CheckState.Checked:
            self.session.completed.add(key)
        else:
            self.session.completed.discard(key)

    def mark_skill(self):
        route = self.current_route()
        if route:
            skill, _ = self.session.next_skill(route)
            if skill:
                self.session.learned[skill] += 1
                self.manual_skill_history.append(skill)

    def undo_skill(self):
        if self.manual_skill_history:
            skill = self.manual_skill_history.pop()
            self.session.learned[skill] = max(0, self.session.learned[skill] - 1)

    def on_gsi(self, payload):
        game_map=payload.get('map',{})
        state=game_map.get('game_state', self.observed_game_state)
        match_id=str(game_map.get('matchid') or '')
        if match_id=='0':match_id=''
        drafting=state=='DOTA_GAMERULES_STATE_HERO_SELECTION'
        new_match=(match_id and self.observed_match_id and match_id!=self.observed_match_id)
        new_draft=drafting and self.observed_game_state is not None and not self.draft_phase
        clock=game_map.get('clock_time')
        new_bot_game=(type(clock) is int and clock<0 and self.observed_clock is not None
                      and self.observed_clock>0)
        if new_match or new_draft or new_bot_game:
            self.reset_detection_overrides()
            self.session.reset(self.hero.currentData())
            self.manual_second=0
            self.manual_running=False
            self.manual_skill_history=[]
            self.generation+=1
            self.cancel.set()
            self.pending_auto_fetch=False
            self.routes=[]
            self.render_routes()
        if type(clock) is int:self.observed_clock=clock
        if match_id:self.observed_match_id=match_id
        self.observed_game_state=state
        if drafting and not self.draft_phase:
            self.role_epoch+=1
            self.role_applied=False
            self.role_candidate=None
            self.role_streak=0
        self.draft_phase=drafting
        self.role_state_at=time.monotonic()
        self.lane_timers.ingest(payload)
        self.draft.ingest_draft(payload)
        if drafting and not self.draft_preview_hero and not self.hero_manual:
            new_draft=not self.draft.meta_active
            self.draft.meta_active=True
            if new_draft or self.draft.meta_requested_role is None:
                self.draft.refresh_meta()
        if self.source.currentIndex() == 1:
            return
        hero_id = payload.get("hero", {}).get("id")
        if type(hero_id) is not int or str(hero_id) not in HEROES or not payload.get('player',{}).get('steamid'):
            self.draft_candidate=None
            self.draft_candidate_reads=0
            self.gsi_status = "Dota data received · waiting for a local hero (draft/menu or spectator data)"
            return
        if (self.hero_manual or not self.auto_hero.isChecked()) and hero_id != self.session.hero_id:
            self.gsi_status = "Game hero differs · keeping manual hero. Resume detection to follow Dota."
            return
        previous_match, previous_hero = self.session.match_id, self.session.hero_id
        previous_clock = self.session.clock
        previous_skills_at = self.session.skills_at
        if payload.get("map", {}).get("game_state") == "DOTA_GAMERULES_STATE_HERO_SELECTION":
            self.gsi_status = f"Draft data received · {HEROES[str(hero_id)]['localized_name']} · waiting for confirmed pick / strategy phase"
            self.preview_game_hero(hero_id)
            return
        if self.session.ingest(payload):
            self.draft_preview_hero=None
            self.draft_candidate=None
            self.draft_candidate_reads=0
            self.draft.meta_active=False
            self.draft.overlay_enabled.setChecked(False)
            if self.session.skills_at != previous_skills_at:
                self.manual_skill_history = []
            self.gsi_status = 'Connected · local player'
            changed = (previous_hero != self.session.hero_id or (previous_match and self.session.match_id != previous_match)
                       or (previous_clock is not None and previous_clock > 0 and self.session.clock is not None and self.session.clock < 0))
            if changed:
                self.manual_skill_history = []
                self.manual_second = 0
                self.manual_running = False
                self.prefer_gsi_clock.setChecked(True)
                self.hero.blockSignals(True)
                self.hero.setCurrentIndex(self.hero.findData(self.session.hero_id))
                self.hero.blockSignals(False)
                self.generation += 1
                self.cancel.set()
                self.routes = []
                self.render_routes()
                if not self.fetching:
                    self.fetch()
                else:
                    self.pending_auto_fetch = True
                    self.status.setText("New game detected. Loading its builds after the previous search stops.")
            elif not self.routes and not self.fetching and not getattr(self, "auto_fetch_attempted", False):
                self.auto_fetch_attempted = True
                self.fetch()
            route = self.current_route()
            if route and self.session.field_status('inventory') == 'fresh':
                counts = Counter(p.key for p in route.purchases)
                for p in route.purchases:
                    # Repeated consumables cannot be matched to a specific purchase from a snapshot.
                    if counts[p.key] == 1 and self.session.inventory[p.key]:
                        self.session.completed.add(p.identity)
                self.purchases.blockSignals(True)
                for row, p in enumerate(route.purchases):
                    self.purchases.item(row, 0).setCheckState(Qt.CheckState.Checked if self.session.is_complete(p) else Qt.CheckState.Unchecked)
                self.purchases.blockSignals(False)

    def new_match(self):
        self.reset_detection_overrides()
        self.draft.meta_active=True
        self.draft.clear()
        self.draft.overlay_enabled.setChecked(False)
        self.session.reset(self.hero.currentData())
        self.session.accept_routes(self.routes)
        self.manual_running = False
        self.manual_second = 0
        self.manual_skill_history = []
        self.auto_fetch_attempted = False
        self.render_route()

    def sync_clock(self):
        self.prefer_gsi_clock.setChecked(False)
        self.manual_second = self.manual_time.value()
        self.manual_anchor = time.monotonic()
        self.manual_running = True

    def pause_clock(self):
        if self.manual_running:
            self.manual_second += int(time.monotonic() - self.manual_anchor)
        self.manual_anchor = time.monotonic()
        self.manual_running = not self.manual_running

    def game_clock(self):
        if self.prefer_gsi_clock.isChecked() and self.session.clock_at is not None:
            age = time.monotonic() - self.session.clock_at
            return self.session.clock, ("GSI stale · frozen" if age > 5 else "Paused" if self.session.paused else "Game clock")
        second = self.manual_second + (int(time.monotonic() - self.manual_anchor) if self.manual_running else 0)
        return second, "Manual estimate" + (" · paused" if not self.manual_running else "")

    def tick(self):
        hero_mode=('manual' if self.hero_manual or not self.auto_hero.isChecked() else
                   'draft preview · unconfirmed' if self.draft_preview_hero else
                   'game confirmed' if self.session.field_status('hero')=='fresh' else 'waiting for game')
        role_mode='manual' if self.role_manual else 'screen detected' if self.role_applied else 'saved selection'
        self.selection_status.setText(f'Hero: {hero_mode} · Position: {role_mode}')
        self.resume_detection_button.setEnabled(self.hero_manual or self.role_manual or not self.auto_hero.isChecked())
        active = dota_active()
        visible = self.overlay_enabled.isChecked() and (active or self.preview.isChecked())
        self.overlay.set_locked(active or not self.preview.isChecked())
        self.overlay.setWindowOpacity(self.opacity.value() / 100)
        self.overlay.setVisible(visible)
        route = self.current_route()
        second, clock_status = self.game_clock()
        self.overlay.title.hide()
        self.overlay.hero.setText(f"{self.hero.currentText()} · {ROLES[self.role.currentData()]}")
        self.overlay.clock.setText(f"{clock_text(second)} · {clock_status}")
        if self.draft_preview_hero:
            self.overlay.clock.setText('Draft preview · lock-in unconfirmed')
        if route:
            self.overlay.title.setText("OFFLINE DEMO" if route.demo else "TOURNAMENT BUILD" if route.tournament else "RANKED PUB BUILD")
            self.overlay.route_label.setText(route_identity(route))
            self.overlay.route_label.setToolTip(f'{route.title}\nMatch: {route.match_ids[0] if route.match_ids else "demo"}')
            initial = starting_items.counts(route)
            initial_text = ("STARTING BUY · saved quantities\n" if starting_items.correction(route) is not None else
                           "STARTING BUY · counts unverified\n" if route.source == 'STRATZ'
                            else "STARTING BUY\n") + starting_buy_text(route)
            self.overlay.initial_buy.setVisible(bool(initial) and (second is None or second < 60))
            self.overlay.initial_buy.setToolTip(initial_text)
            self.overlay.initial_buy.setText(initial_text)
            sections = overlay_sections(route, second, self.supply_minutes.value())
            self.overlay.components.setText('EARLY PARTS · until 5:00\n' + purchase_summary(sections['components']))
            self.overlay.components.setVisible(bool(sections['components']))
            self.overlay.supplies.setText(f'LANING SUPPLIES · until {self.supply_minutes.value()}:00\n' + purchase_summary(sections['supplies']))
            self.overlay.supplies.setVisible(bool(sections['supplies']))
            lines = []
            # Keep finished-item milestones, including already completed ones.
            for p in sections['items']:
                target = clock_text(p.time)
                if p.low is not None and p.time >= 0:
                    target = f"{clock_text(p.low)}–{clock_text(p.high)}"
                checked = "✓ " if self.session.is_complete(p) else ""
                lines.append((f"{target}  {checked}{item_name(p.key)}", bool(checked)))
            if lines:
                self.overlay.set_item_lines(lines)
            else:
                self.overlay.set_message('No recorded item milestones')
            skill, warning = self.session.next_skill(route)
            self.overlay.skill.setText(f"Next upgrade: {ability_name(skill)}" if skill else warning)
            talents=list(dict.fromkeys(s for s in route.skills if s.startswith('special_bonus_') and s!='special_bonus_attributes'))
            talent_lines=[("Done · " if self.session.learned[s] else "")+ability_name(s) for s in talents]
            self.overlay.talents.setText("Talent picks · recorded order\n"+"\n".join(talent_lines)
                                         if talents else "Talent picks not recorded")
            self.overlay.talents.show()
            notes = []
            if not route.demo:
                if self.session.hero_at is not None:
                    missing = [f'{name} {self.session.field_status(name)}' for name in ('inventory', 'skills')
                               if self.session.field_status(name) != 'fresh']
                    if missing:
                        notes.append('Game data · ' + ' · '.join(missing))
                if any("Cached" in w for w in route.warnings):
                    notes.append("Cached / stale")
                enemies = {c.currentData() for c in self.draft.enemies}
                if ((second is None or second < 600) and enemies & {22, 25, 26}
                        and self.session.field_status('inventory') == 'fresh'
                        and not self.session.inventory['infused_raindrop']
                        and not any(p.key == 'infused_raindrop' for p in route.purchases)):
                    names = ", ".join(HEROES[str(h)]['localized_name'] for h in sorted(enemies & {22, 25, 26}))
                    notes.append(f"Optional · Infused Raindrops vs {names} (magic bursts)")
            self.overlay.note.setText("\n".join(notes))
        else:
            self.overlay.talents.hide()
            self.overlay.initial_buy.hide()
            self.overlay.components.hide()
            self.overlay.supplies.hide()
            self.overlay.route_label.setText("")
            self.overlay.set_message("Choose a hero and find a build route.")
            self.overlay.skill.setText("")
            self.overlay.note.setText("No route loaded")
        telemetry = ' · '.join(f'{name.title()} {self.session.field_status(name)}' for name in ('clock', 'inventory', 'skills'))
        self.connection_summary.setText(telemetry if self.session.hero_at is not None else 'Game data · waiting for Dota')
        ages = []
        for name in ('hero', 'clock', 'inventory', 'charges', 'skills'):
            received = getattr(self.session, name + '_at')
            age = f'{max(0, int(time.monotonic()-received))}s ago' if received is not None else 'not received'
            ages.append(f'{name.title()}: {self.session.field_status(name)} · {age}')
        self.diagnostics.setText(f"{self.gsi_status}\n" + '\n'.join(ages) + f"\n{clock_status} · Dota foreground: {'yes' if active else 'no'} · "
                                 f"Shortcut: {'registered' if self.hotkey_ok else 'unavailable / in use'}\n"
                                 f"API: {self.api_status}\nMetadata snapshot: bundled OpenDota constants; patch {patch_name(PATCHES[-1]['id'])}")
        draft_text = self.draft.overlay_text()
        self.overlay.show_invoker(self.hero.currentData() == invoker.HERO_ID and not draft_text)
        self.export_guide_button.setEnabled(route is not None)
        timer_text=self.lane_timers.text(second,clock_status,self.role.currentData(),
                                        HEROES.get(str(self.hero.currentData()),{}),bool(draft_text))
        self.overlay.lane_timers.setText(timer_text)
        self.overlay.lane_timers.setVisible(bool(timer_text))
        if draft_text:
            self.overlay.talents.hide()
            self.overlay.initial_buy.hide()
            self.overlay.components.hide()
            self.overlay.supplies.hide()
            enemies, suggestions, note = draft_text
            self.overlay.title.setText("DRAFT HELPER")
            self.overlay.title.show()
            self.overlay.hero.setText("Picks to consider")
            self.overlay.route_label.setText(enemies)
            self.overlay.clock.setText("Position " + str(self.role.currentData()))
            self.overlay.set_message(suggestions)
            self.overlay.skill.setText("Choose a hero in Dota; confirmed picks load builds.")
            self.overlay.note.setText(note)
        self.overlay.fit_content()
        self.overlay_fit_status.setText(self.overlay.fit_message)
        if self.overlay_width.value() != self.overlay.preferred_width:
            self.overlay_width.blockSignals(True)
            self.overlay_width.setValue(self.overlay.preferred_width)
            self.overlay_width.blockSignals(False)

    def change_hotkey(self):
        unregister_hotkey()
        self.hotkey_ok = register_hotkey(self.hotkey.currentData())

    def export_gsi(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export game-state configuration", "gamestate_integration_build_helper.cfg", "Dota configuration (*.cfg)")
        if path:
            Path(path).write_text(config_text(self.settings["gsi_token"]), encoding="utf-8")
            self.status.setText("Config exported. Copy into Dota's gamestate_integration folder, add launch option, and restart Dota.")

    def export_shop_guide(self):
        route = self.current_route()
        if route is None:
            self.status.setText("Select a build before exporting a shop guide.")
            return
        directories = guides.guide_directories()
        destination = Path(self.settings.get('guide_export_dir', str(LOCAL / 'guides')))
        saved_destination = self.settings.get('guide_export_dir')
        if saved_destination and Path(saved_destination).is_dir():
            destination = Path(saved_destination)
        elif len(directories) == 1:
            destination = directories[0]
        elif len(directories) > 1:
            choices = [str(path) for path in directories] + ['Choose another folder…']
            choice, accepted = QInputDialog.getItem(self, "Steam account for this guide",
                "Choose the account you use for Dota (userdata folder number):", choices, 0, False)
            if not accepted:
                return
            if choice != choices[-1]:
                destination = Path(choice)
        path, _ = QFileDialog.getSaveFileName(self, "Export selected build — restart Dota to load it",
                                            str(destination / guides.filename(route)), "Dota hero guide (*.build)")
        if not path:
            return
        try:
            saved = guides.write_guide(route, path)
        except (OSError, ValueError) as exc:
            self.show_error(str(exc) if isinstance(exc, ValueError) else
                            "Could not save the guide. Choose a writable folder and try again.")
            return
        self.settings['guide_export_dir'] = str(saved.parent)
        self.settings.setdefault('guide_exports', {})[guides.filename(route)] = {
            'path': str(saved), 'fingerprint': guides.fingerprint(route),
            'file_hash': guides.file_hash(saved)}
        self.save_settings()
        self.refresh_guide_status()
        self.status.setText(f"Shop guide saved: {guides.title(route)}")
        QMessageBox.information(self, "Dota shop guide saved",
            f"Saved to:\n{saved}\n\n"
            "Keep this file in Steam/userdata/<your account>/570/remote/guides.\n"
            "Restart Dota when you have finished playing. Open the shop's guide selector "
            f"for this hero and choose:\n{guides.title(route)}\n\n"
            "Hover items for timings. Skill and talent sequences are in the guide notes; "
            "level-up prompts remain in the helper. Export again after changing builds or starting quantities.")

    def calibrate(self):
        self.status.setText("Capture in 5 seconds. Alt-Tab to Dota on the selected monitor.")
        QTimer.singleShot(5000, self.capture_monitor)

    def capture_monitor(self, region_key='region'):
        if not dota_active():
            self.show_error("Calibration cancelled: Dota must be the foreground window.")
            return
        monitor_index = self.monitor.value()

        def grab(progress):
            import mss
            with mss.mss() as screen:
                monitor = screen.monitors[monitor_index]
                return capture(monitor), monitor

        def done(result):
            frame, monitor = result
            dialog = CropDialog(frame, monitor, self)
            if region_key=='role_region':
                dialog.setWindowTitle('Drag around ONLY your assigned role text, then release')
            self.activateWindow()
            if dialog.exec():
                self.settings[region_key] = dialog.region
                self.save_settings()
                self.status.setText('Role label region saved.' if region_key=='role_region' else "Portrait region saved in physical pixels. Now save a selected hero reference.")
        self.launch_worker(grab, done)

    def save_portrait(self):
        if not self.settings.get("region"):
            self.show_error("Calibrate the portrait region first.")
            return
        hero_id = self.hero.currentData()
        self.status.setText(f"Saving {self.hero.currentText()} reference in 5 seconds. Alt-Tab to your locked portrait.")

        def take():
            if not dota_active():
                self.show_error("Reference cancelled: Dota must be foreground.")
                return

            def done(frame):
                frame.save(LOCAL / "portraits" / f"{hero_id}.png")
                self.status.setText("Local portrait reference saved. Enable capture to recognize it.")
            self.launch_worker(lambda _: capture(self.settings["region"]), done)
        QTimer.singleShot(5000, take)

    def detect_frame(self):
        self.detect_role()
        if not self.capture_enabled.isChecked() or not dota_active():
            self.detector.candidate, self.detector.streak = None, 0
            if not self.capture_enabled.isChecked() or time.monotonic() - self.detected_at > 30:
                self.detected = None
                self.accept_candidate.setEnabled(False)
                self.detection_status.setText("Capture paused · enable capture and focus Dota")
            return
        if not self.settings.get("region"):
            self.detection_status.setText("Screen recognition is not calibrated. Use game-state connection, or calibrate a portrait region first.")
            return
        if self.capture_busy:
            return
        self.capture_busy = True

        def done(result):
            self.capture_busy = False
            hero, score, status = result
            self.detected = hero
            self.detected_at = time.monotonic()
            self.accept_candidate.setEnabled(hero is not None)
            name = HEROES.get(str(hero), {}).get("localized_name", "")
            self.detection_status.setText(f"{name} · {score:.0%} similarity · {status}")

        def fail(message):
            self.capture_busy = False
            self.detected = None
            self.accept_candidate.setEnabled(False)
            self.detection_status.setText(message)
        self.launch_worker(lambda _: self.detector.inspect(capture(self.settings["region"])), done, fail)

    def override_role(self, *_):
        self.role_manual=True
        self.role_epoch+=1
        self.role_status.setText('Manual position override for this match')
        self.request_selection_builds()

    def override_hero(self, *_):
        self.hero_manual=True
        self.draft_preview_hero=None
        self.request_selection_builds()

    def request_selection_builds(self):
        """Only the latest selection may publish; an old request must finish first."""
        self.auto_fetch_attempted=True
        if self.fetching:
            self.cancel.set()
            self.pending_auto_fetch=True
        else:
            self.fetch()

    def reset_detection_overrides(self):
        self.hero_manual=False
        self.role_manual=False
        self.role_applied=False
        self.role_candidate=None
        self.role_streak=0
        self.role_epoch+=1
        self.draft_candidate=None
        self.draft_candidate_reads=0
        self.draft_preview_hero=None
        self.last_draft_lookup=None
        self.auto_fetch_attempted=False

    def resume_detection(self):
        self.reset_detection_overrides()
        self.auto_hero.setChecked(True)
        self.role_status.setText('Waiting for assigned-role text during draft; OCR must be enabled and calibrated.')
        self.gsi_status='Automatic selection resumed · waiting for fresh game data'

    def preview_game_hero(self, hero_id):
        """A stable local GSI hero can warm builds, but does not prove lock-in."""
        if self.hero_manual or not self.auto_hero.isChecked() or not self.preview_draft_hero.isChecked():
            return
        now=time.monotonic()
        if hero_id!=self.draft_candidate or now-self.draft_candidate_seen>5:
            self.draft_candidate=hero_id
            self.draft_candidate_at=now
            self.draft_candidate_reads=0
        self.draft_candidate_seen=now
        self.draft_candidate_reads+=1
        if self.draft_candidate_reads<3 or now-self.draft_candidate_at<2:
            return
        if self.draft_preview_hero==hero_id:
            return
        if self.last_draft_lookup is not None and now-self.last_draft_lookup<10:
            return
        self.last_draft_lookup=now
        self.hero.setCurrentIndex(self.hero.findData(hero_id))
        self.draft_preview_hero=hero_id
        self.draft.meta_active=False
        self.draft.overlay_enabled.setChecked(False)
        self.request_selection_builds()

    def calibrate_role(self):
        self.status.setText('Capture in 5 seconds. Focus Dota with your assigned role visible.')
        QTimer.singleShot(5000,lambda:self.capture_monitor('role_region'))

    def detect_role(self):
        if (not self.role_ocr.isChecked() or not self.draft_phase or self.role_manual or self.role_applied
                or time.monotonic()-self.role_state_at>5 or not dota_active()):
            self.role_candidate=None; self.role_streak=0
            return
        if self.role_busy:return
        if not self.settings.get('role_region'):
            self.role_status.setText('Calibrate your assigned-role label first.')
            return
        from .role_detection import read_role
        self.role_busy=True
        epoch=self.role_epoch
        def done(role):
            self.role_busy=False
            if (epoch!=self.role_epoch or self.role_manual or not self.draft_phase
                    or not self.role_ocr.isChecked() or time.monotonic()-self.role_state_at>5
                    or not dota_active()):return
            self.role_streak=self.role_streak+1 if role and role==self.role_candidate else 1 if role else 0
            self.role_candidate=role
            self.role_status.setText('Role unclear; manual selection remains available.' if not role else f'Checking position {role}: {self.role_streak}/3 reads')
            if role and self.role_streak>=3:
                self.role_applied=True
                changed=self.role.currentData()!=role
                self.role.setCurrentIndex(self.role.findData(role))
                self.role_status.setText(f'Detected position {role}. Change position in Builds to override.')
                if changed and (self.draft_preview_hero or self.hero_manual or self.session.field_status('hero')=='fresh'):
                    self.request_selection_builds()
        def failed(message):
            self.role_busy=False
            if epoch!=self.role_epoch:return
            self.role_streak=0
            self.role_status.setText(message)
            self.role_ocr.setChecked(False)
        self.launch_worker(lambda _:read_role(capture(self.settings['role_region'])),done,failed)

    def use_candidate(self):
        if self.detected:
            self.hero.setCurrentIndex(self.hero.findData(self.detected))
            self.hero_manual=True
            self.draft_preview_hero=None
            self.tabs.setCurrentIndex(0)
            self.request_selection_builds()

    def save_settings(self):
        if hasattr(self, "opacity"):
            self.settings.pop("lane", None)
            self.settings.update(hero_id=self.hero.currentData(), role=self.role.currentData(),
                                 opacity=self.opacity.value(), monitor=self.monitor.value(), hotkey=self.hotkey.currentData(),
                                 overlay_x=self.overlay.x(), overlay_y=self.overlay.y(),
                                 overlay_w=self.overlay.preferred_width, overlay_h=self.overlay.height(),
                                 overlay_font=self.overlay.font_size, supply_minutes=self.supply_minutes.value())
        profile.save_settings(self.settings_file, self.settings)

    def closeEvent(self, event):
        self.closing = True
        self.draft.stop()
        self.cancel.set()
        self.quantity_cancel.set()
        self.pending_auto_fetch = False
        self.capture_timer.stop()
        if self.workers:
            self.status.setText("Finishing background operations before closing…")
            self.setEnabled(False)
            QTimer.singleShot(250, self.close)
            event.ignore()
            return
        self.timer.stop()
        self.capture_timer.stop()
        self.save_settings()
        unregister_hotkey()
        QApplication.instance().removeNativeEventFilter(self.hotkey_filter)
        if self.receiver:
            self.receiver.stop()
        self.overlay.close()
        event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="Open labeled synthetic demo")
    args = parser.parse_args()
    if IS_WINDOWS:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('DotaBuildHelper.Companion')
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Dota Build Helper")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / 'data' / 'app-icon.ico')))
    # Check account-bound credentials before a wrong-account process can rewrite settings.
    from .credentials import load_token
    try:
        load_token()
        profile.load_settings(LOCAL / 'settings.json')
    except (RuntimeError, OSError) as error:
        QMessageBox.critical(None, 'Saved profile unavailable', str(error))
        return 1
    LOCAL.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(LOCAL / 'helper.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None, 'Dota Build Helper',
                                'The helper is already open for this profile. Use the existing window.')
        return 0
    window = MainWindow(demo=args.demo)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
