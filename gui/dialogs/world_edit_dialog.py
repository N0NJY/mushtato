"""Add/Edit World dialog for the address book (Phase 6)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QSpinBox, QVBoxLayout

from engine.storage import WorldProfile


class WorldEditDialog(QDialog):
    def __init__(self, parent=None, *, world: Optional[WorldProfile] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit World" if world is not None else "Add World")

        self.name_edit = QLineEdit(world.name if world else "")
        self.host_edit = QLineEdit(world.host if world else "")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(world.port if world else 23)
        self.notes_edit = QLineEdit(world.notes if world else "")

        form = QFormLayout()
        form.addRow("Name:", self.name_edit)
        form.addRow("Host:", self.host_edit)
        form.addRow("Port:", self.port_spin)
        form.addRow("Notes:", self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def result_profile(self) -> Optional[WorldProfile]:
        """Build a WorldProfile from the current field values.

        Returns None if name or host is blank -- callers should treat
        that as "nothing to save", not raise.
        """
        name = self.name_edit.text().strip()
        host = self.host_edit.text().strip()
        if not name or not host:
            return None
        return WorldProfile(
            name=name, host=host, port=self.port_spin.value(), notes=self.notes_edit.text()
        )
