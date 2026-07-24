"""The app's root window (Phase 7e): one persistent shell holding a
QTabWidget of SessionTab connections, a shared menu bar/toolbar/status
bar, and the app's settings. Always present from launch to exit --
Rick's explicit design call: "the main connection window should be the
root of all things," with the address book and spawn windows as
satellites opened *from* it, not the other way around (Phases 5-7d had
it backwards: MainWindow was one connection, and AddressBookWindow was
the thing you started from).

Deliberately not wired to engine/scripting yet -- see CLAUDE.md's
Phase 5/6 notes for why that's an explicit deferral, not an oversight.
"""

from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import QDateTime, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QToolBar,
)

from engine.storage import (
    DEFAULT_HOTKEYS,
    DEFAULT_THEME,
    CharacterProfile,
    Settings,
    WorldProfile,
    address_book_path,
    load_address_book,
    save_address_book,
    save_settings,
    settings_path,
    user_data_dir,
)
from engine.storage.paths import safe_filename

from ..dialogs.settings_dialog import SettingsDialog
from ..help.help_window import HelpWindow
from ..theme import apply_theme
from ..version import mushtato_version
from .session_tab import SessionTab
from .telnet_bridge import TelnetBridge

__all__ = ["MainWindow", "mushtato_version"]


class MainWindow(QMainWindow):
    # Tab-activity flashing (post-8b addition): a single fixed color
    # used for every world, on either theme -- not a Potato/TinyFugue
    # port, no per-theme variant attempted (this is tab-bar chrome, not
    # scrollback content, so the dark/light legibility concerns that
    # drove engine/ansi/gui/theme's own color choices don't apply the
    # same way here).
    ACTIVITY_COLOR = QColor(255, 140, 0)  # orange
    ACTIVITY_BLINK_INTERVAL_MS = 500
    # Phase 9: how often the shared script-variable autosave timer
    # checks for dirty tabs. Rick's exact spec -- 5 minutes, dirty-flag
    # gated, not "save on every set_var()" (which risks a synchronous
    # atomic JSON write on every incoming line if a trigger fires
    # often).
    SCRIPT_AUTOSAVE_INTERVAL_MS = 5 * 60 * 1000

    def __init__(
        self,
        *,
        hotkeys: Optional[Dict[str, str]] = None,
        theme: Optional[str] = None,
        address_book_storage_path=None,
        scripts_dir=None,
        scrollback_font_family: str = "",
        scrollback_font_size: int = 0,
        input_font_family: str = "",
        input_font_size: int = 0,
        splitter_sizes: Optional[list] = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("MushTato")

        # Same pattern as every other phase: defaults to the plain
        # constant, never touching disk on its own -- callers that want
        # the user's actually-saved values (gui/app.py) load Settings
        # themselves and pass them through explicitly. Keeps
        # construction side-effect-free for tests.
        self._hotkeys = hotkeys if hotkeys is not None else dict(DEFAULT_HOTKEYS)
        self._theme = theme if theme is not None else DEFAULT_THEME
        self._scrollback_font_family = scrollback_font_family
        self._scrollback_font_size = scrollback_font_size
        self._input_font_family = input_font_family
        self._input_font_size = input_font_size
        # The dual-input splitter's last-dragged size, one global
        # preference applied as every *newly-opened* tab's starting
        # split -- see record_splitter_sizes's docstring for why this
        # doesn't live-resize already-open tabs the way font/theme do.
        self._splitter_sizes = list(splitter_sizes) if splitter_sizes else []
        self._address_book_path = (
            address_book_storage_path if address_book_storage_path is not None else address_book_path()
        )
        # Phase 9: same override pattern as address_book_storage_path
        # above -- defaults to the real per-user scripts directory,
        # overridable so tests never touch it. Each tab's actual script
        # file is this directory joined with its world's safe filename
        # (see open_tab()), computed here rather than per-call so every
        # tab for the same world agrees on the same path.
        self._scripts_dir = scripts_dir if scripts_dir is not None else user_data_dir() / "scripts"
        self._address_book_window = None  # lazily constructed on first use
        self._help_window = None  # lazily constructed on first use

        self.tab_widget = QTabWidget(self)
        self.tab_widget.setTabsClosable(False)
        self.tab_widget.currentChanged.connect(self._on_current_tab_changed)
        self.setCentralWidget(self.tab_widget)

        # Tab-activity flashing: which SessionTabs currently have unseen
        # activity (tracked by object, not index -- indices shift as
        # tabs open/close, so looking up a tab's *current* index each
        # tick via indexOf() is the only reliable option). One shared
        # timer flashes every marked tab in sync, rather than a timer
        # per tab -- simpler and keeps multiple flashing tabs blinking
        # together instead of independently. Runs only while at least
        # one tab actually has unseen activity.
        self._tabs_with_activity: set = set()
        self._activity_flash_on = False
        self._activity_timer = QTimer(self)
        self._activity_timer.setInterval(self.ACTIVITY_BLINK_INTERVAL_MS)
        self._activity_timer.timeout.connect(self._tick_activity_flash)

        # Debounced splitter-size persistence: splitterMoved fires on
        # every pixel of a drag, so writing settings.json synchronously
        # on each one would hit the disk dozens of times per drag.
        # Restarting a single-shot timer on every call coalesces that
        # into one write shortly after the drag actually stops.
        self._splitter_save_timer = QTimer(self)
        self._splitter_save_timer.setSingleShot(True)
        self._splitter_save_timer.setInterval(400)
        self._splitter_save_timer.timeout.connect(self._save_settings_to_disk)

        # Phase 9: periodic autosave of script variables. One shared
        # timer iterating every open tab (same reasoning as
        # _activity_timer above) rather than one timer per tab. Only
        # writes for a tab whose ScriptWorld.dirty is actually set
        # (i.e. set_var() has fired since the last save) -- an idle
        # tab with no variable mutations never touches disk. This is
        # *in addition to* SessionTab's own save-on-shutdown/disconnect
        # (session_tab.py's save_script_state()), not a replacement --
        # it exists to survive a crash/force-quit that skips that path.
        self._script_autosave_timer = QTimer(self)
        self._script_autosave_timer.setInterval(self.SCRIPT_AUTOSAVE_INTERVAL_MS)
        self._script_autosave_timer.timeout.connect(self._autosave_dirty_scripts)
        self._script_autosave_timer.start()

        self._build_chrome()
        self._apply_hotkeys()
        self._refresh_action_enabled_state()

    # -- tab management -----------------------------------------------

    def open_tab(
        self,
        host: str,
        port: int,
        *,
        name: Optional[str] = None,
        bridge: Optional[TelnetBridge] = None,
        world: Optional[WorldProfile] = None,
        character: Optional[CharacterProfile] = None,
    ) -> SessionTab:
        """Open a new connection tab, or switch to an existing one for
        the same host:port rather than opening a duplicate.

        ``world`` (Phase 8b), when given, is the full saved profile --
        SessionTab needs it for auto-sends/character login, not just
        the host/port/name a direct-connect (no address book) tab has.

        ``character``, when given, is an explicit "Log In as" choice
        from the address book's character picker -- unlike a plain
        Connect, this deliberately skips the existing-tab dedup check
        below and always opens a new tab, since logging in as a
        different character than one already connected is a genuinely
        different session server-side (e.g. running a main + an alt at
        once), not a duplicate of the same connection.
        """
        if character is None:
            for index in range(self.tab_widget.count()):
                existing = self.tab_widget.widget(index)
                if existing.host == host and existing.port == port:
                    self.tab_widget.setCurrentIndex(index)
                    return existing

        tab = SessionTab(
            host,
            port,
            name=name,
            bridge=bridge,
            theme=self._theme,
            host_window=self,
            world=world,
            character=character,
            scrollback_font_family=self._scrollback_font_family,
            scrollback_font_size=self._scrollback_font_size,
            input_font_family=self._input_font_family,
            input_font_size=self._input_font_size,
            splitter_sizes=self._splitter_sizes or None,
            script_store_path=(
                self._scripts_dir / f"{safe_filename(world.name)}.json" if world is not None else None
            ),
        )
        tab.connectionStateChanged.connect(lambda state, t=tab: self._on_tab_state_changed(t, state))
        tab.activity.connect(lambda t=tab: self._on_tab_activity(t))
        index = self.tab_widget.addTab(tab, tab.name)
        self.tab_widget.setCurrentIndex(index)
        self._refresh_action_enabled_state()
        return tab

    def close_tab(self, tab: SessionTab) -> None:
        index = self.tab_widget.indexOf(tab)
        if index == -1:
            return
        tab.shutdown()
        self._tabs_with_activity.discard(tab)
        if not self._tabs_with_activity:
            self._activity_timer.stop()
        self.tab_widget.removeTab(index)
        tab.deleteLater()
        self._refresh_action_enabled_state()
        self._refresh_status_bar()

    def close_current_tab(self) -> None:
        tab = self.tab_widget.currentWidget()
        if tab is not None:
            self.close_tab(tab)

    def connect_by_name(self, name: str) -> str:
        worlds = load_address_book(self._address_book_path)
        world = next((w for w in worlds if w.name.lower() == name.lower()), None)
        if world is None:
            return f"No saved world named {name!r}."
        self.open_tab(world.host, world.port, name=world.name, world=world)
        return f"Connecting to {name}..."

    def record_world_connected(self, world: WorldProfile) -> None:
        """Persist an incremented connect_count for ``world`` (Phase
        8b) -- called by SessionTab right as a connection succeeds, so
        "first connect ever" auto-sends correctly never fire again
        after the real first connection, even across app restarts.

        Reloads the address book fresh and matches by name+host+port
        rather than relying on ``world`` being the same object already
        held by AddressBookWindow's in-memory list -- a tab opened via
        ``/connect <name>`` gets a freshly-loaded WorldProfile that
        isn't that same object, so this has to work for both paths.
        """
        world.connect_count += 1
        worlds = load_address_book(self._address_book_path)
        for candidate in worlds:
            if (
                candidate.name.lower() == world.name.lower()
                and candidate.host == world.host
                and candidate.port == world.port
            ):
                candidate.connect_count = world.connect_count
                break
        save_address_book(self._address_book_path, worlds)
        if self._address_book_window is not None:
            self._address_book_window.worlds = worlds
            self._address_book_window._refresh_list()

    # -- Phase 9: live script reload for an open tab -------------------

    def tabs_for_world(self, world_name: str) -> list:
        """Every currently-open tab whose world matches ``world_name``
        (case-insensitive) -- a world-less (direct-connect) tab never
        matches. Used both to compute the Scripts UI's "this script has
        a disabled trigger" indicator and to live-reload scripts after
        World Properties saves changes for a world that's currently
        connected.
        """
        matches = []
        for index in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(index)
            if tab.world is not None and tab.world.name.lower() == world_name.lower():
                matches.append(tab)
        return matches

    def reload_scripts_for_world(self, world_name: str) -> None:
        for tab in self.tabs_for_world(world_name):
            tab.reload_scripts()

    # -- settings persistence (hotkeys/theme/fonts/splitter size) -----

    def _current_settings(self) -> Settings:
        return Settings(
            hotkeys=self._hotkeys,
            theme=self._theme,
            scrollback_font_family=self._scrollback_font_family,
            scrollback_font_size=self._scrollback_font_size,
            input_font_family=self._input_font_family,
            input_font_size=self._input_font_size,
            splitter_sizes=self._splitter_sizes,
        )

    def _save_settings_to_disk(self) -> None:
        save_settings(settings_path(), self._current_settings())

    def record_splitter_sizes(self, sizes) -> None:
        """Remember the dual-input splitter's last-dragged sizes as one
        global preference -- applied as the *starting* split for every
        newly-opened tab, this session or a future launch (Rick's
        explicit choice over per-world persistence).

        Deliberately does NOT resize any already-open tab's splitter --
        unlike theme/fonts, dragging one tab's split isn't a "setting
        change" the user made through Settings, it's an in-the-moment
        layout tweak on that one tab; silently resizing every other
        open tab to match would be surprising mid-session. Debounced
        (400ms, restarts on every call) so a fast drag -- which fires
        this on every pixel of movement -- doesn't hit the disk dozens
        of times per second.
        """
        self._splitter_sizes = list(sizes)
        self._splitter_save_timer.start()

    def _on_current_tab_changed(self, index: int) -> None:
        if index != -1:
            self._clear_tab_activity(self.tab_widget.widget(index))
        self._refresh_status_bar()
        self._refresh_action_enabled_state()

    def _on_tab_state_changed(self, tab: SessionTab, state: str) -> None:
        if self.tab_widget.currentWidget() is tab:
            self.status_state_label.setText(state)

    # -- tab-activity flashing ------------------------------------------

    def _on_tab_activity(self, tab: SessionTab) -> None:
        # Only *other* tabs get flashed -- text arriving in the tab
        # you're already looking at isn't "activity you missed".
        if self.tab_widget.currentWidget() is tab:
            return
        if tab not in self._tabs_with_activity:
            self._tabs_with_activity.add(tab)
        if not self._activity_timer.isActive():
            self._activity_flash_on = True
            self._apply_activity_colors()
            self._activity_timer.start()

    def _tick_activity_flash(self) -> None:
        self._activity_flash_on = not self._activity_flash_on
        self._apply_activity_colors()

    def _apply_activity_colors(self) -> None:
        bar = self.tab_widget.tabBar()
        color = self.ACTIVITY_COLOR if self._activity_flash_on else QColor()
        for tab in self._tabs_with_activity:
            index = self.tab_widget.indexOf(tab)
            if index != -1:
                bar.setTabTextColor(index, color)

    def _clear_tab_activity(self, tab: SessionTab) -> None:
        if tab in self._tabs_with_activity:
            self._tabs_with_activity.discard(tab)
            index = self.tab_widget.indexOf(tab)
            if index != -1:
                # An invalid QColor tells Qt to fall back to the tab
                # bar's own default text color, rather than us having
                # to compute/track what that default is per-theme.
                self.tab_widget.tabBar().setTabTextColor(index, QColor())
        if not self._tabs_with_activity:
            self._activity_timer.stop()

    # -- Phase 9: periodic script-variable autosave ---------------------

    def _autosave_dirty_scripts(self) -> None:
        for index in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(index)
            if tab.script_world.dirty:
                tab.save_script_state()

    # -- address book / settings (host-level, shared by every tab) ---

    def _show_address_book(self) -> None:
        if self._address_book_window is None:
            from .address_book_window import AddressBookWindow

            self._address_book_window = AddressBookWindow(
                self, storage_path=self._address_book_path, scripts_dir=self._scripts_dir
            )
        self._address_book_window.show()
        self._address_book_window.raise_()
        self._address_book_window.activateWindow()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self, settings=self._current_settings())
        if dialog.exec():
            result = dialog.result_settings()
            self._hotkeys = result.hotkeys
            self._theme = result.theme
            self._scrollback_font_family = result.scrollback_font_family
            self._scrollback_font_size = result.scrollback_font_size
            self._input_font_family = result.input_font_family
            self._input_font_size = result.input_font_size
            # splitter_sizes isn't editable in the dialog -- result.splitter_sizes
            # is just the same value the dialog was constructed with, passed
            # through unchanged, so this line is a no-op in practice; kept
            # for the same reason as every other field here: one save writes
            # the *complete* current settings, never a partial one.
            self._splitter_sizes = result.splitter_sizes
            self._save_settings_to_disk()
            self._apply_hotkeys()  # only one owner of hotkeys now -- live-reload is cheap
            app = QApplication.instance()
            if app is not None:
                apply_theme(app, self._theme)
            self._retheme_open_tabs()
            self._refont_open_tabs()

    def set_theme(self, theme: str) -> str:
        self._theme = theme
        self._save_settings_to_disk()
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, theme)
        self._retheme_open_tabs()
        return f"Theme set to {theme}."

    def _retheme_open_tabs(self) -> None:
        # Every open tab's own scrollback override, not just the
        # app-wide palette -- see SessionTab.apply_theme's docstring
        # for why this used to be an accepted gap and isn't anymore.
        for index in range(self.tab_widget.count()):
            self.tab_widget.widget(index).apply_theme(self._theme)

    def _refont_open_tabs(self) -> None:
        # Font changes live-reload to every already-open tab, the same
        # treatment theme already gets -- unlike splitter size (see
        # record_splitter_sizes's docstring), a font change made
        # through Settings is a deliberate preference change, not an
        # in-the-moment layout tweak, so propagating it everywhere is
        # the expected behavior here, not a surprise.
        for index in range(self.tab_widget.count()):
            self.tab_widget.widget(index).apply_fonts(
                self._scrollback_font_family,
                self._scrollback_font_size,
                self._input_font_family,
                self._input_font_size,
            )

    def _show_about(self) -> None:
        QMessageBox.information(
            self,
            "About MushTato",
            f"MushTato {mushtato_version()}\n\n"
            "Written by Rick Donaldson, 2026\n"
            "(aka Thoran Yo, aka Fletcher, aka N0NJY)\n\n"
            "MIT License\n"
            "Latest copy: github.com/N0NJY/mushtato",
        )

    def show_help(self) -> None:
        """Open the real Help window (Phase 8), replacing the Phase 7c
        /help placeholder. Available with zero tabs open -- this is
        static app documentation, not tied to any one connection.
        """
        if self._help_window is None:
            self._help_window = HelpWindow(hotkeys=self._hotkeys, theme=self._theme)
        else:
            # Rebuilt every open, not just shown as-is -- hotkeys/theme
            # can have changed since this singleton window was last
            # shown, and stale content would be worse than the small
            # cost of rebuilding it.
            self._help_window.refresh(self._hotkeys, self._theme)
        self._help_window.show()
        self._help_window.raise_()
        self._help_window.activateWindow()

    # -- chrome: menu bar, toolbar, status bar -------------------------

    def _build_chrome(self) -> None:
        """Menu bar, toolbar, and status bar modeled on Potato's real
        GUI chrome (Phase 7d). Reworked for Phase 7e: everything here is
        host-level chrome that acts on the *active* tab (Reconnect,
        Disconnect, Copy, Spawn Log, Close) or the app as a whole
        (Address Book, Settings, Theme, About, Help, Exit) -- there is
        no more per-connection chrome, since MainWindow itself is no
        longer one connection.
        """
        menu_bar = self.menuBar()
        toolbar = QToolBar("Main", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.toolbar = toolbar

        def add_action(menu, text, slot=None, *, enabled=True):
            action = QAction(text, self)
            if slot is not None:
                action.triggered.connect(slot)
            action.setEnabled(enabled)
            menu.addAction(action)
            return action

        # -- File ------------------------------------------------------
        self.file_menu = file_menu = menu_bar.addMenu("&File")
        self.address_book_action = add_action(file_menu, "Address Book...", self._show_address_book)
        self.reconnect_action = add_action(file_menu, "Reconnect", self._reconnect_current_tab)
        self.disconnect_action = add_action(file_menu, "Disconnect", self._disconnect_current_tab)
        file_menu.addSeparator()
        self.close_action = add_action(file_menu, "Close", self.close_current_tab)
        file_menu.addSeparator()
        self.exit_action = add_action(file_menu, "Exit", self._exit_application)

        toolbar.addAction(self.reconnect_action)
        toolbar.addAction(self.disconnect_action)
        toolbar.addAction(self.close_action)
        toolbar.addSeparator()
        toolbar.addAction(self.address_book_action)

        # -- Edit --------------------------------------------------------
        # Cut/Copy/Paste/Undo/Redo/Select All all dispatch to whichever
        # widget currently has keyboard focus (see
        # _dispatch_focused_edit_action's docstring) rather than being
        # hardcoded to one widget -- Copy used to be hardcoded to the
        # active tab's scrollback specifically; unified onto the same
        # focus-dispatch mechanism as the other five for consistency,
        # since a selection sitting in an input box is what a user
        # clicking Copy right after typing would actually expect copied.
        # No "Clear" item (Phase 10 checkpoint, Rick's choice) -- what it
        # would even clear was never well-defined (the focused input box?
        # the whole scrollback, a much more destructive and arguably
        # separate action?) and wasn't worth the ambiguity.
        self.edit_menu = edit_menu = menu_bar.addMenu("&Edit")
        self.cut_action = add_action(
            edit_menu, "Cut", lambda: self._dispatch_focused_edit_action("cut")
        )
        self.cut_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Cut))
        self.copy_action = add_action(
            edit_menu, "Copy", lambda: self._dispatch_focused_edit_action("copy")
        )
        self.copy_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Copy))
        self.paste_action = add_action(
            edit_menu, "Paste", lambda: self._dispatch_focused_edit_action("paste")
        )
        self.paste_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Paste))
        edit_menu.addSeparator()
        self.undo_action = add_action(
            edit_menu, "Undo", lambda: self._dispatch_focused_edit_action("undo")
        )
        self.undo_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Undo))
        self.redo_action = add_action(
            edit_menu, "Redo", lambda: self._dispatch_focused_edit_action("redo")
        )
        self.redo_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Redo))
        edit_menu.addSeparator()
        self.select_all_action = add_action(
            edit_menu, "Select All", lambda: self._dispatch_focused_edit_action("selectAll")
        )
        self.select_all_action.setShortcut(QKeySequence(QKeySequence.StandardKey.SelectAll))
        edit_menu.addSeparator()
        self.find_action = add_action(edit_menu, "Find...", None, enabled=False)

        # -- View --------------------------------------------------------
        self.view_menu = view_menu = menu_bar.addMenu("&View")
        self.theme_menu = theme_menu = view_menu.addMenu("Theme")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        self.dark_theme_action = QAction("Dark", self)
        self.dark_theme_action.setCheckable(True)
        self.light_theme_action = QAction("Light", self)
        self.light_theme_action.setCheckable(True)
        for action, theme_name in (
            (self.dark_theme_action, "dark"),
            (self.light_theme_action, "light"),
        ):
            theme_group.addAction(action)
            theme_menu.addAction(action)
            action.triggered.connect(lambda checked=False, t=theme_name: self.set_theme(t))
        (self.dark_theme_action if self._theme == "dark" else self.light_theme_action).setChecked(True)

        # -- Logging -------------------------------------------------------
        self.logging_menu = logging_menu = menu_bar.addMenu("&Logging")
        self.spawn_log_action = add_action(
            logging_menu, "Spawn Log Window", self._spawn_log_for_current_tab
        )
        toolbar.addSeparator()
        toolbar.addAction(self.spawn_log_action)

        # -- Options ---------------------------------------------------
        self.options_menu = options_menu = menu_bar.addMenu("&Options")
        self.settings_action = add_action(options_menu, "Settings...", self.open_settings)
        toolbar.addAction(self.settings_action)

        # -- Tools (placeholders; Potato has these, MushTato doesn't yet) --
        self.tools_menu = tools_menu = menu_bar.addMenu("&Tools")
        self.editor_action = add_action(tools_menu, "Editor", None, enabled=False)
        self.upload_action = add_action(tools_menu, "Upload", None, enabled=False)
        self.mail_window_action = add_action(tools_menu, "Mail Window", None, enabled=False)
        self.events_action = add_action(tools_menu, "Events", None, enabled=False)
        toolbar.addSeparator()
        toolbar.addAction(self.editor_action)
        toolbar.addAction(self.upload_action)
        toolbar.addAction(self.mail_window_action)
        toolbar.addAction(self.find_action)

        # -- Help ------------------------------------------------------
        self.help_menu = help_menu = menu_bar.addMenu("&Help")
        self.help_action = add_action(help_menu, "Help", self.show_help)
        self.about_action = add_action(help_menu, "About", self._show_about)
        toolbar.addSeparator()
        toolbar.addAction(self.help_action)
        toolbar.addAction(self.about_action)

        # -- status bar ----------------------------------------------------
        self.status_name_label = QLabel("No connection")
        self.status_addr_label = QLabel("")
        self.status_duration_label = QLabel("")
        self.status_time_label = QLabel()
        self.status_state_label = QLabel("")
        status_bar = self.statusBar()
        status_bar.addWidget(self.status_name_label)
        status_bar.addWidget(self.status_addr_label)
        status_bar.addPermanentWidget(self.status_state_label)
        status_bar.addPermanentWidget(self.status_duration_label)
        status_bar.addPermanentWidget(self.status_time_label)

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def _refresh_status_bar(self) -> None:
        tab = self.tab_widget.currentWidget()
        if tab is None:
            self.status_name_label.setText("No connection")
            self.status_addr_label.setText("")
            self.status_state_label.setText("")
            self.status_duration_label.setText("")
        else:
            self.status_name_label.setText(tab.name)
            self.status_addr_label.setText(f"{tab.host}:{tab.port}")
            self.status_state_label.setText(tab.connection_state)

    def _refresh_action_enabled_state(self) -> None:
        has_tab = self.tab_widget.count() > 0
        for action in (
            self.reconnect_action,
            self.disconnect_action,
            self.close_action,
            self.spawn_log_action,
            self.cut_action,
            self.copy_action,
            self.paste_action,
            self.undo_action,
            self.redo_action,
            self.select_all_action,
        ):
            action.setEnabled(has_tab)

    def _update_clock(self) -> None:
        now = QDateTime.currentDateTime()
        self.status_time_label.setText(now.toString("dd/MM/yyyy - HH:mm:ss"))
        tab = self.tab_widget.currentWidget()
        if tab is not None and tab.connected_at is not None:
            elapsed = tab.connected_at.secsTo(now)
            hours, remainder = divmod(elapsed, 3600)
            minutes = remainder // 60
            self.status_duration_label.setText(f"Connected For: {hours}h {minutes}m")
        elif tab is not None:
            self.status_duration_label.setText("Not connected")
        else:
            self.status_duration_label.setText("")

    # -- actions that operate on the active tab ------------------------

    def _reconnect_current_tab(self) -> None:
        tab = self.tab_widget.currentWidget()
        if tab is not None:
            tab.reconnect_bridge()

    def _disconnect_current_tab(self) -> None:
        tab = self.tab_widget.currentWidget()
        if tab is not None:
            tab.disconnect_bridge()

    def _spawn_log_for_current_tab(self) -> None:
        tab = self.tab_widget.currentWidget()
        if tab is not None:
            tab.spawn_log_window()

    def _dispatch_focused_edit_action(self, method_name: str) -> None:
        """Cut/Copy/Paste/Undo/Redo/Select All all act on whichever
        widget currently has keyboard focus -- an input box or the
        active tab's scrollback -- rather than being hardcoded to one
        widget. Cut/Paste/Undo/Redo only make sense against an input
        box (the scrollback is read-only, no undo stack); a widget
        without the given method, or with nothing to act on (e.g. Paste
        against an empty clipboard), is simply a no-op -- Qt's own
        QLineEdit/QTextEdit methods already handle that gracefully.
        """
        widget = QApplication.focusWidget()
        method = getattr(widget, method_name, None)
        if callable(method):
            method()

    def _switch_input_focus_on_current_tab(self) -> None:
        tab = self.tab_widget.currentWidget()
        if tab is None:
            return
        if tab.input_line.hasFocus():
            tab.secondary_input.setFocus()
        else:
            tab.input_line.setFocus()

    def _exit_application(self) -> None:
        self.close()

    # -- hotkeys (host-level: Ctrl+W closes the active tab, etc.) -----

    def _apply_hotkeys(self) -> None:
        # Rebuilt (not just created once) so Settings changes can take
        # effect immediately -- there's exactly one owner of hotkeys
        # now (this shell), unlike the old per-connection-window model
        # where a change only ever reached the *next* window opened.
        for shortcut in getattr(self, "_hotkey_shortcuts", []):
            shortcut.setParent(None)
        self._hotkey_shortcuts = [
            QShortcut(
                QKeySequence(self._hotkeys["spawn_log_window"]),
                self,
                activated=self._spawn_log_for_current_tab,
            ),
            QShortcut(
                QKeySequence(self._hotkeys["switch_input_focus"]),
                self,
                activated=self._switch_input_focus_on_current_tab,
            ),
            QShortcut(
                QKeySequence(self._hotkeys["close_window"]), self, activated=self.close_current_tab
            ),
        ]

    def closeEvent(self, event) -> None:  # noqa: N802 -- Qt override signature
        # The root window closing means the whole program exits --
        # explicit, not left to Qt's quitOnLastWindowClosed default,
        # since the address book or a spawn window might still be open
        # when this happens.
        for index in range(self.tab_widget.count()):
            self.tab_widget.widget(index).shutdown()
        super().closeEvent(event)
        app = QApplication.instance()
        if app is not None:
            app.quit()
