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


# -- Remembered fonts + splitter size (post-8b addition) -----------------


def test_constructing_with_explicit_fonts_applies_them(qapp):
    tab = SessionTab(
        "example.com", 4201, bridge=FakeBridge(),
        scrollback_font_family="Courier New", scrollback_font_size=14,
        input_font_family="Arial", input_font_size=11,
    )

    assert tab.scrollback.font().family() == "Courier New"
    assert tab.scrollback.font().pointSize() == 14
    assert tab.input_line.font().family() == "Arial"
    assert tab.input_line.font().pointSize() == 11
    assert tab.secondary_input.font().family() == "Arial"
    assert tab.secondary_input.font().pointSize() == 11


def test_constructing_with_no_font_override_keeps_the_original_defaults(qapp):
    from gui.fonts import default_scrollback_font

    tab = SessionTab("example.com", 4201, bridge=FakeBridge())

    assert tab.scrollback.font().family() == default_scrollback_font().family()


def test_apply_fonts_updates_an_already_constructed_tab(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())

    tab.apply_fonts("Courier New", 14, "Arial", 11)

    assert tab.scrollback.font().family() == "Courier New"
    assert tab.scrollback.font().pointSize() == 14
    assert tab.input_line.font().family() == "Arial"
    assert tab.secondary_input.font().family() == "Arial"


def test_constructing_with_splitter_sizes_applies_them(qapp):
    from PySide6.QtWidgets import QApplication

    # QSplitter only actually distributes sizes once it has real
    # geometry to divide up (show() + processEvents(), not just
    # resize()) -- and treats the given sizes as relative proportions,
    # rescaled to fit the actual available space, not literal final
    # pixel values. [100, 500] (input area *larger* than scrollback) is
    # deliberately the inverse of the built-in 5:1 scrollback-favoring
    # default, so the assertion can't pass by accident from ending up
    # close to the default ratio.
    tab = SessionTab("example.com", 4201, bridge=FakeBridge(), splitter_sizes=[100, 500])
    tab.resize(900, 700)
    tab.show()
    QApplication.processEvents()

    scrollback_size, input_size = tab.splitter.sizes()
    assert input_size > scrollback_size


def test_constructing_with_no_splitter_sizes_uses_the_stretch_factor_default(qapp):
    from PySide6.QtWidgets import QApplication

    tab = SessionTab("example.com", 4201, bridge=FakeBridge())
    tab.resize(900, 700)
    tab.show()
    QApplication.processEvents()

    scrollback_size, input_size = tab.splitter.sizes()
    assert scrollback_size > input_size  # the built-in 5:1 default favors the scrollback


class _FakeHostForSplitter:
    def __init__(self) -> None:
        self.recorded_sizes = None

    def record_splitter_sizes(self, sizes) -> None:
        self.recorded_sizes = list(sizes)


def test_dragging_the_splitter_reports_the_new_sizes_to_the_host(qapp):
    host = _FakeHostForSplitter()
    tab = SessionTab("example.com", 4201, bridge=FakeBridge(), host_window=host)

    tab.splitter.setSizes([300, 200])
    tab.splitter.splitterMoved.emit(300, 1)

    assert host.recorded_sizes == tab.splitter.sizes()


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
