"""Address book: browse/add/edit/delete saved worlds, connect to open
an independent session window per world (Phase 6).

Each "Connect" spawns its own MainWindow + TelnetBridge pair with its
own background thread -- the multi-window model Phase 5's checkpoint
discussion already committed to. This window just needs to keep
references to the ones it opens so Qt doesn't garbage-collect them,
and remove that reference again once a session window closes.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

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
from .main_window import MainWindow


class AddressBookWindow(QMainWindow):
    def __init__(
        self,
        *,
        storage_path: Optional[Path] = None,
        window_factory=MainWindow,
    ) -> None:
        super().__init__()
        self.setWindowTitle("MushTato — Address Book")

        self._path = storage_path if storage_path is not None else address_book_path()
        # Injectable so tests can supply a fake in place of the real
        # MainWindow (which would otherwise open a real TelnetBridge) --
        # same pattern MainWindow itself uses for `bridge`.
        self._window_factory = window_factory

        self.worlds: List[WorldProfile] = load_address_book(self._path)
        self.open_windows: List[MainWindow] = []

        self.list_widget = QListWidget(self)
        self.list_widget.itemDoubleClicked.connect(self._connect_selected)
        self._refresh_list()

        add_button = QPushButton("Add")
        add_button.clicked.connect(self._add_world)
        edit_button = QPushButton("Edit")
        edit_button.clicked.connect(self._edit_selected)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self._delete_selected)
        connect_button = QPushButton("Connect")
        connect_button.clicked.connect(self._connect_selected)

        button_row = QHBoxLayout()
        button_row.addWidget(add_button)
        button_row.addWidget(edit_button)
        button_row.addWidget(delete_button)
        button_row.addWidget(connect_button)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addWidget(self.list_widget)
        layout.addLayout(button_row)
        self.setCentralWidget(central)

    def _refresh_list(self) -> None:
        self.list_widget.clear()
        for world in self.worlds:
            self.list_widget.addItem(f"{world.name} ({world.host}:{world.port})")

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

    def connect_to(self, world: WorldProfile) -> MainWindow:
        window = self._window_factory(world.host, world.port, name=world.name)
        window.closed.connect(lambda: self._remove_open_window(window))
        self.open_windows.append(window)
        window.resize(800, 600)
        window.show()
        return window

    def _remove_open_window(self, window: MainWindow) -> None:
        if window in self.open_windows:
            self.open_windows.remove(window)
