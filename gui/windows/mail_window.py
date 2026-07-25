"""Mail Window (Phase 12b): a compose/send-only dialog for a world's
own mail system, modeled on Potato's real ``::potato::mailWindow`` --
verified against the actual source (``potato.tcl``, ``potato-config.
tcl``) rather than guessed. See ``engine/mail_format.py`` for the
verified format templates and the pure command-building logic.

Confirmed via checkpoint (2026-07-25), all matching the Potato-parity
option over the alternative:

- **Compose-only, no list/read/search** -- Potato's own real source has
  none of that either; the mail window is purely "write a message,
  send it."
- **One window per tab**, not unlimited simultaneous windows like
  Phase 12a's Text Editor -- matches Potato's real ``.mailWindow$c``
  behavior (a second attempt re-shows the existing one). Owned by
  ``SessionTab`` as a single ``Optional[MailWindow]`` slot, the same
  per-tab-not-global pattern ``find_bar`` already uses.
- **Format/Custom-template/Convert-Returns are edited only here**, not
  in a separate World Properties page -- matches Potato's real model,
  where the compose window is the only place these ever get edited.
- **No unsaved-changes-on-close prompt** -- confirmed from Potato's own
  source: ``<Destroy>`` just cleans up variables, ``<Escape>`` invokes
  Cancel directly, no confirmation dialog anywhere. Deliberately
  different from Phase 12a's Text Editor (which does prompt) -- not an
  inconsistency, this is what the real reference behavior actually is.

Independent Edit menu (Cut/Copy/Paste/Undo/Redo/Select All on the body
widget), for the identical, already-confirmed reason Phase 12a's Text
Editor needed one: ``QApplication.focusWidget()`` cannot reach a
separate top-level window's own widget once this window is activated.
Uses MushTato's own established simpler "always enabled, no-op if
nothing to act on" convention rather than Potato's own more elaborate
dynamic Copy/Cut/Paste enable-state logic (``editMenuCXV``).
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from engine.mail_format import (
    CUSTOM_FORMAT,
    FORMAT_NAMES,
    FORMAT_TEMPLATES,
    build_mail_commands,
    escape_special_characters,
    fields_used_by_template,
)
from engine.storage import WorldProfile


class MailWindow(QMainWindow):
    closed = Signal()

    def __init__(
        self,
        world: Optional[WorldProfile],
        send_line: Callable[[str], None],
        *,
        persist_world: Optional[Callable[[WorldProfile], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._world = world
        self._send_line = send_line
        self._persist_world = persist_world
        # A world-less tab (direct-connect, or a standalone test) still
        # gets a fully working compose window -- it just has nothing to
        # read defaults from or persist changes to, matching how
        # auto-sends/character-login already degrade gracefully with no
        # WorldProfile at all. Defaults are read from a bare WorldProfile
        # rather than duplicating its literal default strings a second
        # time here.
        defaults = world if world is not None else WorldProfile(name="", host="", port=0)

        self.setWindowTitle(f"Send Mail — {world.name}" if world is not None else "Send Mail")

        self.to_edit = QLineEdit(self)
        self.cc_edit = QLineEdit(self)
        self.bcc_edit = QLineEdit(self)
        self.subject_edit = QLineEdit(self)

        self.format_combo = QComboBox(self)
        self.format_combo.addItems(FORMAT_NAMES)
        self.format_combo.setCurrentText(defaults.mail_format)
        self.format_combo.currentTextChanged.connect(self._on_format_changed)

        self.custom_edit = QLineEdit(self)
        self.custom_edit.setText(defaults.mail_format_custom)
        self.custom_edit.textChanged.connect(self._update_field_states)

        self.body_edit = QPlainTextEdit(self)
        self.body_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

        self.convert_checkbox = QCheckBox("Convert returns?", self)
        self.convert_checkbox.setChecked(defaults.mail_convert_returns)
        self.convert_to_edit = QLineEdit(self)
        self.convert_to_edit.setText(defaults.mail_convert_returns_to)
        self.convert_to_edit.setMaximumWidth(60)

        self.send_button = QPushButton("Send", self)
        self.send_button.clicked.connect(self._on_send)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self.close)

        form = QFormLayout()
        form.addRow("Recipient:", self.to_edit)
        form.addRow("CC:", self.cc_edit)
        form.addRow("BCC:", self.bcc_edit)
        form.addRow("Subject:", self.subject_edit)
        form.addRow("Format:", self.format_combo)
        form.addRow("Custom:", self.custom_edit)

        convert_row = QHBoxLayout()
        convert_row.addWidget(self.convert_checkbox)
        convert_row.addWidget(QLabel("Convert To:", self))
        convert_row.addWidget(self.convert_to_edit)
        convert_row.addStretch()

        button_row = QHBoxLayout()
        button_row.addWidget(self.send_button)
        button_row.addWidget(self.cancel_button)
        button_row.addStretch()

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(form)
        layout.addWidget(self.body_edit)
        layout.addLayout(convert_row)
        layout.addLayout(button_row)
        self.setCentralWidget(central)

        self._build_menu()
        self._on_format_changed(self.format_combo.currentText())

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.close)
        self.to_edit.setFocus()

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction("Escape Special Characters", self._on_escape_special_characters)

        edit_menu = menu_bar.addMenu("&Edit")
        edit_menu.addAction("Undo", self.body_edit.undo).setShortcut(
            QKeySequence(QKeySequence.StandardKey.Undo)
        )
        edit_menu.addAction("Redo", self.body_edit.redo).setShortcut(
            QKeySequence(QKeySequence.StandardKey.Redo)
        )
        edit_menu.addSeparator()
        edit_menu.addAction("Cut", self.body_edit.cut).setShortcut(
            QKeySequence(QKeySequence.StandardKey.Cut)
        )
        edit_menu.addAction("Copy", self.body_edit.copy).setShortcut(
            QKeySequence(QKeySequence.StandardKey.Copy)
        )
        edit_menu.addAction("Paste", self.body_edit.paste).setShortcut(
            QKeySequence(QKeySequence.StandardKey.Paste)
        )
        edit_menu.addSeparator()
        edit_menu.addAction("Select All", self.body_edit.selectAll).setShortcut(
            QKeySequence(QKeySequence.StandardKey.SelectAll)
        )

    # -- format-driven field enable/disable -----------------------------

    def _active_template(self) -> str:
        format_name = self.format_combo.currentText()
        if format_name == CUSTOM_FORMAT:
            return self.custom_edit.text()
        return FORMAT_TEMPLATES[format_name]

    def _on_format_changed(self, format_name: str) -> None:
        self.custom_edit.setEnabled(format_name == CUSTOM_FORMAT)
        self._update_field_states()

    def _update_field_states(self) -> None:
        used = set(fields_used_by_template(self._active_template()))
        self.to_edit.setEnabled("to" in used)
        self.cc_edit.setEnabled("cc" in used)
        self.bcc_edit.setEnabled("bcc" in used)
        self.subject_edit.setEnabled("subject" in used)

    # -- actions ---------------------------------------------------------

    def _on_escape_special_characters(self) -> None:
        self.body_edit.setPlainText(escape_special_characters(self.body_edit.toPlainText()))

    def _on_send(self) -> None:
        format_name = self.format_combo.currentText()
        commands = build_mail_commands(
            self._active_template(),
            to=self.to_edit.text(),
            cc=self.cc_edit.text(),
            bcc=self.bcc_edit.text(),
            subject=self.subject_edit.text(),
            body=self.body_edit.toPlainText(),
            convert_returns=self.convert_checkbox.isChecked(),
            convert_returns_to=self.convert_to_edit.text(),
        )
        for line in commands:
            self._send_line(line)

        if self._world is not None:
            # Matches Potato's own real persistence exactly: the custom
            # template is only ever updated when Custom was actually
            # the selected format, leaving a previously-saved custom
            # template untouched otherwise.
            if format_name == CUSTOM_FORMAT:
                self._world.mail_format_custom = self.custom_edit.text()
            self._world.mail_format = format_name
            self._world.mail_convert_returns = self.convert_checkbox.isChecked()
            self._world.mail_convert_returns_to = self.convert_to_edit.text()
            if self._persist_world is not None:
                self._persist_world(self._world)

        self.close()

    def closeEvent(self, event) -> None:  # noqa: N802 -- Qt override signature
        # No unsaved-changes prompt -- confirmed from Potato's own real
        # source (mailWindowCleanup just unsets variables; Escape
        # invokes Cancel directly), not an oversight or inconsistency
        # with the Text Editor's own different (prompting) behavior.
        self.closed.emit()
        super().closeEvent(event)
