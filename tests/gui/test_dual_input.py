"""Headless tests for Phase 6's dual input: two simultaneous boxes,
both sending to the same connection, each with independent history.
Now lives on SessionTab (Phase 7e) rather than MainWindow itself.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent

from engine.storage.address_book import WorldProfile
from gui.windows.history_line_edit import HistoryLineEdit
from gui.windows.session_tab import SessionTab, _split_input_lines
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
        self.world_saves = []  # list of (world, sizes) tuples

    def record_splitter_sizes(self, sizes) -> None:
        self.recorded_sizes = list(sizes)

    def save_splitter_sizes_for_world(self, world, sizes) -> None:
        self.world_saves.append((world, list(sizes)))


def test_dragging_the_splitter_reports_the_new_sizes_to_the_host(qapp):
    host = _FakeHostForSplitter()
    tab = SessionTab("example.com", 4201, bridge=FakeBridge(), host_window=host)

    tab.splitter.setSizes([300, 200])
    tab.splitter.splitterMoved.emit(300, 1)

    assert host.recorded_sizes == tab.splitter.sizes()
    assert host.world_saves == []


def test_dragging_the_splitter_on_a_world_tab_saves_to_the_world_not_globally(qapp):
    # Post-1.1.0: a tab with a saved world persists its splitter size
    # per-world instead of to the app-wide preference -- debounced on
    # SessionTab's own timer (see _on_splitter_moved), so nothing is
    # recorded until that timer actually fires.
    host = _FakeHostForSplitter()
    world = WorldProfile(name="Example", host="example.com", port=4201)
    tab = SessionTab("example.com", 4201, bridge=FakeBridge(), host_window=host, world=world)

    tab.splitter.setSizes([300, 200])
    tab.splitter.splitterMoved.emit(300, 1)

    assert host.recorded_sizes is None
    assert host.world_saves == []

    tab._save_splitter_sizes_for_world_now()

    assert host.recorded_sizes is None
    assert host.world_saves == [(world, list(tab.splitter.sizes()))]


def test_dragging_the_splitter_on_a_world_tab_debounces_the_save(qapp):
    from PySide6.QtTest import QTest

    host = _FakeHostForSplitter()
    world = WorldProfile(name="Example", host="example.com", port=4201)
    tab = SessionTab("example.com", 4201, bridge=FakeBridge(), host_window=host, world=world)

    tab.splitter.setSizes([300, 200])
    tab.splitter.splitterMoved.emit(300, 1)
    assert host.world_saves == []

    QTest.qWait(500)

    assert host.world_saves == [(world, list(tab.splitter.sizes()))]


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


# -- multi-line paste (Potato parity, pending-list item 12) ---------------
#
# Real Potato's own input window is a genuine multi-line Tk Text widget;
# pasting several lines into it just shows several lines, inherent to any
# multi-line widget -- confirmed against ~/git/potato/potato.vfs's real
# source before implementing this. Return sends the *entire* box content,
# split on newline, each line processed/sent separately, then clears the
# box (real Potato's own send_mushage, matched here by
# gui.windows.session_tab._split_input_lines +
# SessionTab._on_primary_send/_on_secondary_send).


def test_split_input_lines_single_line():
    assert _split_input_lines("look") == ["look"]


def test_split_input_lines_empty_box_is_one_blank_line():
    # A single Return on a genuinely empty box must still behave exactly
    # as it did before this feature existed -- one blank line, not zero.
    assert _split_input_lines("") == [""]


def test_split_input_lines_multiple_lines_no_trailing_newline():
    assert _split_input_lines("north\nsouth\nlook") == ["north", "south", "look"]


def test_split_input_lines_strips_exactly_one_trailing_newline():
    # Routine after pasting a block copied from elsewhere, which commonly
    # ends with its own trailing newline -- must not become an extra,
    # unwanted blank send tacked onto the end.
    assert _split_input_lines("north\nsouth\n") == ["north", "south"]


def test_split_input_lines_keeps_an_interior_blank_line():
    # A *real* blank line in the middle of a paste is a deliberate blank
    # send, not a trailing-newline artifact -- must not be silently
    # dropped the same way.
    assert _split_input_lines("north\n\nsouth") == ["north", "", "south"]


def test_split_input_lines_only_strips_one_trailing_newline_not_several():
    assert _split_input_lines("north\n\n") == ["north", ""]


def test_pasting_multiple_lines_shows_them_as_separate_visible_lines(qapp):
    # The literal claim from the pending-list report: pasted content is
    # genuinely visible as multiple lines, not collapsed into one long
    # string -- proven via a real clipboard + a real .paste() call, not
    # just calling setPlainText() directly.
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())
    qapp.clipboard().setText("north\nsouth\nlook")

    tab.input_line.paste()

    assert tab.input_line.document().blockCount() == 3
    assert tab.input_line.text() == "north\nsouth\nlook"


def test_returning_a_pasted_multiline_block_sends_each_line_separately(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)
    qapp.clipboard().setText("north\nsouth\nlook")
    tab.input_line.paste()

    tab.input_line.returnPressed.emit()

    assert bridge.sent == ["north", "south", "look"]
    assert tab.input_line.text() == ""  # box cleared after sending, same as single-line


def test_pasted_trailing_newline_does_not_send_an_extra_blank_line(qapp):
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)
    qapp.clipboard().setText("north\nsouth\n")
    tab.input_line.paste()

    tab.input_line.returnPressed.emit()

    assert bridge.sent == ["north", "south"]


def test_secondary_input_multiline_paste_bypasses_commands_on_every_line(qapp):
    # Same "never reinterpreted" guarantee the single-line secondary box
    # already has (a pose starting with "/" is sent literally) -- proven
    # here across every line of a multi-line paste, not just the first.
    bridge = FakeBridge()
    tab = SessionTab("example.com", 4201, bridge=bridge)
    tab.secondary_input.setText("waves hello\n/quit\nsmiles")

    tab.secondary_input.returnPressed.emit()

    # If "/quit" had been reinterpreted as a real command it would never
    # have reached the bridge at all (and would have closed the tab) --
    # its literal presence here, third in order, proves it was sent as
    # plain text on its own line, not executed.
    assert bridge.sent == ["waves hello", "/quit", "smiles"]


def test_multiline_paste_is_recorded_as_one_history_entry(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())
    tab.input_line.setText("north\nsouth")

    tab.input_line.returnPressed.emit()
    tab.input_line.setText("look")
    tab.input_line.returnPressed.emit()

    _press(tab.input_line, Qt.Key.Key_Up)
    assert tab.input_line.text() == "look"
    _press(tab.input_line, Qt.Key.Key_Up)
    assert tab.input_line.text() == "north\nsouth"  # the whole block, one entry


def test_up_down_move_cursor_normally_within_multiline_content(qapp):
    # History recall only kicks in when the cursor is already on the
    # first/last line -- with genuine multi-line content and the cursor
    # in the middle, Up/Down must move the cursor, not replace the box's
    # content with a history entry.
    edit = HistoryLineEdit()
    edit.setText("first")
    edit.returnPressed.emit()
    edit.setText("north\nsouth\nlook")
    cursor = edit.textCursor()
    cursor.movePosition(cursor.MoveOperation.Start)
    cursor.movePosition(cursor.MoveOperation.NextBlock)  # onto the middle line ("south")
    edit.setTextCursor(cursor)

    _press(edit, Qt.Key.Key_Up)

    assert edit.text() == "north\nsouth\nlook"  # unchanged -- not replaced by history
    assert edit.textCursor().blockNumber() == 0  # cursor moved up a line instead


def test_shift_return_inserts_a_literal_newline_instead_of_sending(qapp):
    # Real QTest.keyClick dispatch (not a hand-built QKeyEvent passed
    # directly to keyPressEvent) -- proves the base QPlainTextEdit's own
    # real newline-insertion behavior actually fires when this class
    # defers to it, not just that this class's own code chose to defer.
    from PySide6.QtTest import QTest

    tab = SessionTab("example.com", 4201, bridge=FakeBridge())
    tab.input_line.setText("north")
    sent = []
    tab.input_line.returnPressed.connect(lambda: sent.append(1))

    QTest.keyClick(tab.input_line, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)

    assert sent == []
    assert tab.input_line.document().blockCount() == 2
    assert tab.input_line.text() == "north\n"
