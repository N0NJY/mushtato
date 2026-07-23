"""World Properties dialog (Phase 8b): Potato-parity depth for a saved
world -- characters, auto-sends, notes, connection specifics -- reached
via a "Properties..." button on AddressBookWindow, additive to the
existing quick WorldEditDialog (name/host/port/notes) rather than
replacing it.

Layout modeled on Potato's own real World Properties window (verified
against ~/git/potato/potato.vfs's configureWorld proc): a category list
on the left, a matching content page on the right -- here a QListWidget
+ QStackedWidget rather than Potato's ttk::treeview + canvas, but the
same shape. Scoped to 5 sections (Basic, Characters, Connection,
Auto-Sends, Notes) out of Potato's real 13 -- the rest either duplicate
what MushTato's own theme/hotkey system already handles differently, or
would need real engine/net work (SSL, proxy, telnet negotiation toggles)
that's out of scope for this phase; those specific fields are still
shown, but disabled, in the Connection page -- visible and honest about
what's not built yet, matching the Phase 7d toolbar placeholder pattern,
not hidden.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from engine.storage import CharacterProfile, WorldProfile


class _CharactersPage(QWidget):
    """Characters section: a list + Name/Password fields + Add/Edit/
    Delete/Save/Cancel -- matches Potato's real Characters section
    (configureWorldCharsAddEdit/Finish/Delete) shape: explicit Add/Edit
    populates the fields, Save/Cancel commits or discards, rather than
    editing the list inline.
    """

    characterAdded = Signal(str)  # emitted with the new name -- NOT emitted on edit

    def __init__(self, parent: Optional[QWidget], characters: List[CharacterProfile]) -> None:
        super().__init__(parent)
        self.characters: List[CharacterProfile] = [
            CharacterProfile(name=c.name, password=c.password) for c in characters
        ]
        self._editing_index: Optional[int] = None  # None = not adding/editing; -1 = adding new

        self.list_widget = QListWidget(self)
        self._refresh_list()

        self.name_edit = QLineEdit(self)
        self.password_edit = QLineEdit(self)
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.add_button = QPushButton("Add Character")
        self.edit_button = QPushButton("Edit Character")
        self.delete_button = QPushButton("Delete Character")
        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")

        self.add_button.clicked.connect(self._start_add)
        self.edit_button.clicked.connect(self._start_edit)
        self.delete_button.clicked.connect(self._delete_selected)
        self.save_button.clicked.connect(self._save_current)
        self.cancel_button.clicked.connect(self._cancel_edit)

        form = QFormLayout()
        form.addRow("Character:", self.name_edit)
        form.addRow("Password:", self.password_edit)

        edit_buttons = QHBoxLayout()
        edit_buttons.addWidget(self.save_button)
        edit_buttons.addWidget(self.cancel_button)

        list_buttons = QHBoxLayout()
        list_buttons.addWidget(self.add_button)
        list_buttons.addWidget(self.edit_button)
        list_buttons.addWidget(self.delete_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)
        layout.addLayout(list_buttons)
        layout.addLayout(form)
        layout.addLayout(edit_buttons)

        self._set_edit_fields_enabled(False)

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        for character in self.characters:
            self.list_widget.addItem(character.name)

    def _set_edit_fields_enabled(self, enabled: bool) -> None:
        self.name_edit.setEnabled(enabled)
        self.password_edit.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        self.cancel_button.setEnabled(enabled)

    def _start_add(self) -> None:
        self._editing_index = -1
        self.name_edit.clear()
        self.password_edit.clear()
        self._set_edit_fields_enabled(True)

    def _start_edit(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        self._editing_index = row
        self.name_edit.setText(self.characters[row].name)
        self.password_edit.setText(self.characters[row].password)
        self._set_edit_fields_enabled(True)

    def _save_current(self) -> None:
        if self._editing_index is None:
            return
        name = self.name_edit.text().strip()
        if not name:
            return
        profile = CharacterProfile(name=name, password=self.password_edit.text())
        was_adding = self._editing_index == -1
        if was_adding:
            self.characters.append(profile)
        else:
            self.characters[self._editing_index] = profile
        self._finish_editing()
        if was_adding:
            self.characterAdded.emit(profile.name)

    def _cancel_edit(self) -> None:
        self._finish_editing()

    def _finish_editing(self) -> None:
        self._editing_index = None
        self.name_edit.clear()
        self.password_edit.clear()
        self._set_edit_fields_enabled(False)
        self._refresh_list()

    def _delete_selected(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        del self.characters[row]
        self._refresh_list()


class WorldPropertiesDialog(QDialog):
    def __init__(self, parent: Optional[QWidget], *, world: WorldProfile) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Properties for '{world.name}'")
        self._world = world
        self.resize(650, 500)

        self.category_list = QListWidget(self)
        self.pages = QStackedWidget(self)

        self._build_basic_page()
        self._build_characters_page(world.characters)
        self._build_connection_page()
        self._build_autosends_page()
        self._build_notes_page()

        self.category_list.setCurrentRow(0)
        self.category_list.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.category_list.currentRowChanged.connect(self._refresh_default_character_combo)

        splitter_layout = QHBoxLayout()
        splitter_layout.addWidget(self.category_list, 0)
        splitter_layout.addWidget(self.pages, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(splitter_layout)
        layout.addWidget(buttons)

        self._load_from_world(world)
        self._characters_page.characterAdded.connect(self._on_character_added)

    def _add_page(self, title: str, widget: QWidget) -> None:
        self.category_list.addItem(title)
        self.pages.addWidget(widget)

    def _on_character_added(self, name: str) -> None:
        # Rick's real-world report: adding a Character on this page
        # didn't do anything on connect until he *also* went to Basic
        # and picked it from Default Character -- an easy-to-miss
        # second step on a different page. If nothing is set as
        # default yet, the first Character you add becomes it
        # automatically; adding a second one later never overrides an
        # existing default -- that stays an explicit choice.
        was_none = self.default_character_combo.currentText() in ("(None)", "")
        self._refresh_default_character_combo()
        if was_none:
            self.default_character_combo.setCurrentText(name)

    # -- Basic -----------------------------------------------------------

    def _build_basic_page(self) -> None:
        page = QWidget(self)
        self.name_edit = QLineEdit(page)
        self.host_edit = QLineEdit(page)
        self.port_spin = QSpinBox(page)
        self.port_spin.setRange(1, 65535)
        self.default_character_combo = QComboBox(page)

        form = QFormLayout(page)
        form.addRow("World Name:", self.name_edit)
        form.addRow("Host:", self.host_edit)
        form.addRow("Port:", self.port_spin)
        form.addRow("Default Character:", self.default_character_combo)
        self._add_page("Basic", page)

    def _refresh_default_character_combo(self) -> None:
        current = self.default_character_combo.currentText()
        self.default_character_combo.clear()
        self.default_character_combo.addItem("(None)")
        for character in self._characters_page.characters:
            self.default_character_combo.addItem(character.name)
        index = self.default_character_combo.findText(current)
        self.default_character_combo.setCurrentIndex(index if index >= 0 else 0)

    # -- Characters --------------------------------------------------------

    def _build_characters_page(self, characters: List[CharacterProfile]) -> None:
        self._characters_page = _CharactersPage(self, characters)
        self._add_page("Characters", self._characters_page)

    # -- Connection --------------------------------------------------------

    def _build_connection_page(self) -> None:
        page = QWidget(self)
        self.login_format_edit = QLineEdit(page)
        self.login_delay_spin = QDoubleSpinBox(page)
        self.login_delay_spin.setRange(0.0, 60.0)
        self.login_delay_spin.setSingleStep(0.5)
        self.login_delay_spin.setSuffix(" s")

        form = QFormLayout()
        form.addRow("Login Format:", self.login_format_edit)
        form.addRow("Login Delay:", self.login_delay_spin)

        # Not yet supported by engine/net -- shown disabled, not hidden,
        # same honesty principle as Phase 7d's toolbar placeholders.
        # No WorldProfile fields back these; there's nothing real to
        # persist for a setting the engine can't act on yet.
        placeholder_note = QLabel(
            "The following are modeled on Potato's real Connection/Telnet "
            "settings but aren't supported by MushTato's connection engine "
            "yet -- shown disabled, not hidden."
        )
        placeholder_note.setWordWrap(True)

        self.ssl_checkbox = QCheckBox("Use SSL")
        self.ssl_checkbox.setEnabled(False)
        self.host2_edit = QLineEdit(page)
        self.host2_edit.setEnabled(False)
        self.port2_spin = QSpinBox(page)
        self.port2_spin.setRange(1, 65535)
        self.port2_spin.setEnabled(False)
        self.proxy_combo = QComboBox(page)
        self.proxy_combo.addItem("None")
        self.proxy_combo.setEnabled(False)
        self.naws_checkbox = QCheckBox("Negotiate NAWS")
        self.naws_checkbox.setEnabled(False)
        self.keepalive_checkbox = QCheckBox("Use NOP Keepalive")
        self.keepalive_checkbox.setEnabled(False)
        self.term_checkbox = QCheckBox("Send Client Info")
        self.term_checkbox.setEnabled(False)

        placeholder_form = QFormLayout()
        placeholder_form.addRow("2nd Address:", self.host2_edit)
        placeholder_form.addRow("2nd Port:", self.port2_spin)
        placeholder_form.addRow("SSL:", self.ssl_checkbox)
        placeholder_form.addRow("Proxy:", self.proxy_combo)
        placeholder_form.addRow("Telnet:", self.naws_checkbox)
        placeholder_form.addRow("", self.keepalive_checkbox)
        placeholder_form.addRow("", self.term_checkbox)

        layout = QVBoxLayout(page)
        layout.addLayout(form)
        layout.addWidget(placeholder_note)
        layout.addLayout(placeholder_form)
        layout.addStretch(1)
        self._add_page("Connection", page)

    # -- Auto-Sends --------------------------------------------------------

    def _build_autosends_page(self) -> None:
        page = QWidget(self)
        self.autosend_firstconnect_edit = QPlainTextEdit(page)
        self.autosend_connect_edit = QPlainTextEdit(page)
        self.autosend_login_edit = QPlainTextEdit(page)

        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Send upon first connect ever, before login:"))
        layout.addWidget(self.autosend_firstconnect_edit)
        layout.addWidget(QLabel("Send on every connect, before login:"))
        layout.addWidget(self.autosend_connect_edit)
        layout.addWidget(QLabel("Send on every connect, after login:"))
        layout.addWidget(self.autosend_login_edit)
        self._add_page("Auto-Sends", page)

    # -- Notes -----------------------------------------------------------

    def _build_notes_page(self) -> None:
        page = QWidget(self)
        self.notes_edit = QPlainTextEdit(page)
        layout = QVBoxLayout(page)
        layout.addWidget(self.notes_edit)
        self._add_page("Notes", page)

    # -- load/save -----------------------------------------------------

    def _load_from_world(self, world: WorldProfile) -> None:
        self.name_edit.setText(world.name)
        self.host_edit.setText(world.host)
        self.port_spin.setValue(world.port)
        self._refresh_default_character_combo()
        index = self.default_character_combo.findText(world.default_character)
        self.default_character_combo.setCurrentIndex(index if index >= 0 else 0)

        self.login_format_edit.setText(world.login_format)
        self.login_delay_spin.setValue(world.login_delay)

        self.autosend_firstconnect_edit.setPlainText(world.autosend_firstconnect)
        self.autosend_connect_edit.setPlainText(world.autosend_connect)
        self.autosend_login_edit.setPlainText(world.autosend_login)

        self.notes_edit.setPlainText(world.notes)

    def result_profile(self) -> Optional[WorldProfile]:
        """Build the updated WorldProfile from current field values.

        Returns None if name or host is blank, same "nothing to save"
        convention WorldEditDialog already uses. connect_count isn't
        editable here -- carried over unchanged from the original.
        """
        name = self.name_edit.text().strip()
        host = self.host_edit.text().strip()
        if not name or not host:
            return None

        default_character = self.default_character_combo.currentText()
        if default_character == "(None)":
            default_character = ""

        return WorldProfile(
            name=name,
            host=host,
            port=self.port_spin.value(),
            notes=self.notes_edit.toPlainText(),
            characters=list(self._characters_page.characters),
            default_character=default_character,
            login_format=self.login_format_edit.text(),
            login_delay=self.login_delay_spin.value(),
            autosend_firstconnect=self.autosend_firstconnect_edit.toPlainText(),
            autosend_connect=self.autosend_connect_edit.toPlainText(),
            autosend_login=self.autosend_login_edit.toPlainText(),
            connect_count=self._world.connect_count,
        )
