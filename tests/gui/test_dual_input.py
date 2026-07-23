"""Headless tests for Phase 6's dual input: two simultaneous boxes,
both sending to the same connection, each with independent history.
Now lives on SessionTab (Phase 9) rather than MainWindow itself.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent

from gui.windows.history_line_edit import HistoryLineEdit
from gui.windows.session_tab import SessionTab
from tests.gui.test_main_window_smoke import FakeBridge


def _press(widget, key):
    event = QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    widget.keyPressEvent(event)


def test_both_boxes_send_to_the_same_connection(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    tab.input_line.setText("look")
    tab.input_line.returnPressed.emit()
    tab.secondary_input.setText("waves hello")
    tab.secondary_input.returnPressed.emit()

    assert bridge.sent == ["look", "waves hello"]


def test_secondary_input_echoes_locally_and_clears(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    tab.secondary_input.setText("waves hello")
    tab.secondary_input.returnPressed.emit()

    assert "waves hello" in tab.scrollback.toPlainText()
    assert tab.secondary_input.text() == ""


def test_connection_closed_disables_both_inputs(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)

    bridge.connectionClosed.emit()

    assert tab.input_line.isEnabled() is False
    assert tab.secondary_input.isEnabled() is False


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


def test_scrollback_and_input_area_are_resizable_via_a_splitter(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())
    tab.show()
    tab.resize(800, 600)

    assert tab.splitter.count() == 2
    assert tab.splitter.widget(0) is tab.scrollback
    # input_line/secondary_input live in a container that's the
    # splitter's second pane, not added to it directly.
    input_container = tab.splitter.widget(1)
    assert tab.input_line in input_container.findChildren(type(tab.input_line))
    assert tab.secondary_input in input_container.findChildren(type(tab.secondary_input))

    original_sizes = tab.splitter.sizes()
    tab.splitter.setSizes([50, 400])
    assert tab.splitter.sizes() != original_sizes


def test_primary_and_secondary_history_are_independent(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())

    tab.input_line.setText("north")
    tab.input_line.returnPressed.emit()

    tab.secondary_input.setText("smiles")
    tab.secondary_input.returnPressed.emit()

    _press(tab.input_line, Qt.Key.Key_Up)
    assert tab.input_line.text() == "north"

    _press(tab.secondary_input, Qt.Key.Key_Up)
    assert tab.secondary_input.text() == "smiles"
