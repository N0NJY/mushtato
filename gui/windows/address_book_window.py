"""Address book: browse/add/edit/delete saved worlds, connect to open
a tab in the host MainWindow (Phase 7e -- previously this opened its own
independent MainWindow per world; now MainWindow is the persistent
root and this is a satellite picker spawned *from* it, per Rick's
explicit design call).

Settings/About/general chrome deliberately do NOT live here anymore --
those are host-level concerns now that the host always exists. This
window's only job is picking a saved world to connect to and managing
the saved list itself.

Post-8b addition: a Character picker (checkpoint discussion before
code) -- selecting a World shows its saved Characters in a second list;
picking one and clicking Log In connects using that specific Character,
bypassing (not changing) whatever default_character is stored. This is
a genuine MushTato addition, not a Potato port -- verified against the
real Potato source (~/git/potato/potato.vfs) that its own Manage Worlds
window has no equivalent picker; its "Char" column and Connect button
only ever read/use the stored default.

Post-Character-picker addition (another genuine MushTato addition,
Rick's own request, no Potato equivalent claimed): a per-world
"auto-login on startup" checkbox right on each row of the Worlds list,
and Sort A-Z/Z-A buttons plus drag-and-drop manual reordering. The
checkbox is only enabled once a world has a default_character set
(auto-login has nothing to log in as otherwise) -- shown greyed-out
rather than hidden so it's visible feedback, not a silent gap.
Reordering (drag-and-drop or a sort click) rewrites ``self.worlds`` and
persists immediately, the same "list order is stored order" model
Potato itself doesn't have any precedent for either. gui/app.py's
startup path reads this flag directly from the saved address book (no
GUI window needs to exist yet) -- see ``worlds_to_auto_login`` there.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from engine.storage import (
    WorldProfile,
    WorldScriptProfile,
    address_book_path,
    load_address_book,
    load_world_scripts,
    save_address_book,
    save_world_scripts,
    user_data_dir,
)
from engine.storage.paths import safe_filename

from ..dialogs.world_edit_dialog import WorldEditDialog
from ..dialogs.world_properties_dialog import WorldPropertiesDialog


class AddressBookWindow(QMainWindow):
    def __init__(
        self,
        host_window,
        *,
        storage_path: Optional[Path] = None,
        scripts_dir: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("MushTato — Address Book")

        self.host_window = host_window
        self._path = storage_path if storage_path is not None else address_book_path()
        # Phase 9: same override pattern as storage_path above -- see
        # MainWindow's own _scripts_dir for the reasoning (defaults to
        # the real per-user scripts directory, overridable for tests).
        self._scripts_dir = scripts_dir if scripts_dir is not None else user_data_dir() / "scripts"

        self.worlds: List[WorldProfile] = load_address_book(self._path)

        self.list_widget = QListWidget(self)
        self.list_widget.itemDoubleClicked.connect(self._connect_selected)
        self.list_widget.currentRowChanged.connect(self._refresh_selection_dependent_buttons)
        self.list_widget.currentRowChanged.connect(self._refresh_character_list)
        self.list_widget.itemChanged.connect(self._on_world_item_changed)
        # Manual drag-and-drop reordering ("choose the order in which
        # they are listed") -- InternalMove keeps this a pure reorder,
        # never a copy/drop-from-elsewhere.
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.model().rowsMoved.connect(self._on_worlds_reordered)

        self.character_list = QListWidget(self)
        self.character_list.currentRowChanged.connect(self._refresh_login_button)

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
        self.login_button = QPushButton("Log In")
        self.login_button.clicked.connect(self._log_in_as_selected_character)
        sort_az_button = QPushButton("Sort A-Z")
        sort_az_button.clicked.connect(self._sort_alpha)
        sort_za_button = QPushButton("Sort Z-A")
        sort_za_button.clicked.connect(self._sort_reverse_alpha)

        button_row = QHBoxLayout()
        button_row.addWidget(add_button)
        button_row.addWidget(self.edit_button)
        button_row.addWidget(self.delete_button)
        button_row.addWidget(self.connect_button)
        button_row.addWidget(self.properties_button)
        button_row.addWidget(self.login_button)
        button_row.addWidget(sort_az_button)
        button_row.addWidget(sort_za_button)

        lists_row = QHBoxLayout()
        worlds_column = QVBoxLayout()
        worlds_column.addWidget(QLabel("Worlds"))
        worlds_column.addWidget(self.list_widget)
        characters_column = QVBoxLayout()
        characters_column.addWidget(QLabel("Characters"))
        characters_column.addWidget(self.character_list)
        lists_row.addLayout(worlds_column, 2)
        lists_row.addLayout(characters_column, 1)

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
        layout.addLayout(lists_row)
        layout.addLayout(button_row)
        self.setCentralWidget(central)

        self._apply_hotkeys()

    def _apply_hotkeys(self) -> None:
        hotkeys = self.host_window._hotkeys
        QShortcut(QKeySequence(hotkeys["add_world"]), self, activated=self._add_world)
        QShortcut(QKeySequence(hotkeys["connect"]), self, activated=self._connect_selected)
        QShortcut(QKeySequence(hotkeys["close_window"]), self, activated=self.close)

    def _refresh_list(self) -> None:
        # Blocked so that setCheckState() below (a data change on a
        # freshly-added item) doesn't fire itemChanged and re-save
        # during a routine repopulation -- only a real user click on
        # the checkbox should trigger _on_world_item_changed.
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for world in self.worlds:
            item = QListWidgetItem(f"{world.name} ({world.host}:{world.port})")
            # The row itself always stays selectable/enabled (Edit,
            # Delete, Connect, Properties, double-click all still need
            # to work on a world with no default character set yet) --
            # only the checkbox's presence is conditional. A world
            # without a default character simply shows no checkbox at
            # all rather than a disabled one, since Qt ties a disabled
            # checkbox to a disabled (unselectable) *row*, which would
            # break every other button for that world.
            flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
            can_auto_login = bool(world.default_character)
            if can_auto_login:
                flags |= Qt.ItemFlag.ItemIsUserCheckable
            item.setFlags(flags)
            if can_auto_login:
                item.setCheckState(
                    Qt.CheckState.Checked if world.auto_login else Qt.CheckState.Unchecked
                )
                item.setToolTip("Auto-login on startup")
            else:
                item.setToolTip("Set a default character (Properties...) to enable auto-login")
            item.setData(Qt.ItemDataRole.UserRole, world)
            self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)
        self._refresh_selection_dependent_buttons()
        self._refresh_character_list()

    def _on_world_item_changed(self, item: QListWidgetItem) -> None:
        world = item.data(Qt.ItemDataRole.UserRole)
        if world is None:
            return
        checked = item.checkState() == Qt.CheckState.Checked
        if world.auto_login != checked:
            world.auto_login = checked
            self._save()

    def _on_worlds_reordered(self, *_args) -> None:
        self.worlds = [
            self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.list_widget.count())
        ]
        self._save()

    def _sort_alpha(self) -> None:
        self.worlds.sort(key=lambda w: w.name.lower())
        self._save()
        self._refresh_list()

    def _sort_reverse_alpha(self) -> None:
        self.worlds.sort(key=lambda w: w.name.lower(), reverse=True)
        self._save()
        self._refresh_list()

    def _refresh_selection_dependent_buttons(self, *_args) -> None:
        has_selection = self._selected_index() is not None
        for button in (
            self.edit_button,
            self.delete_button,
            self.connect_button,
            self.properties_button,
        ):
            button.setEnabled(has_selection)

    def _refresh_character_list(self, *_args) -> None:
        self.character_list.clear()
        index = self._selected_index()
        if index is not None:
            for character in self.worlds[index].characters:
                self.character_list.addItem(character.name)
        self._refresh_login_button()

    def _refresh_login_button(self, *_args) -> None:
        self.login_button.setEnabled(self.character_list.currentRow() >= 0)

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
        world = self.worlds[index]
        scripts_path = self._scripts_dir / f"{safe_filename(world.name)}.json"
        existing_scripts_profile = load_world_scripts(scripts_path)

        # A currently-open tab for this world (if any) has the live,
        # authoritative ScriptWorld -- its auto-disabled triggers (if
        # any) are what the Scripts page's visible marker reflects,
        # not something this dialog could otherwise know about (it
        # only ever works with static, on-disk ScriptRecords).
        disabled_trigger_scripts: set = set()
        for tab in self.host_window.tabs_for_world(world.name):
            disabled_trigger_scripts |= tab.script_world.triggers.disabled_source_scripts()

        dialog = WorldPropertiesDialog(
            self,
            world=world,
            scripts=existing_scripts_profile.scripts,
            disabled_trigger_scripts=disabled_trigger_scripts,
        )
        if dialog.exec():
            profile = dialog.result_profile()
            if profile is not None:
                self.worlds[index] = profile
                self._save()
                self._refresh_list()
            # Variables are preserved as-is -- this dialog only ever
            # edits script *source*, never the accumulated in-play
            # state a currently-open tab (or a past session) built up.
            save_world_scripts(
                scripts_path,
                WorldScriptProfile(
                    scripts=dialog.result_scripts(), variables=existing_scripts_profile.variables
                ),
            )
            self.host_window.reload_scripts_for_world(world.name)

    def _log_in_as_selected_character(self) -> None:
        world_index = self._selected_index()
        char_row = self.character_list.currentRow()
        if world_index is None or char_row < 0:
            return
        world = self.worlds[world_index]
        character = world.characters[char_row]
        self.log_in_as(world, character)

    def log_in_as(self, world: WorldProfile, character):
        """Open a *new* tab logged in as ``character`` specifically --
        one-time only, never changes world.default_character. Unlike
        connect_to(), this always opens a new tab even if this world's
        host:port is already connected elsewhere (see
        MainWindow.open_tab's docstring for why -- a different
        Character is a genuinely different session server-side).
        """
        return self.host_window.open_tab(
            world.host, world.port, name=world.name, world=world, character=character
        )
