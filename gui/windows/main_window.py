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

from typing import Dict, List, Optional

from PySide6.QtCore import QDateTime, QEvent, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSystemTrayIcon,
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
from engine.storage import logs_dir as default_logs_dir
from engine.storage import drafts_dir as default_drafts_dir
from engine.storage import ssh_known_hosts_path
from engine.storage import ssl_known_certs_path
from engine.storage.paths import safe_filename
from engine.errorlog import get_error_log
from engine.net import CertificateStore, HostKeyStore

from ..dialogs.settings_dialog import SettingsDialog
from ..help.help_window import HelpWindow
from ..theme import apply_theme
from ..tray_icon import TrayIcon
from .text_editor_window import TextEditor
from .error_log_window import ErrorLogWindow
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
    # Active-tab highlight (Rick's real report: in dark mode, Fusion's
    # own selected-vs-unselected tab shading is too subtle to tell which
    # tab you're on "at a glance" -- confirmed by pixel-checking a real
    # screenshot before picking a fix, not assumed). A distinct color
    # from ACTIVITY_COLOR on purpose -- a steady cyan tab (this one) vs.
    # a blinking orange tab (unseen activity elsewhere) must stay
    # visually distinguishable at a glance, not just "some tab is
    # colored." Verified against both themes with real screenshots
    # (light and dark) before picking one fixed value for both, same
    # simplification ACTIVITY_COLOR already makes.
    ACTIVE_TAB_COLOR = QColor(78, 201, 245)  # cyan
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
        logs_dir=None,
        error_log=None,
        drafts_dir=None,
        scrollback_font_family: str = "",
        scrollback_font_size: int = 0,
        input_font_family: str = "",
        input_font_size: int = 0,
        splitter_sizes: Optional[list] = None,
        editor_font_family: str = "",
        editor_font_size: int = 0,
        editor_line_numbers: bool = True,
        editor_word_wrap: bool = True,
        editor_window_geometry: Optional[list] = None,
        editor_last_dir: str = "",
        upload_last_dir: str = "",
        host_key_store=None,
        cert_store=None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("MushTato")

        # Same pattern as every other phase: defaults to the plain
        # constant, never touching disk on its own -- callers that want
        # the user's actually-saved values (gui/app.py) load Settings
        # themselves and pass them through explicitly. Keeps
        # construction side-effect-free for tests. Merged with
        # DEFAULT_HOTKEYS (not used as-is) for the same reason
        # engine/storage/settings.py's load_settings() already merges
        # rather than trusting a saved file is complete -- a caller
        # passing a hand-rolled partial dict (real tests already did
        # this) must never leave a newly-added action unbound; caught
        # by exactly that happening when open_text_editor was added.
        self._hotkeys = {**DEFAULT_HOTKEYS, **hotkeys} if hotkeys is not None else dict(DEFAULT_HOTKEYS)
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
        # Phase 11: same override pattern as scripts_dir above, threaded
        # through to every SpawnWindow via SessionTab -- tests must
        # never touch the real per-user logs directory when saving a
        # spawnlog (the exact class of leak Phase 9 already hit once
        # with world_script_path).
        self._logs_dir = logs_dir if logs_dir is not None else default_logs_dir()
        # Phase 11: defaults to the real process-wide singleton (sys.
        # excepthook/threading.excepthook are themselves inherently
        # process-global, so there's naturally one shared ErrorLog in
        # the real app) -- overridable so tests get an independent,
        # disk-isolated instance instead of polluting/reading the real
        # one shared across the whole test process.
        self._error_log = error_log if error_log is not None else get_error_log()
        # Phase 12: same override pattern as logs_dir above.
        self._drafts_dir = drafts_dir if drafts_dir is not None else default_drafts_dir()
        # SSH support: same override pattern -- defaults to the real
        # per-user known-hosts store, overridable so tests never touch
        # it. One shared instance for every tab (blank tabs opened via
        # open_blank_tab(), and eventually SSH-protocol address book
        # worlds), since it's backed by one shared on-disk file.
        self._host_key_store = (
            host_key_store if host_key_store is not None else HostKeyStore(ssh_known_hosts_path())
        )
        # SSL support (item 6 of the SSL/proxy/NAWS plan): identical
        # override pattern to _host_key_store above -- one shared
        # instance for every tab, backed by one shared on-disk file,
        # overridable so tests never touch the real per-user store.
        self._cert_store = (
            cert_store if cert_store is not None else CertificateStore(ssl_known_certs_path())
        )
        self._editor_font_family = editor_font_family
        self._editor_font_size = editor_font_size
        self._editor_line_numbers = editor_line_numbers
        self._editor_word_wrap = editor_word_wrap
        # One shared "starting geometry/directory for the next new
        # editor window" preference -- same non-live-updating-already-
        # open-windows reasoning as splitter_sizes above, not per-window
        # state (Text Editor windows can be multiple and simultaneous,
        # Rick's checkpoint choice).
        self._editor_window_geometry = list(editor_window_geometry) if editor_window_geometry else []
        self._editor_last_dir = editor_last_dir
        # Shared "next Upload dialog's starting directory" preference,
        # same non-live-updating-already-open-tabs reasoning as
        # editor_last_dir above.
        self._upload_last_dir = upload_last_dir
        self._address_book_window = None  # lazily constructed on first use
        self._help_window = None  # lazily constructed on first use
        self._error_log_window = None  # lazily constructed on first use
        # Multiple simultaneous windows (Rick's checkpoint choice) --
        # same list-not-singleton pattern SessionTab.spawn_windows
        # already established for SpawnWindow, not the singleton-
        # satellite pattern Help/Address Book/Error Log use.
        self._text_editor_windows: List[TextEditor] = []

        self.tab_widget = QTabWidget(self)
        self.tab_widget.setTabsClosable(False)
        # Phase 11: Qt's own native drag-to-reorder -- session-only per
        # checkpoint (tabs are live connections, not documents; nothing
        # currently reopens closed tabs except the separate auto-login
        # feature), so this is the entire scope, no persistence layer.
        self.tab_widget.setMovable(True)
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
        # Tracked by tab object, not index, same reasoning as
        # _tabs_with_activity above -- indices shift as tabs open/close.
        self._active_tab: Optional[SessionTab] = None
        self._activity_timer = QTimer(self)
        self._activity_timer.setInterval(self.ACTIVITY_BLINK_INTERVAL_MS)
        self._activity_timer.timeout.connect(self._tick_activity_flash)

        # Phase 12c: system tray icon. Always shown whenever the
        # platform supports one at all -- no separate show/hide setting
        # (Phase 12 checkpoint) -- guarded by isSystemTrayAvailable()
        # so this degrades to simply not existing rather than crashing
        # on a platform/environment without tray support (this dev
        # sandbox's offscreen platform included).
        self._tray_icon: Optional[TrayIcon] = None
        self._tray_activity_pending = False
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray_icon = TrayIcon(self)
            self._tray_icon.restore_requested.connect(self._restore_from_tray)
            self._tray_icon.exit_requested.connect(self._exit_application)
            self._tray_icon.show()

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
            splitter_sizes=(
                (world.splitter_sizes if world is not None and world.splitter_sizes else None)
                or (self._splitter_sizes or None)
            ),
            script_store_path=(
                self._scripts_dir / f"{safe_filename(world.name)}.json" if world is not None else None
            ),
            logs_dir_override=self._logs_dir,
            upload_last_dir=self._upload_last_dir,
            host_key_store=self._host_key_store,
            cert_store=self._cert_store,
        )
        self._wire_new_tab(tab)
        return tab

    def open_blank_tab(self) -> SessionTab:
        """Opens a new tab with no connection yet -- the user
        establishes it themselves by typing ``/connect <host> <port>``
        or ``/ssh [-p port] user@host``. No existing-tab dedup check
        applies here (there's no host:port yet to dedup against).
        """
        tab = SessionTab(
            host_window=self,
            theme=self._theme,
            scrollback_font_family=self._scrollback_font_family,
            scrollback_font_size=self._scrollback_font_size,
            input_font_family=self._input_font_family,
            input_font_size=self._input_font_size,
            splitter_sizes=self._splitter_sizes or None,
            upload_last_dir=self._upload_last_dir,
            host_key_store=self._host_key_store,
            cert_store=self._cert_store,
        )
        self._wire_new_tab(tab)
        return tab

    def _wire_new_tab(self, tab: SessionTab) -> int:
        tab.connectionStateChanged.connect(lambda state, t=tab: self._on_tab_state_changed(t, state))
        tab.activity.connect(lambda t=tab: self._on_tab_activity(t))
        # A blank tab's placeholder "New Tab" name becomes a real one
        # once /connect or /ssh establishes its first connection --
        # this is what keeps the QTabWidget's own label in sync with it.
        tab.titleChanged.connect(lambda title, t=tab: self._on_tab_title_changed(t, title))
        index = self.tab_widget.addTab(tab, tab.name)
        self.tab_widget.setCurrentIndex(index)
        self._refresh_action_enabled_state()
        return index

    def _on_tab_title_changed(self, tab: SessionTab, title: str) -> None:
        index = self.tab_widget.indexOf(tab)
        if index != -1:
            self.tab_widget.setTabText(index, title)
        self._refresh_status_bar()

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

    def save_mail_settings_for_world(self, world: WorldProfile) -> None:
        """Persist ``world``'s mail_format/mail_format_custom/
        mail_convert_returns/mail_convert_returns_to (Phase 12b) --
        same reload-find-copy-save pattern as record_world_connected
        above, since ``world`` (already mutated in place by MailWindow
        itself before this is called) may not be the same object
        AddressBookWindow's in-memory list holds.
        """
        worlds = load_address_book(self._address_book_path)
        for candidate in worlds:
            if (
                candidate.name.lower() == world.name.lower()
                and candidate.host == world.host
                and candidate.port == world.port
            ):
                candidate.mail_format = world.mail_format
                candidate.mail_format_custom = world.mail_format_custom
                candidate.mail_convert_returns = world.mail_convert_returns
                candidate.mail_convert_returns_to = world.mail_convert_returns_to
                break
        save_address_book(self._address_book_path, worlds)
        if self._address_book_window is not None:
            self._address_book_window.worlds = worlds
            self._address_book_window._refresh_list()

    def _open_mail_window_for_current_tab(self) -> None:
        tab = self.tab_widget.currentWidget()
        if tab is not None:
            tab.open_mail_window()

    def _open_upload_for_current_tab(self) -> None:
        tab = self.tab_widget.currentWidget()
        if tab is not None:
            tab.open_upload_dialog()

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
            editor_font_family=self._editor_font_family,
            editor_font_size=self._editor_font_size,
            editor_line_numbers=self._editor_line_numbers,
            editor_word_wrap=self._editor_word_wrap,
            editor_window_geometry=self._editor_window_geometry,
            editor_last_dir=self._editor_last_dir,
            upload_last_dir=self._upload_last_dir,
        )

    def _save_settings_to_disk(self) -> None:
        save_settings(settings_path(), self._current_settings())

    def record_splitter_sizes(self, sizes) -> None:
        """Remember the dual-input splitter's last-dragged sizes as one
        global preference -- applied as the *starting* split for the
        next newly-opened tab that has no world of its own (a blank tab,
        or a raw ``/connect host port``), this session or a future
        launch.

        Post-1.1.0: a tab connected to a *saved* world no longer goes
        through this method at all -- see
        ``save_splitter_sizes_for_world`` below, which persists per-world
        instead, reversing the original post-8b decision to keep this a
        single app-wide preference (per Rick's later, explicit request).
        This method remains the mechanism for world-less tabs, which
        have nowhere per-world to persist to.

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

    def save_splitter_sizes_for_world(self, world: WorldProfile, sizes) -> None:
        """Persist ``world``'s dual-input splitter size (post-1.1.0) --
        same reload-find-copy-save pattern as
        ``save_mail_settings_for_world``, since ``world`` may not be the
        same object AddressBookWindow's in-memory list holds. Debouncing
        happens on the caller's side (SessionTab keeps its own per-tab
        timer) since this does a full address-book reload/save on every
        call -- much more expensive than the in-memory-only
        ``record_splitter_sizes`` above, so it must never be called on
        every raw ``splitterMoved`` pixel event.
        """
        world.splitter_sizes = list(sizes)
        worlds = load_address_book(self._address_book_path)
        for candidate in worlds:
            if (
                candidate.name.lower() == world.name.lower()
                and candidate.host == world.host
                and candidate.port == world.port
            ):
                candidate.splitter_sizes = world.splitter_sizes
                break
        save_address_book(self._address_book_path, worlds)
        if self._address_book_window is not None:
            self._address_book_window.worlds = worlds
            self._address_book_window._refresh_list()

    # -- Phase 12: Text Editor shared "next new window" preferences ---
    # Same reasoning as record_splitter_sizes above: each of these is a
    # starting default for the *next* newly-opened editor window, not a
    # live-update to every already-open one -- toggling Word Wrap in
    # one editor shouldn't silently change a different open editor's
    # display. Reuses the same debounce timer as splitter_sizes (it was
    # already a generic "debounce a full settings save," not something
    # splitter-specific) since window resize/move events fire just as
    # rapidly as splitter dragging does.

    def record_editor_line_numbers(self, enabled: bool) -> None:
        self._editor_line_numbers = enabled
        self._splitter_save_timer.start()

    def record_editor_word_wrap(self, enabled: bool) -> None:
        self._editor_word_wrap = enabled
        self._splitter_save_timer.start()

    def record_editor_geometry(self, geometry: List[int]) -> None:
        self._editor_window_geometry = list(geometry)
        self._splitter_save_timer.start()

    def record_editor_last_dir(self, directory: str) -> None:
        self._editor_last_dir = directory
        self._splitter_save_timer.start()

    def record_upload_last_dir(self, directory: str) -> None:
        self._upload_last_dir = directory
        self._splitter_save_timer.start()

    def open_text_editor(self) -> TextEditor:
        """Always opens a *new* Text Editor window -- Rick's explicit
        checkpoint choice over the single-reused-window pattern every
        other satellite window here uses, matching the existing
        SpawnWindow precedent (a tracked list, not one slot) instead.
        """
        window = TextEditor(
            self,
            font_family=self._editor_font_family,
            font_size=self._editor_font_size,
            line_numbers=self._editor_line_numbers,
            word_wrap=self._editor_word_wrap,
            geometry=self._editor_window_geometry or None,
            last_dir=self._editor_last_dir,
            drafts_dir_override=self._drafts_dir,
        )
        window.closed.connect(lambda: self._remove_text_editor_window(window))
        self._text_editor_windows.append(window)
        window.show()
        return window

    def _remove_text_editor_window(self, window: TextEditor) -> None:
        if window in self._text_editor_windows:
            self._text_editor_windows.remove(window)

    def _refont_open_editors(self) -> None:
        for window in self._text_editor_windows:
            window.apply_font(self._editor_font_family, self._editor_font_size)

    def _on_current_tab_changed(self, index: int) -> None:
        new_tab = self.tab_widget.widget(index) if index != -1 else None
        if new_tab is not None:
            self._clear_tab_activity(new_tab)
        self._update_active_tab_highlight(new_tab)
        # Switching tabs at all counts as "you looked at something" for
        # the tray icon -- even switching to a tab that wasn't itself
        # flashing still means you're paying attention to the app now.
        self._set_tray_activity_pending(False)
        self._refresh_status_bar()
        self._refresh_action_enabled_state()
        self._refresh_timestamps_action_state()

    def _update_active_tab_highlight(self, new_tab: Optional[SessionTab]) -> None:
        """Colors the currently active tab's label distinctly (cyan) so
        which tab you're on is obvious at a glance -- see
        ACTIVE_TAB_COLOR's own comment for why this exists and why it's
        a plain QTabBar.setTabTextColor() call, not a stylesheet.
        """
        bar = self.tab_widget.tabBar()
        if self._active_tab is not None and self._active_tab is not new_tab:
            old_index = self.tab_widget.indexOf(self._active_tab)
            if old_index != -1:
                bar.setTabTextColor(old_index, QColor())
        if new_tab is not None:
            new_index = self.tab_widget.indexOf(new_tab)
            if new_index != -1:
                bar.setTabTextColor(new_index, self.ACTIVE_TAB_COLOR)
        self._active_tab = new_tab

    def _on_tab_state_changed(self, tab: SessionTab, state: str) -> None:
        if self.tab_widget.currentWidget() is tab:
            self.status_state_label.setText(state)

    # -- tab-activity flashing ------------------------------------------

    def _on_tab_activity(self, tab: SessionTab) -> None:
        is_active_tab = self.tab_widget.currentWidget() is tab
        # Broader than the tab-label-flash condition below (Phase 12c
        # checkpoint, Rick's explicit choice over just reusing
        # _tabs_with_activity as-is): the tray icon should also notice
        # activity on the tab you were already looking at, if the whole
        # app itself wasn't focused (e.g. minimized or alt-tabbed away)
        # when it arrived -- closer to Potato's own real condition
        # (verified against potato.tcl: new activity AND (app isn't
        # focused at all OR it's a different connection)).
        if not is_active_tab or QApplication.activeWindow() is None:
            self._set_tray_activity_pending(True)

        # Only *other* tabs get flashed in the tab bar itself -- text
        # arriving in the tab you're already looking at isn't "activity
        # you missed" in that narrower sense, regardless of the tray
        # condition above.
        if is_active_tab:
            return
        if tab not in self._tabs_with_activity:
            self._tabs_with_activity.add(tab)
        if not self._activity_timer.isActive():
            self._activity_flash_on = True
            self._apply_activity_colors()
            self._activity_timer.start()

    def _set_tray_activity_pending(self, pending: bool) -> None:
        self._tray_activity_pending = pending
        if self._tray_icon is None:
            return
        if pending:
            self._tray_icon.start_blinking()
        else:
            self._tray_icon.stop_blinking()

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
            self._editor_font_family = result.editor_font_family
            self._editor_font_size = result.editor_font_size
            # editor_line_numbers/word_wrap/window_geometry/last_dir
            # aren't editable in the dialog either -- same pass-through
            # reasoning as splitter_sizes.
            self._editor_line_numbers = result.editor_line_numbers
            self._editor_word_wrap = result.editor_word_wrap
            self._editor_window_geometry = result.editor_window_geometry
            self._editor_last_dir = result.editor_last_dir
            # upload_last_dir isn't editable in the dialog either --
            # same pass-through reasoning as splitter_sizes/editor_last_dir.
            self._upload_last_dir = result.upload_last_dir
            self._save_settings_to_disk()
            self._apply_hotkeys()  # only one owner of hotkeys now -- live-reload is cheap
            app = QApplication.instance()
            if app is not None:
                apply_theme(app, self._theme)
            self._retheme_open_tabs()
            self._refont_open_tabs()
            self._refont_open_editors()

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

    def show_error_log(self) -> None:
        """Open the Error Log window (Phase 11) -- a lazily-constructed
        singleton, same reuse pattern as the Help/Address Book windows.
        Available with zero tabs open, same reasoning as Help: this
        shows unhandled-exception history, not anything tied to one
        connection.
        """
        if self._error_log_window is None:
            self._error_log_window = ErrorLogWindow(self._error_log)
        else:
            self._error_log_window.refresh()
        self._error_log_window.show()
        self._error_log_window.raise_()
        self._error_log_window.activateWindow()

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
        self.new_tab_action = add_action(file_menu, "New Tab", lambda: self.open_blank_tab())
        self.address_book_action = add_action(file_menu, "Address Book...", self._show_address_book)
        self.reconnect_action = add_action(file_menu, "Reconnect", self._reconnect_current_tab)
        self.disconnect_action = add_action(file_menu, "Disconnect", self._disconnect_current_tab)
        file_menu.addSeparator()
        self.close_action = add_action(file_menu, "Close", self.close_current_tab)
        file_menu.addSeparator()
        self.exit_action = add_action(file_menu, "Exit", self._exit_application)

        toolbar.addAction(self.new_tab_action)
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
        # Phase 11: real implementation of what was a disabled
        # placeholder through Phase 10 -- toggles the active tab's own
        # FindBar, same "same handler" principle as every other chrome
        # action (Ctrl+F and this menu item both call toggle_find_bar()
        # on whichever tab is active).
        self.find_action = add_action(edit_menu, "Find...", self._toggle_find_on_current_tab)
        self.find_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Find))

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

        # Per-tab, not host-level (checkpointed 2026-07-27) -- unlike
        # Theme, this checkbox reflects whichever tab is currently
        # active and is re-synced on every tab switch (see
        # _refresh_timestamps_action_state), not one shared state.
        self.timestamps_action = QAction("Show Timestamps", self)
        self.timestamps_action.setCheckable(True)
        self.timestamps_action.triggered.connect(self._toggle_timestamps_on_current_tab)
        view_menu.addAction(self.timestamps_action)

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

        # -- Tools (Events is still a placeholder; Potato has this,
        # MushTato doesn't yet. Editor, Upload, and Mail Window are real.) --
        self.tools_menu = tools_menu = menu_bar.addMenu("&Tools")
        self.editor_action = add_action(tools_menu, "Editor", self.open_text_editor)
        self.upload_action = add_action(tools_menu, "Upload", self._open_upload_for_current_tab)
        self.mail_window_action = add_action(tools_menu, "Mail Window", self._open_mail_window_for_current_tab)
        self.events_action = add_action(tools_menu, "Events", None, enabled=False)
        tools_menu.addSeparator()
        self.error_log_action = add_action(tools_menu, "Error Log", self.show_error_log)
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
            self.find_action,
            self.mail_window_action,
            self.upload_action,
            self.timestamps_action,
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

    def _toggle_find_on_current_tab(self) -> None:
        tab = self.tab_widget.currentWidget()
        if tab is not None:
            tab.toggle_find_bar()

    def _toggle_timestamps_on_current_tab(self, checked: bool) -> None:
        tab = self.tab_widget.currentWidget()
        if tab is not None:
            tab.set_show_timestamps(checked)

    def _refresh_timestamps_action_state(self) -> None:
        """Syncs the View menu's checkbox to whichever tab is now
        active -- this is genuinely per-tab state (unlike Theme), so
        switching tabs must not silently carry one tab's on/off setting
        over to another's display. blockSignals guards against
        setChecked() here re-triggering _toggle_timestamps_on_current_tab,
        which would otherwise flip the *new* tab's real state to match
        whatever the old tab's checkbox happened to show.
        """
        tab = self.tab_widget.currentWidget()
        self.timestamps_action.blockSignals(True)
        self.timestamps_action.setChecked(tab.show_timestamps if tab is not None else False)
        self.timestamps_action.blockSignals(False)

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

    def _restore_from_tray(self) -> None:
        # Matches Potato's real winicoRestore (deiconify + raise +
        # focus) -- MushTato has just the one persistent root window,
        # so "restore" always means this one.
        self.showNormal()
        self.raise_()
        self.activateWindow()

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
            QShortcut(
                QKeySequence(self._hotkeys["open_text_editor"]),
                self,
                activated=self.open_text_editor,
            ),
            QShortcut(
                QKeySequence(self._hotkeys["new_tab"]),
                self,
                activated=lambda: self.open_blank_tab(),
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

    def changeEvent(self, event) -> None:  # noqa: N802 -- Qt override signature
        super().changeEvent(event)
        # The app regaining OS focus counts as "you noticed" for the
        # tray icon (Phase 12c checkpoint) -- even if you never
        # switched tabs, e.g. you were already sitting on the one tab
        # that got new text and just alt-tabbed back.
        if event.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            self._set_tray_activity_pending(False)
