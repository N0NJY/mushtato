"""Add/Edit World dialog for the address book (Phase 6)."""

from __future__ import annotations

import dataclasses
from typing import Optional

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from engine.storage import DEFAULT_PROTOCOL, PROTOCOLS, WorldProfile

_PROTOCOL_LABELS = {"telnet": "Telnet", "ssh": "SSH"}


class WorldEditDialog(QDialog):
    def __init__(self, parent=None, *, world: Optional[WorldProfile] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit World" if world is not None else "Add World")
        # Kept so result_profile() can preserve everything this quick
        # dialog doesn't expose (characters, auto-sends, login format/
        # delay, connect_count -- Phase 8b) rather than silently
        # discarding them -- a real data-loss bug found while adding
        # those fields: this dialog used to always build a brand new
        # WorldProfile from just its 4 visible fields.
        self._original_world = world

        self.name_edit = QLineEdit(world.name if world else "")
        self.host_edit = QLineEdit(world.host if world else "")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(world.port if world else 23)
        self.notes_edit = QLineEdit(world.notes if world else "")

        # SSH support: a saved world is Telnet (a MU*) unless explicitly
        # switched to SSH (a real Unix shell account) -- ssh_username is
        # only meaningful/enabled for the latter. The SSH *password* is
        # deliberately never a field here or anywhere persisted (Rick's
        # explicit call) -- it's always prompted fresh at connect time.
        self.protocol_combo = QComboBox(self)
        for value in PROTOCOLS:
            self.protocol_combo.addItem(_PROTOCOL_LABELS[value], userData=value)
        initial_protocol = world.protocol if world else DEFAULT_PROTOCOL
        self.protocol_combo.setCurrentIndex(PROTOCOLS.index(initial_protocol))
        self.protocol_combo.currentIndexChanged.connect(self._update_field_states)

        self.ssh_username_edit = QLineEdit(world.ssh_username if world else "")

        form = QFormLayout()
        form.addRow("Name:", self.name_edit)
        form.addRow("Protocol:", self.protocol_combo)
        form.addRow("Host:", self.host_edit)
        form.addRow("Port:", self.port_spin)
        form.addRow("SSH Username:", self.ssh_username_edit)
        form.addRow("Notes:", self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self._update_field_states()

    def _update_field_states(self) -> None:
        self.ssh_username_edit.setEnabled(self._selected_protocol() == "ssh")

    def _selected_protocol(self) -> str:
        return self.protocol_combo.currentData()

    def result_profile(self) -> Optional[WorldProfile]:
        """Build a WorldProfile from the current field values.

        Returns None if name or host is blank -- callers should treat
        that as "nothing to save", not raise. When editing an existing
        world, everything this dialog doesn't show (characters, auto-
        sends, login format/delay, connect_count) is carried over
        unchanged from the original rather than reset to defaults --
        only Add World (no original) starts everything blank.
        """
        name = self.name_edit.text().strip()
        host = self.host_edit.text().strip()
        if not name or not host:
            return None
        if self._original_world is not None:
            return dataclasses.replace(
                self._original_world,
                name=name,
                host=host,
                port=self.port_spin.value(),
                notes=self.notes_edit.text(),
                protocol=self._selected_protocol(),
                ssh_username=self.ssh_username_edit.text().strip(),
            )
        return WorldProfile(
            name=name,
            host=host,
            port=self.port_spin.value(),
            notes=self.notes_edit.text(),
            protocol=self._selected_protocol(),
            ssh_username=self.ssh_username_edit.text().strip(),
        )
