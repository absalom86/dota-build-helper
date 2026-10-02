"""Opt-in installer updates; all network and file verification runs off the UI thread."""
import sys

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout

from .updates import RELEASES_URL, Updater
from .version import VERSION


class UpdateController(QObject):
    def __init__(self, window, root):
        super().__init__(window)
        self.window = window
        self.updater = Updater(root)
        self.busy = False
        self.downloading = False
        self.path = None
        self.dialog = None
        self.message = 'Check for a newer Windows installer on GitHub.'
        self.button = QPushButton('Updates')
        self.button.clicked.connect(self.show)
        self.refresh()

    def in_match(self):
        # Keep the guard even if GSI temporarily stops sending packets. A later
        # post-game/menu state clears it. A manual clock alone is also sufficient.
        state = self.window.observed_game_state or ''
        return self.window.manual_running or state in {
            'DOTA_GAMERULES_STATE_HERO_SELECTION', 'DOTA_GAMERULES_STATE_STRATEGY_TIME',
            'DOTA_GAMERULES_STATE_TEAM_SHOWCASE', 'DOTA_GAMERULES_STATE_WAIT_FOR_MAP_TO_LOAD',
            'DOTA_GAMERULES_STATE_PRE_GAME', 'DOTA_GAMERULES_STATE_GAME_IN_PROGRESS',
        }

    def refresh(self):
        release = self.updater.release
        self.button.setText(f'Update {release.tag}' if release and not self.updater.deferred() else 'Updates')
        self.button.setToolTip(f'Running v{VERSION}. Updates are optional.')
        if not self.dialog:
            return
        self.status.setText(self.message)
        notes = (release.notes or 'No release notes provided.') if release else 'No newer release selected.'
        if self.notes.toPlainText() != notes:
            self.notes.setPlainText(notes)
        self.check_button.setEnabled(not self.busy)
        self.download_button.setEnabled(bool(release) and not self.busy)
        self.cancel_button.setVisible(self.downloading)
        self.install_button.setEnabled(bool(self.path and release) and not self.busy
                                       and not self.in_match() and bool(getattr(sys, 'frozen', False)))
        if self.in_match():
            self.hint.setText('Finish the match before installing an update.')
        elif not getattr(sys, 'frozen', False):
            self.hint.setText('Run the packaged app to install updates. Source checkouts can check and download.')
        else:
            self.hint.setText('Install saves your settings and closes the helper, then reopens the installed app. '
                             'A portable EXE stays unchanged; use the Start menu shortcut afterward.')

    def show(self):
        if not self.dialog:
            self.dialog = QDialog(self.window)
            self.dialog.setWindowTitle('Dota Build Helper · Updates')
            self.dialog.resize(580, 430)
            layout = QVBoxLayout(self.dialog)
            layout.addWidget(QLabel(f'Dota Build Helper · v{VERSION}'))
            self.status = QLabel()
            self.status.setWordWrap(True)
            layout.addWidget(self.status)
            self.notes = QTextEdit()
            self.notes.setReadOnly(True)
            layout.addWidget(self.notes, 1)
            self.hint = QLabel()
            self.hint.setWordWrap(True)
            layout.addWidget(self.hint)
            row = QHBoxLayout()
            for attr, title, callback in (
                ('check_button', 'Check now', lambda: self.check(True)),
                ('download_button', 'Download', self.download),
                ('cancel_button', 'Cancel download', self.updater.cancel.set),
            ):
                widget = QPushButton(title)
                widget.clicked.connect(callback)
                setattr(self, attr, widget)
                row.addWidget(widget)
            layout.addLayout(row)
            row = QHBoxLayout()
            self.install_button = QPushButton('Install and restart')
            self.install_button.clicked.connect(self.install)
            row.addWidget(self.install_button)
            page = QPushButton('Release page')
            page.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(RELEASES_URL)))
            row.addWidget(page)
            later = QPushButton('Later')
            later.clicked.connect(self.later)
            row.addWidget(later)
            layout.addLayout(row)
            self.timer = QTimer(self.dialog)
            self.timer.timeout.connect(self.refresh)
            self.timer.start(1000)
        self.refresh()
        self.dialog.show()
        self.dialog.raise_()
        self.check(False)

    def later(self):
        if not self.busy:
            try:
                self.updater.later()
            except OSError:
                self.message = 'Could not save the reminder preference.'
        self.dialog.hide()
        self.refresh()

    def failed(self, message):
        self.busy = self.downloading = False
        self.message = message
        self.refresh()

    def check(self, force=False):
        if self.busy or self.window.closing or (not force and not self.updater.due()):
            return
        self.busy = True
        self.message = 'Checking GitHub releases…'
        self.refresh()
        def done(release):
            self.busy = False
            self.path = None
            self.message = self.updater.message
            self.refresh()
        self.window.launch_worker(lambda _: self.updater.check(force), done, self.failed)

    def download(self):
        if self.busy or self.window.closing or not self.updater.release:
            return
        release = self.updater.release
        self.busy = self.downloading = True
        self.path = None
        self.updater.cancel.clear()
        self.message = f'Downloading {release.tag}…'
        self.refresh()
        def progress(message):
            self.message = message
            self.refresh()
        def done(path):
            self.busy = self.downloading = False
            self.path = path
            self.message = f'{release.tag} downloaded and checksum verified. Ready when you are.'
            self.refresh()
        self.window.launch_worker(lambda progress: self.updater.download(release, progress), done,
                                  self.failed, progress=progress)

    def install(self):
        if self.busy or self.window.closing or self.in_match() or not getattr(sys, 'frozen', False):
            return
        release, path = self.updater.release, self.path
        if not path or not release:
            return
        self.busy = True
        self.message = 'Verifying installer before closing…'
        self.refresh()
        def done(verified):
            self.busy = False
            if self.window.closing or self.in_match():
                self.message = 'Installation postponed. Finish the match first.'
                self.refresh()
                return
            self.window.pending_update = (verified, release)
            self.window.close()
        self.window.launch_worker(lambda _: self.updater.verify(path, release), done, self.failed)
