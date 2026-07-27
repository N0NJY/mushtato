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

from typing import List, Optional, Set

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
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
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from engine.storage import PROTOCOLS, CharacterProfile, ScriptRecord, WorldProfile

_PROTOCOL_LABELS = {"telnet": "Telnet", "ssh": "SSH"}


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


class _ScriptsPage(QWidget):
    """Scripts section (Phase 9): a list + name/enabled/source fields +
    Add/Edit/Delete/Save/Cancel -- deliberately the exact same shape as
    _CharactersPage above (checked for reuse before building anything
    new, per CLAUDE.md rule 6), since ScriptRecord is likewise a named,
    multi-entry-per-world thing edited one at a time.

    ``disabled_trigger_scripts`` (a set of script names) is purely a
    *display* hint -- passed in by the caller (AddressBookWindow, which
    can see a currently-open tab's live ScriptWorld) so a script that
    currently has at least one auto-disabled trigger (Checkpoint 4's
    5-consecutive-failures mechanism) shows a visible marker here, not
    just a scrollback line the user may have already scrolled past.
    This dialog has no live ScriptWorld of its own to compute that from
    -- it only ever works with static, on-disk ScriptRecords.
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        scripts: List[ScriptRecord],
        *,
        disabled_trigger_scripts: Optional[Set[str]] = None,
    ) -> None:
        super().__init__(parent)
        self.scripts: List[ScriptRecord] = [
            ScriptRecord(name=s.name, source=s.source, trusted=s.trusted, enabled=s.enabled)
            for s in scripts
        ]
        self._disabled_trigger_scripts = disabled_trigger_scripts or set()
        self._editing_index: Optional[int] = None  # None = not adding/editing; -1 = adding new

        self.list_widget = QListWidget(self)
        self._refresh_list()

        self.name_edit = QLineEdit(self)
        self.enabled_checkbox = QCheckBox("Enabled", self)
        self.enabled_checkbox.setChecked(True)
        self.source_edit = QPlainTextEdit(self)
        self.source_edit.setPlaceholderText(
            "on_trigger('pattern', callback, ...)\non_alias('pattern', callback, ...)\n..."
        )

        self.add_button = QPushButton("Add Script")
        self.edit_button = QPushButton("Edit Script")
        self.delete_button = QPushButton("Delete Script")
        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")

        self.add_button.clicked.connect(self._start_add)
        self.edit_button.clicked.connect(self._start_edit)
        self.delete_button.clicked.connect(self._delete_selected)
        self.save_button.clicked.connect(self._save_current)
        self.cancel_button.clicked.connect(self._cancel_edit)

        form = QFormLayout()
        form.addRow("Name:", self.name_edit)
        form.addRow("", self.enabled_checkbox)

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
        layout.addWidget(QLabel("Source:"))
        layout.addWidget(self.source_edit)
        layout.addLayout(edit_buttons)

        self._set_edit_fields_enabled(False)

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        for record in self.scripts:
            text = record.name
            if not record.enabled:
                text += " (disabled)"
            item = QListWidgetItem(text)
            if record.name in self._disabled_trigger_scripts:
                item.setForeground(QColor(220, 120, 0))
                item.setToolTip(
                    "A trigger from this script was auto-disabled after 5 "
                    "consecutive errors -- fix and re-save to re-enable it."
                )
            self.list_widget.addItem(item)

    def _set_edit_fields_enabled(self, enabled: bool) -> None:
        self.name_edit.setEnabled(enabled)
        self.enabled_checkbox.setEnabled(enabled)
        self.source_edit.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        self.cancel_button.setEnabled(enabled)

    def _start_add(self) -> None:
        self._editing_index = -1
        self.name_edit.clear()
        self.enabled_checkbox.setChecked(True)
        self.source_edit.clear()
        self._set_edit_fields_enabled(True)

    def _start_edit(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        self._editing_index = row
        record = self.scripts[row]
        self.name_edit.setText(record.name)
        self.enabled_checkbox.setChecked(record.enabled)
        self.source_edit.setPlainText(record.source)
        self._set_edit_fields_enabled(True)

    def _save_current(self) -> None:
        if self._editing_index is None:
            return
        name = self.name_edit.text().strip()
        if not name:
            return
        original = (
            None
            if self._editing_index == -1
            else self.scripts[self._editing_index]
        )
        record = ScriptRecord(
            name=name,
            source=self.source_edit.toPlainText(),
            trusted=original.trusted if original is not None else False,
            enabled=self.enabled_checkbox.isChecked(),
        )
        if self._editing_index == -1:
            self.scripts.append(record)
        else:
            self.scripts[self._editing_index] = record
        self._finish_editing()

    def _cancel_edit(self) -> None:
        self._finish_editing()

    def _finish_editing(self) -> None:
        self._editing_index = None
        self.name_edit.clear()
        self.enabled_checkbox.setChecked(True)
        self.source_edit.clear()
        self._set_edit_fields_enabled(False)
        self._refresh_list()

    def _delete_selected(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        del self.scripts[row]
        self._refresh_list()


class WorldPropertiesDialog(QDialog):
    def __init__(
        self,
        parent: Optional[QWidget],
        *,
        world: WorldProfile,
        scripts: Optional[List[ScriptRecord]] = None,
        disabled_trigger_scripts: Optional[Set[str]] = None,
    ) -> None:
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
        self._build_scripts_page(scripts or [], disabled_trigger_scripts)

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
        # SSH support: Telnet (a MU*) unless explicitly switched to SSH
        # (a real Unix shell account) -- ssh_username only meaningful/
        # enabled for the latter. The SSH password is deliberately never
        # a field here or anywhere persisted; always prompted at connect.
        self.protocol_combo = QComboBox(page)
        for value in PROTOCOLS:
            self.protocol_combo.addItem(_PROTOCOL_LABELS[value], userData=value)
        self.protocol_combo.currentIndexChanged.connect(self._update_protocol_field_states)
        self.host_edit = QLineEdit(page)
        self.port_spin = QSpinBox(page)
        self.port_spin.setRange(1, 65535)
        self.ssh_username_edit = QLineEdit(page)
        self.default_character_combo = QComboBox(page)

        form = QFormLayout(page)
        form.addRow("World Name:", self.name_edit)
        form.addRow("Protocol:", self.protocol_combo)
        form.addRow("Host:", self.host_edit)
        form.addRow("Port:", self.port_spin)
        form.addRow("SSH Username:", self.ssh_username_edit)
        form.addRow("Default Character:", self.default_character_combo)
        self._add_page("Basic", page)

    def _update_protocol_field_states(self) -> None:
        self.ssh_username_edit.setEnabled(self._selected_protocol() == "ssh")

    def _selected_protocol(self) -> str:
        return self.protocol_combo.currentData()

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
        # Real and functional (post-Phase-9) -- an application-level
        # Telnet NOP heartbeat, matching Potato's real per-world
        # checkbox of the same name (verified against potato-telnet.tcl
        # -- see gui/windows/telnet_bridge.py's docstring). No longer a
        # placeholder, so it moved out of the disabled section below.
        self.keepalive_checkbox = QCheckBox("Use NOP Keepalive")
        # Real and functional (item 6 of the SSL/proxy/NAWS plan,
        # 2026-07-27) -- encrypts the Telnet/MU* connection itself via
        # implicit TLS, trust-on-first-use certificate verification
        # (see engine/net/client.py's CertificateStore). Also moved out
        # of the disabled placeholder section below, same treatment as
        # keepalive_checkbox got when it became real.
        self.ssl_checkbox = QCheckBox("Use SSL")
        # Real and functional (item 7 of the SSL/proxy/NAWS plan,
        # 2026-07-27) -- engine/net/telnet.py's TelnetNegotiator now
        # really answers these two telnet options instead of always
        # refusing them. Also moved out of the disabled placeholder
        # section below, same treatment as keepalive/ssl above.
        self.naws_checkbox = QCheckBox("Negotiate NAWS")
        self.term_checkbox = QCheckBox("Send Client Info")
        # Real and functional (item 8 of the SSL/proxy/NAWS plan,
        # 2026-07-27) -- a fallback address tried after the primary one
        # fails, on every connect/reconnect attempt (verified against
        # real Potato's own confirmed behavior: fixed try-primary-then-
        # secondary order, never "sticky"). use_ssl2 has no Potato-
        # inherited placeholder to promote out of -- Potato's own real
        # ssl2 field has a UI checkbox too, so this adds one rather than
        # leaving the fallback address unable to use SSL independently
        # of the primary's own Use SSL setting.
        self.host2_edit = QLineEdit(page)
        self.port2_spin = QSpinBox(page)
        self.port2_spin.setRange(0, 65535)
        self.ssl2_checkbox = QCheckBox("Use SSL for 2nd Address")
        # Real and functional (item 9 of the SSL/proxy/NAWS plan,
        # 2026-07-27) -- a hand-rolled SOCKS4/SOCKS4a client
        # (engine/net/socks4.py), matching real Potato's own scope
        # exactly (only SOCKS4 is actually implemented there, despite a
        # proxy-type framework that could support more). A plain host/
        # port pair rather than Potato's "None"/type-dropdown -- SOCKS4
        # is the only real option, so "both fields set" is the on/off
        # toggle, the same convention host2/port2 above already use.
        # This was the *last* Connection-page item modeled on Potato
        # but not yet supported -- the disabled-placeholder section
        # that used to hold it is now gone entirely, not just this one
        # row, since there's nothing left in it to be honest about.
        self.proxy_host_edit = QLineEdit(page)
        self.proxy_port_spin = QSpinBox(page)
        self.proxy_port_spin.setRange(0, 65535)

        form = QFormLayout()
        form.addRow("Login Format:", self.login_format_edit)
        form.addRow("Login Delay:", self.login_delay_spin)
        form.addRow("", self.keepalive_checkbox)
        form.addRow("", self.ssl_checkbox)
        form.addRow("", self.naws_checkbox)
        form.addRow("", self.term_checkbox)
        form.addRow("2nd Address:", self.host2_edit)
        form.addRow("2nd Port:", self.port2_spin)
        form.addRow("", self.ssl2_checkbox)
        form.addRow("Proxy Host:", self.proxy_host_edit)
        form.addRow("Proxy Port:", self.proxy_port_spin)

        layout = QVBoxLayout(page)
        layout.addLayout(form)
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

    # -- Scripts (Phase 9) --------------------------------------------------

    def _build_scripts_page(
        self, scripts: List[ScriptRecord], disabled_trigger_scripts: Optional[Set[str]]
    ) -> None:
        self._scripts_page = _ScriptsPage(
            self, scripts, disabled_trigger_scripts=disabled_trigger_scripts
        )
        self._add_page("Scripts", self._scripts_page)

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
        self.protocol_combo.setCurrentIndex(PROTOCOLS.index(world.protocol))
        self.host_edit.setText(world.host)
        self.port_spin.setValue(world.port)
        self.ssh_username_edit.setText(world.ssh_username)
        self._update_protocol_field_states()
        self._refresh_default_character_combo()
        index = self.default_character_combo.findText(world.default_character)
        self.default_character_combo.setCurrentIndex(index if index >= 0 else 0)

        self.login_format_edit.setText(world.login_format)
        self.login_delay_spin.setValue(world.login_delay)
        self.keepalive_checkbox.setChecked(world.nop_keepalive)
        self.ssl_checkbox.setChecked(world.use_ssl)
        self.naws_checkbox.setChecked(world.telnet_naws)
        self.term_checkbox.setChecked(world.telnet_term)
        self.host2_edit.setText(world.host2)
        self.port2_spin.setValue(world.port2)
        self.ssl2_checkbox.setChecked(world.use_ssl2)
        self.proxy_host_edit.setText(world.proxy_host)
        self.proxy_port_spin.setValue(world.proxy_port)

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
            # auto_login isn't editable on this dialog (it's a checkbox
            # on the Address Book's own Worlds list) -- carried over
            # unchanged, same treatment as connect_count above. A real,
            # pre-existing bug found and fixed in the same pass as
            # adding nop_keepalive below: this field was never being
            # passed through at all, meaning saving *any* Properties
            # change used to silently reset auto_login back to False.
            auto_login=self._world.auto_login,
            nop_keepalive=self.keepalive_checkbox.isChecked(),
            use_ssl=self.ssl_checkbox.isChecked(),
            telnet_naws=self.naws_checkbox.isChecked(),
            telnet_term=self.term_checkbox.isChecked(),
            host2=self.host2_edit.text().strip(),
            port2=self.port2_spin.value(),
            use_ssl2=self.ssl2_checkbox.isChecked(),
            proxy_host=self.proxy_host_edit.text().strip(),
            proxy_port=self.proxy_port_spin.value(),
            protocol=self._selected_protocol(),
            ssh_username=self.ssh_username_edit.text().strip(),
            # mail_* isn't editable on this dialog either (it's set from
            # the Mail Window itself, on Send) -- carried over unchanged,
            # same treatment as auto_login/connect_count above. A real
            # bug found while adding SSH support: this dialog was never
            # threading these through at all, meaning saving *any*
            # Properties change (even something unrelated, like a
            # Character edit) silently reset a world's Mail Window
            # settings back to defaults.
            mail_format=self._world.mail_format,
            mail_format_custom=self._world.mail_format_custom,
            mail_convert_returns=self._world.mail_convert_returns,
            mail_convert_returns_to=self._world.mail_convert_returns_to,
            # splitter_sizes isn't editable on this dialog either (it's
            # only ever set by dragging the splitter in an open tab) --
            # carried over unchanged, same treatment as mail_*/auto_login
            # above, to avoid the identical class of bug already fixed
            # twice for those fields.
            splitter_sizes=self._world.splitter_sizes,
        )

    def result_scripts(self) -> List[ScriptRecord]:
        """The current list of saved scripts (Phase 9) -- separate from
        result_profile() since scripts live in their own per-world file
        (engine/storage/script_store.py), not on WorldProfile itself.
        """
        return list(self._scripts_page.scripts)
