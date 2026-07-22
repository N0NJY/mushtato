"""Headless tests for Phase 6's dual input: two simultaneous boxes,
both sending to the same connection, each with independent history.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent

from gui.windows.history_line_edit import HistoryLineEdit
from gui.windows.main_window import MainWindow
from tests.gui.test_main_window_smoke import FakeBridge


def _press(widget, key):
    event = QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    widget.keyPressEvent(event)


def test_both_boxes_send_to_the_same_connection(qapp):
    bridge = FakeBridge()
    window = MainWindow("example.com", 4201, bridge=bridge)

    window.input_line.setText("look")
    window.input_line.returnPressed.emit()
    window.secondary_input.setText("waves hello")
    window.secondary_input.returnPressed.emit()

    assert bridge.sent == ["look", "waves hello"]


def test_secondary_input_echoes_locally_and_clears(qapp):
    bridge = FakeBridge()
    window = MainWindow("example.com", 4201, bridge=bridge)

    window.secondary_input.setText("waves hello")
    window.secondary_input.returnPressed.emit()

    assert "waves hello" in window.scrollback.toPlainText()
    assert window.secondary_input.text() == ""


def test_connection_closed_disables_both_inputs(qapp):
    bridge = FakeBridge()
    window = MainWindow("example.com", 4201, bridge=bridge)

    bridge.connectionClosed.emit()

    assert window.input_line.isEnabled() is False
    assert window.secondary_input.isEnabled() is False


def test_history_line_edit_recalls_previous_entries():
    edit = HistoryLineEdit()
    edit.setText("first")
    edit.returnPressed.emit()
    edit.setText("second")
    edit.returnPressed.emit()

    _press(edit, Qt.Key.Key_Up)
    assert edit.text() == "second"
    _press(edit, Qt.Key.Key_Up)
    assert edit.text() == "first"
    _press(edit, Qt.Key.Key_Down)
    assert edit.text() == "second"
    _press(edit, Qt.Key.Key_Down)
    assert edit.text() == ""


def test_primary_and_secondary_history_are_independent(qapp):
    window = MainWindow("example.com", 4201, bridge=FakeBridge())

    window.input_line.setText("north")
    window.input_line.returnPressed.emit()

    window.secondary_input.setText("smiles")
    window.secondary_input.returnPressed.emit()

    _press(window.input_line, Qt.Key.Key_Up)
    assert window.input_line.text() == "north"

    _press(window.secondary_input, Qt.Key.Key_Up)
    assert window.secondary_input.text() == "smiles"
