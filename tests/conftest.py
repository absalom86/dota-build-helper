"""Keep one Qt application alive across widget tests and deferred events."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope='session', autouse=True)
def qt_application():
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()
