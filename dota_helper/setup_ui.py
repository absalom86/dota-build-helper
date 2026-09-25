"""A small executable-first setup flow, with folder selection only as a fallback."""
from pathlib import Path
from subprocess import TimeoutExpired

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                              QPushButton, QFileDialog, QInputDialog)

from . import credentials, game_setup


class SetupDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle('Quick setup')
        self.resize(600, 560)
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)

        def note(text):
            widget = QLabel(text)
            widget.setWordWrap(True)
            layout.addWidget(widget)
            return widget

        note('Set up once, then launch Dota from the helper. Python is included in the EXE.')
        note('1. STRATZ key')
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText('Paste your STRATZ API token')
        layout.addWidget(self.key)
        row = QHBoxLayout()
        get_key = QPushButton('Get a key')
        get_key.clicked.connect(lambda: QDesktopServices.openUrl(QUrl('https://stratz.com/api')))
        row.addWidget(get_key)
        self.save_key = QPushButton('Save key')
        self.save_key.clicked.connect(self.store_key)
        row.addWidget(self.save_key)
        layout.addLayout(row)
        try:
            saved = bool(credentials.load_token())
            key_text = 'Key available. Leave this field empty to keep it.' if saved else 'Get your key from STRATZ, or use one privately shared with permission.'
            if saved:
                self.key.setPlaceholderText('Saved key in use — no need to enter it again')
                self.save_key.setText('Replace saved key')
        except (OSError, RuntimeError, UnicodeError):
            key_text = credentials.UNREADABLE_KEY
            self.save_key.setEnabled(False)
        self.key_status = note(key_text)

        note('2. Connect Dota')
        remembered = owner.settings.get('dota_directory')
        choices = game_setup.dota_directories()
        self.root = Path(remembered) if remembered and game_setup.is_dota_directory(remembered) else choices[0] if len(choices) == 1 else None
        self.location = note(str(self.root) if self.root else 'Dota will be located when you click Connect Dota.')
        self.connect_button = QPushButton('Connect Dota')
        self.connect_button.clicked.connect(self.connect_game)
        layout.addWidget(self.connect_button)
        note('This installs the helper connection file automatically. Existing helper configs are backed up.')

        note('3. Launch and test')
        self.launch_button = QPushButton('Launch Dota')
        self.launch_button.clicked.connect(self.start_game)
        layout.addWidget(self.launch_button)
        note('Close Dota first. This button includes -gamestateintegration for this launch. '
             'Use it each time, or add the option once in Steam if you prefer Steam’s Play button. '
             'Start a bot match and select your position in Builds; detected heroes load builds automatically.')
        self.status = note('')
        done = QPushButton('Back to helper')
        done.clicked.connect(self.accept)
        layout.addWidget(done)
        self.refresh()

    def refresh(self):
        ready = self.root is not None and game_setup.config_ready(self.root, self.owner.settings['gsi_token'])
        self.launch_button.setEnabled(ready and self.owner.receiver is not None)
        self.connect_button.setText('Repair connection' if ready else 'Connect Dota')
        if ready:
            self.location.setText(f'Connection file ready · {self.root}')
        if self.owner.receiver is None:
            self.status.setText('Game receiver unavailable. Close other helper copies, then reopen this app.')

    def store_key(self):
        try:
            credentials.save_token(self.key.text())
        except (OSError, ValueError, RuntimeError) as error:
            self.key_status.setText(str(error))
            return
        self.key.clear()
        self.key.setPlaceholderText('Saved key in use — no need to enter it again')
        self.save_key.setText('Replace saved key')
        self.key_status.setText('Key saved securely for your Windows account. API access is checked on lookup.')
        self.owner.draft.refresh_meta()

    def connect_game(self):
        if self.root is None:
            choices = game_setup.dota_directories()
            if len(choices) == 1:
                self.root = choices[0]
            elif choices:
                choice, accepted = QInputDialog.getItem(self, 'Choose Dota installation',
                    'More than one installation was found:', [str(path) for path in choices], 0, False)
                if not accepted:
                    return
                self.root = Path(choice)
            else:
                choice = QFileDialog.getExistingDirectory(self, 'Choose Dota installation folder (usually dota 2 beta)')
                if not choice:
                    return
                self.root = Path(choice)
        try:
            game_setup.install_config(self.root, self.owner.settings['gsi_token'])
        except (OSError, ValueError) as error:
            self.status.setText(f'Connection setup failed: {error}')
            self.root = None
            self.refresh()
            return
        self.owner.settings['dota_directory'] = str(self.root)
        self.owner.save_settings()
        self.status.setText('Connection file installed. Launch Dota below; no manual file copying is needed.')
        self.refresh()

    def start_game(self):
        try:
            game_setup.launch_dota(self.root, self.owner.settings['gsi_token'])
        except (OSError, ValueError, RuntimeError, TimeoutExpired) as error:
            self.status.setText(str(error))
            return
        self.status.setText('Launch requested through Steam. Connection is confirmed only when Dota sends game data.')
