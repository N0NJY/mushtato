"""Address book: browse/add/edit/delete saved worlds, connect to open
a tab in the host MainWindow (Phase 9 -- previously this opened its own
independent MainWindow per world; now MainWindow is the persistent
root and this is a satellite picker spawned *from* it, per Rick's
explicit design call).

Settings/About/general chrome deliberately do NOT live here anymore --
those are host-level concerns now that the host always exists. This
window's only job is picking a saved world to connect to and managing
the saved list itself.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from engine.storage import WorldProfile, address_book_path, load_address_book, save_address_book

from ..dialogs.world_edit_dialog import WorldEditDialog
from ..dialogs.world_properties_dialog import WorldPropertiesDialog


class AddressBookWindow(QMainWindow):
    def __init__(
        self,
        host_window,
        *,
        storage_path: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("MushTato — Address Book")

        self.host_window = host_window
        self._path = storage_path if storage_path is not None else address_book_path()

        self.worlds: List[WorldProfile] = load_address_book(self._path)

        self.list_widget = QListWidget(self)
        self.list_widget.itemDoubleClicked.connect(self._connect_selected)
        self.list_widget.currentRowChanged.connect(self._refresh_selection_dependent_buttons)

        add_button = QPushButton("Add")
        add_button.clicked.connect(self._add_world)
        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self._edit_selected)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete_selected)
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self._connect_selected)
        self.properties_button = QPushButton("Properties...")
        self.properties_button.clicked.connect(self._open_properties)

        button_row = QHBoxLayout()
        button_row.addWidget(add_button)
        button_row.addWidget(self.edit_button)
        button_row.addWidget(self.delete_button)
        button_row.addWidget(self.connect_button)
        button_row.addWidget(self.properties_button)

        # A fresh QListWidget starts with nothing selected even if
        # worlds exist -- clicking Edit/Delete/Connect/Properties at
        # that point used to silently no-op (currentRow() == -1), with
        # zero feedback that a selection was even needed. Disabling
        # these buttons until something is actually selected makes that
        # visible instead of silent. Buttons must exist before this
        # call, since it's what enables/disables them.
        self._refresh_list()

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addWidget(self.list_widget)
        layout.addLayout(button_row)
        self.setCentralWidget(central)

        self._apply_hotkeys()

    def _apply_hotkeys(self) -> None:
        hotkeys = self.host_window._hotkeys
        QShortcut(QKeySequence(hotkeys["add_world"]), self, activated=self._add_world)
        QShortcut(QKeySequence(hotkeys["connect"]), self, activated=self._connect_selected)
        QShortcut(QKeySequence(hotkeys["close_window"]), self, activated=self.close)

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        for world in self.worlds:
            self.list_widget.addItem(f"{world.name} ({world.host}:{world.port})")
        self._refresh_selection_dependent_buttons()

    def _refresh_selection_dependent_buttons(self, *_args) -> None:
        has_selection = self._selected_index() is not None
        for button in (
            self.edit_button,
            self.delete_button,
            self.connect_button,
            self.properties_button,
        ):
            button.setEnabled(has_selection)

    def _save(self) -> None:
        save_address_book(self._path, self.worlds)

    def _selected_index(self) -> Optional[int]:
        row = self.list_widget.currentRow()
        return row if row >= 0 else None

    def _add_world(self) -> None:
        dialog = WorldEditDialog(self)
        if dialog.exec():
            profile = dialog.result_profile()
            if profile is not None:
                self.worlds.append(profile)
                self._save()
                self._refresh_list()

    def _edit_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        dialog = WorldEditDialog(self, world=self.worlds[index])
        if dialog.exec():
            profile = dialog.result_profile()
            if profile is not None:
                self.worlds[index] = profile
                self._save()
                self._refresh_list()

    def _delete_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        del self.worlds[index]
        self._save()
        self._refresh_list()

    def _connect_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        self.connect_to(self.worlds[index])

    def connect_to(self, world: WorldProfile):
        """Ask the host shell to open (or switch to) a tab for this
        world -- the host owns tab creation, not this window. Passes
        the full profile through (Phase 8b) so the tab can fire
        auto-sends/character login, not just host/port/name.
        """
        return self.host_window.open_tab(world.host, world.port, name=world.name, world=world)

    def _open_properties(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        dialog = WorldPropertiesDialog(self, world=self.worlds[index])
        if dialog.exec():
            profile = dialog.result_profile()
            if profile is not None:
                self.worlds[index] = profile
                self._save()
                self._refresh_list()
