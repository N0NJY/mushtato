"""One connection's content: scrollback + dual input, spawn windows,
built-in commands (Phase 7e: extracted from what used to be MainWindow's
entire content, now that MainWindow is a tabbed shell hosting one or
more of these instead of being one connection itself).

Phase 9: engine/scripting is wired in for real here. Every tab gets its
own ``ScriptWorld`` unconditionally (even a world with zero saved
scripts gets an empty one -- one uniform pipeline, no "scripting active
or not" branch), loaded from engine/storage/script_store.py. Incoming
text is line-buffered, ANSI-parsed, and trigger-dispatched (gag/
highlight) on the connection's own background thread via
``LineDispatcher`` (engine/scripting/line_dispatch.py), reached through
``TelnetBridge``'s ``on_text`` callback -- never the GUI thread, since a
slow/hung trigger's ``run_with_timeout`` wait must not freeze the UI
(see telnet_bridge.py's module docstring). Only the final, already-
processed result crosses back to the GUI thread via
``_incomingBatchReady``, a plain Qt signal (safe to emit from any
thread -- Qt marshals delivery based on the *receiving* SessionTab's
own GUI-thread affinity). Outbound alias expansion gets the same
treatment via ``TelnetBridge.run_in_background``.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QDateTime, QTimer, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QSizePolicy, QSplitter, QTextBrowser, QVBoxLayout, QWidget

from engine.ansi import DEFAULT_STYLE, Style, StyledSegment
from engine.commands import CommandTable
from engine.scripting import (
    MAX_CONSECUTIVE_TRIGGER_FAILURES,
    DispatchOutcome,
    LineDispatcher,
    LineDispatchResult,
    ScriptWorld,
)
from engine.scripting.errors import ScriptError
from engine.storage import (
    DEFAULT_THEME,
    CharacterProfile,
    ScriptRecord,
    WorldProfile,
    WorldScriptProfile,
    load_world_scripts,
    save_world_scripts,
    world_script_path,
)

from ..fonts import resolve_input_font, resolve_scrollback_font
from ..help.markdown_tools import strip_markdown
from ..help.topics import COMMAND_HELP, HelpContext, TOPICS, get_topic
from ..theme import apply_scrollback_theme
from ..version import mushtato_version
from .history_line_edit import HistoryLineEdit
from .spawn_window import SpawnWindow
from .styled_text_qt import append_styled_segments, replace_tail
from .telnet_bridge import TelnetBridge


class SessionTab(QWidget):
    """A single connection's scrollback/input/bridge, embeddable as one
    page of MainWindow's QTabWidget. Constructible with
    ``host_window=None`` for standalone headless testing -- commands
    that need the shell (``/connect``, ``/settings``, ``/theme``)
    degrade to a "not available" message in that case, same pattern
    Phase 7c used for MainWindow's optional ``address_book``.
    """

    titleChanged = Signal(str)
    connectionStateChanged = Signal(str)
    activity = Signal()  # new text arrived -- host decides if this tab is "active" or not
    # Phase 9: carries a LineDispatchResult + a list of newly-registered
    # TimerRequests, emitted from TelnetBridge's on_text callback on the
    # connection's background thread -- safe to emit from any thread,
    # Qt marshals delivery onto this SessionTab's own GUI thread.
    _incomingBatchReady = Signal(object, object)
    # echo() is always routed through this signal regardless of which
    # thread called it (background trigger/alias dispatch, or the GUI
    # thread itself for load_script/on_connect/timers) -- uniform,
    # thread-safe handling without needing to branch on caller context.
    _scriptEchoRequested = Signal(str, object)
    # (alias_text, AliasOutcome) -- result of a background-thread alias
    # expansion attempt; AliasOutcome.error carries any failure.
    _aliasExpansionDone = Signal(str, object)
    triggerStateChanged = Signal(str)  # a trigger's enabled state changed -- Scripts UI refresh hook

    # Post-Phase-9 addition: automatic reconnection after a dropped
    # connection. Fixed 30s for every world (Rick's explicit choice
    # over a per-world configurable interval, which Potato's own real
    # autoreconnect,time option supports but Rick didn't want the extra
    # UI for) -- retries indefinitely until it succeeds or the user
    # clicks Disconnect (also Rick's explicit choice, matching Potato's
    # real behavior of reusing Disconnect as the "cancel pending
    # reconnect" action, verified against potato-skin.tcl).
    AUTO_RECONNECT_INTERVAL_MS = 30_000

    def __init__(
        self,
        host: str,
        port: int,
        *,
        name: Optional[str] = None,
        bridge: Optional[TelnetBridge] = None,
        theme: Optional[str] = None,
        host_window=None,  # the MainWindow shell; None only in standalone tests
        world: Optional[WorldProfile] = None,  # Phase 8b: auto-sends/login need the saved profile
        character: Optional[CharacterProfile] = None,  # explicit "Log In as" choice, overrides
        # world.default_character for this one connection without changing it
        scrollback_font_family: str = "",
        scrollback_font_size: int = 0,
        input_font_family: str = "",
        input_font_size: int = 0,
        splitter_sizes: Optional[List[int]] = None,  # last-dragged split, None -> stretch-factor default
        script_store_path=None,  # test-only override for world_script_path(world.name); see _script_store_path()
    ) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.name = name or f"{host}:{port}"
        self.host_window = host_window
        self.world = world
        self._script_store_path_override = script_store_path
        self._explicit_character = character
        self._theme = theme if theme is not None else DEFAULT_THEME
        self.connected_at: Optional[QDateTime] = None
        self.connection_state = "Connecting"
        self.spawn_windows: List[SpawnWindow] = []
        # The "preview" of the still-incomplete trailing line (Phase 9,
        # see engine/scripting/line_dispatch.py's module docstring) --
        # tracked as a document position so a later feed() result can
        # replace it in place rather than appending a duplicate.
        self._preview_start_position: Optional[int] = None
        self._preview_segments: List[StyledSegment] = []
        # Repeating (not single-shot) -- once started, keeps firing
        # every AUTO_RECONNECT_INTERVAL_MS until explicitly stopped
        # (a successful reconnect, or the user clicking Disconnect).
        self._auto_reconnect_timer = QTimer(self)
        self._auto_reconnect_timer.setInterval(self.AUTO_RECONNECT_INTERVAL_MS)
        self._auto_reconnect_timer.timeout.connect(self._auto_reconnect_tick)

        # QTextBrowser (a QTextEdit subclass), not plain QTextEdit --
        # needed for URLs in incoming text to actually be clickable
        # (setOpenExternalLinks/anchorClicked are QTextBrowser-only; a
        # plain QTextEdit renders the same anchor formatting but never
        # responds to a click on it). Already the established pattern
        # for the Help window's content pane (gui/help/help_window.py),
        # including the viewport-palette-fix this scrollback already
        # needs regardless (see apply_scrollback_theme below).
        self.scrollback = QTextBrowser(self)
        self.scrollback.setReadOnly(True)
        self.scrollback.setOpenExternalLinks(True)
        # MUD output (banners, tables, ASCII-art borders, prompts) is
        # authored assuming a fixed-width terminal; the default
        # proportional GUI font breaks that alignment. resolve_
        # scrollback_font falls back to the same fixed-width system
        # font as before when no font setting has been saved yet.
        self.scrollback.setFont(resolve_scrollback_font(scrollback_font_family, scrollback_font_size))

        # Dual input (Phase 6): two independent boxes, both sending to
        # this same connection, each with its own recall history.
        # `input_line` (primary) is for ordinary commands -- it's the
        # only one that checks for built-in "/" commands (Phase 7c) or
        # will apply alias expansion once scripting is wired into the
        # GUI (still deferred). `secondary_input` is for longer
        # free-form text (poses/says); it bypasses *both* -- a pose
        # starting with "/" or a word that happens to match an alias
        # must never be silently reinterpreted, same reasoning for both.
        input_font = resolve_input_font(input_font_family, input_font_size)

        self.input_line = HistoryLineEdit(self)
        self.input_line.setPlaceholderText("Command...")
        self.input_line.returnPressed.connect(self._on_primary_send)
        self.input_line.setFont(input_font)
        # A plain QLineEdit's default vertical size policy is Fixed, so
        # it would ignore any extra space the splitter below hands it.
        self.input_line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.secondary_input = HistoryLineEdit(self)
        self.secondary_input.setPlaceholderText("Pose/says...")
        self.secondary_input.returnPressed.connect(self._on_secondary_send)
        self.secondary_input.setFont(input_font)
        self.secondary_input.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        input_container = QWidget(self)
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.addWidget(self.input_line)
        input_layout.addWidget(self.secondary_input)

        self.splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.splitter.addWidget(self.scrollback)
        self.splitter.addWidget(input_container)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 1)
        if splitter_sizes:
            self.splitter.setSizes(splitter_sizes)
        # Persisted globally (one preference for every tab, not
        # per-world -- Rick's explicit choice), so the *next* tab you
        # open -- this session or a future one -- starts at whatever
        # height you last dragged to. Deliberately does NOT resize
        # already-open tabs live when another tab is dragged; see
        # MainWindow.record_splitter_sizes's docstring.
        self.splitter.splitterMoved.connect(self._on_splitter_moved)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)

        apply_scrollback_theme(self.scrollback, self._theme)

        self._commands = CommandTable()
        self._register_commands()

        # -- Phase 9: scripting --------------------------------------
        # Unconditional, even for a world with zero saved scripts --
        # one uniform pipeline for every tab, no "scripting active or
        # not" branch. send() is a lazy closure (self.bridge doesn't
        # exist yet at this point) rather than a direct reference.
        self.script_world = ScriptWorld(
            send=lambda text: self.bridge.send_line(text),
            echo=self._script_echo,
        )
        self._line_dispatcher = LineDispatcher(self.script_world.triggers)
        self._script_records: List[ScriptRecord] = []
        self._load_saved_scripts(load_variables=True)

        self._incomingBatchReady.connect(self._on_incoming_batch_ready)
        self._scriptEchoRequested.connect(self._on_script_echo_requested)
        self._aliasExpansionDone.connect(self._on_alias_expansion_done)

        # Dependency-injectable so tests can supply a fake bridge that
        # never touches the network (see tests/gui) -- the real
        # runtime path just omits this argument. set_on_text() is
        # called uniformly on whichever bridge we end up with (fresh or
        # injected), rather than only passed at TelnetBridge's own
        # construction, so a test's FakeBridge participates in the same
        # on_text-then-textReceived contract a real TelnetBridge does.
        self.bridge = bridge if bridge is not None else TelnetBridge(
            host, port, nop_keepalive=world.nop_keepalive if world is not None else False
        )
        self.bridge.set_on_text(self._on_raw_incoming_text)
        self.bridge.connected.connect(self._on_connected)
        self.bridge.connectionClosed.connect(self._on_connection_closed)
        self.bridge.connectionFailed.connect(self._on_connection_failed)

        self._append_plain(f"Connecting to {host}:{port} ...\n")
        self._drain_and_schedule_pending_timers()
        self.bridge.start()

    def showEvent(self, event) -> None:  # noqa: N802 -- Qt override signature
        # Reapplies the scrollback theme every time this tab becomes
        # visible (e.g. switched to in the QTabWidget) -- see
        # gui/theme.apply_scrollback_theme's docstring for the real
        # viewport-palette bug this guards against.
        super().showEvent(event)
        apply_scrollback_theme(self.scrollback, self._theme)

    def apply_theme(self, theme: str) -> None:
        """Re-applies a changed theme to this tab's own scrollback.

        Called by the host when the user switches theme while this tab
        is already open -- closes a previously-accepted Phase 7b gap
        (only *newly created* windows ever picked up a theme change;
        already-open ones didn't) now that MainWindow has direct access
        to every open tab, not just a "next window" it hasn't made yet.
        """
        self._theme = theme
        apply_scrollback_theme(self.scrollback, theme)

    def apply_fonts(
        self, scrollback_font_family: str, scrollback_font_size: int,
        input_font_family: str, input_font_size: int,
    ) -> None:
        """Re-applies changed font settings to this tab's widgets --
        called by the host on every already-open tab when Settings is
        saved, the same live-reload treatment apply_theme() already
        gets (unlike splitter size, which only affects newly-opened
        tabs -- see MainWindow.record_splitter_sizes's docstring for
        why those two are treated differently).
        """
        self.scrollback.setFont(resolve_scrollback_font(scrollback_font_family, scrollback_font_size))
        input_font = resolve_input_font(input_font_family, input_font_size)
        self.input_line.setFont(input_font)
        self.secondary_input.setFont(input_font)

    def _on_splitter_moved(self, pos: int, index: int) -> None:  # noqa: ARG002 -- Qt signal args
        del pos, index
        if self.host_window is not None:
            self.host_window.record_splitter_sizes(self.splitter.sizes())

    # -- Phase 9: scripting ---------------------------------------------
    # engine/scripting wired in for real: every tab gets its own
    # ScriptWorld (send/echo/gag/highlight/set_var/get_var/timer/
    # on_trigger/on_connect/on_alias), loaded from engine/storage/
    # script_store.py. Incoming-line trigger dispatch and outbound
    # alias expansion both run off the GUI thread (see this module's
    # docstring); only already-processed results cross back via Qt
    # signals, which are safe to emit from any thread.

    def _load_saved_scripts(self, *, load_variables: bool) -> None:
        """Load this world's saved scripts (and, on first load only,
        its saved variables) into ``self.script_world``.

        ``load_variables=False`` is used by :meth:`reload_scripts` --
        re-reading variables from disk on a mid-session script reload
        would silently revert whatever the live session has
        accumulated via set_var() back to a stale on-disk snapshot,
        which script source/trigger changes have no business touching.
        A no-op for a world-less tab (direct-connect, or a standalone
        test) -- there's nothing saved to load.
        """
        if self.world is None:
            return
        profile = load_world_scripts(self._script_store_path())
        if load_variables:
            self.script_world.variables = dict(profile.variables)
        for record in profile.scripts:
            self._script_records.append(record)
            if not record.enabled:
                continue
            self._load_one_script(record)

    def _load_one_script(self, record: ScriptRecord) -> None:
        try:
            self.script_world.load_script(record.source, script_name=record.name)
        except ScriptError as exc:
            self._append_plain(f"[Script error loading {record.name!r}: {exc}]\n")
        except Exception as exc:  # noqa: BLE001 - a script's own bug must not crash the tab
            self._append_plain(
                f"[Script error loading {record.name!r}: {type(exc).__name__}: {exc}]\n"
            )

    def reload_scripts(self) -> None:
        """Re-read this world's saved scripts from disk and apply them
        to the already-running ScriptWorld, cleanly unloading every
        previously-loaded script first so an edit-and-resave doesn't
        leave stale/duplicate registrations (or a stale disabled/
        failure-counter state) behind. Called by the host when World
        Properties' Scripts page is saved for a world that has this
        tab currently open -- the mechanism behind "re-saving resets
        the [trigger auto-disable] counter."

        Deliberately does not touch ``script_world.variables`` -- see
        :meth:`_load_saved_scripts`'s docstring.
        """
        if self.world is None:
            return
        for record in self._script_records:
            self.script_world.unload_script(record.name)
        self._script_records = []
        self._load_saved_scripts(load_variables=False)
        self._drain_and_schedule_pending_timers()

    def save_script_state(self) -> None:
        """Persist this world's current script variables to disk.

        Called on disconnect/shutdown, and by the host's periodic
        dirty-flag autosave (MainWindow's script-autosave timer) --
        both paths funnel through here rather than each building their
        own save logic. A no-op for a world-less tab.
        """
        if self.world is None:
            return
        profile = WorldScriptProfile(
            scripts=self._script_records, variables=dict(self.script_world.variables)
        )
        save_world_scripts(self._script_store_path(), profile)
        self.script_world.dirty = False

    def _script_store_path(self):
        """Resolves to the real per-world script file
        (engine/storage/paths.world_script_path) unless a test
        explicitly overrode it at construction -- the same
        dependency-injection pattern MainWindow/AddressBookWindow
        already use for address_book_storage_path/storage_path, so
        tests never touch the real user data directory.
        """
        if self._script_store_path_override is not None:
            return self._script_store_path_override
        return world_script_path(self.world.name)

    def _on_raw_incoming_text(self, raw_text: str) -> None:
        """The TelnetBridge ``on_text`` callback -- runs on the
        connection's own background thread, never the GUI thread (see
        this module's and telnet_bridge.py's docstrings for why that's
        load-bearing, not incidental). Only the final, already trigger-
        processed result crosses back to the GUI thread, via a plain
        Qt signal (safe to emit from any thread).
        """
        result = self._line_dispatcher.feed(raw_text)
        timers = list(self.script_world.pending_timers)
        self.script_world.pending_timers.clear()
        self._incomingBatchReady.emit(result, timers)

    def _on_incoming_batch_ready(self, result: LineDispatchResult, timers: list) -> None:
        any_output = False
        for finalized in result.finalized:
            if finalized.gagged:
                self._clear_preview()
            elif finalized.segments:
                self._insert_finalized_segments(finalized.segments, restore_preview=False)
                for spawn in self.spawn_windows:
                    spawn.receive_segments(finalized.segments)
                any_output = True
            self._report_dispatch_outcome(finalized.outcome)
        if result.preview is not None:
            self._show_preview(result.preview)
            any_output = True
        for timer_request in timers:
            self._schedule_timer_request(timer_request)
        if any_output:
            self.activity.emit()

    def _report_dispatch_outcome(self, outcome: DispatchOutcome) -> None:
        for trigger_name, message in outcome.errors:
            self._append_plain(f"[Script error in trigger {trigger_name!r}: {message}]\n")
        for trigger_name in outcome.disabled_triggers:
            self._append_plain(
                f"[Trigger {trigger_name!r} disabled after "
                f"{MAX_CONSECUTIVE_TRIGGER_FAILURES} consecutive errors "
                "- fix and re-save to re-enable]\n"
            )
            self.triggerStateChanged.emit(trigger_name)

    # -- rendering: finalized lines, echo() output, and the replaceable
    # "preview" of a still-incomplete trailing line all funnel through
    # here so the invariant "the preview, if any, is always the very
    # last thing shown" never gets violated by something else being
    # inserted after it (see engine/scripting/line_dispatch.py's module
    # docstring for why that invariant matters for gag/highlight
    # correctness on a line split across chunks).

    def _end_of_document_position(self) -> int:
        cursor = QTextCursor(self.scrollback.document())
        cursor.movePosition(QTextCursor.End)
        return cursor.position()

    def _clear_preview(self) -> None:
        if self._preview_start_position is not None:
            replace_tail(self.scrollback, self._preview_start_position, [])
            self._preview_start_position = None
            self._preview_segments = []

    def _show_preview(self, segments: List[StyledSegment]) -> None:
        if self._preview_start_position is None:
            self._preview_start_position = self._end_of_document_position()
        replace_tail(self.scrollback, self._preview_start_position, segments)
        self._preview_segments = segments

    def _insert_finalized_segments(
        self, segments: List[StyledSegment], *, restore_preview: bool = True
    ) -> None:
        """Insert ``segments``, preserving the invariant that an
        already-showing preview stays the last thing on screen -- used
        as-is by ``_on_script_echo_requested``, where a script's echo()
        genuinely can land in the middle of an unrelated, still-pending
        partial line (e.g. a prompt) and must not swallow it.

        ``_on_incoming_batch_ready`` (real incoming server text) passes
        ``restore_preview=False`` instead: there, ``segments`` being
        inserted is never unrelated to the current preview -- it's
        frequently *the same pending line* LineDispatcher just finished
        (the preview was exactly that line's not-yet-terminated tail).
        Restoring it here would re-insert that same stale tail right
        after the now-complete line, a real duplicate-output bug found
        by reproducing it directly: a line arriving split across two
        network reads (e.g. 'You say, "some' then ' words"\\n') rendered
        as "You say, \"some words\"\\nYou say, \"some" -- the finalized
        line followed by a phantom repeat of its own tail. The correct,
        current preview state (if any) is already re-applied once, after
        every finalized line in the batch, via LineDispatchResult.preview
        -- this inner restore was always redundant for that call path,
        never just extra-safe.
        """
        pending_preview = self._preview_segments if self._preview_start_position is not None else None
        self._clear_preview()
        append_styled_segments(self.scrollback, segments)
        if restore_preview and pending_preview is not None:
            self._show_preview(pending_preview)

    def _script_echo(self, text: str, style: Optional[Style]) -> None:
        # Always routed through this signal, regardless of caller --
        # uniform, thread-safe handling without needing to branch on
        # context. This is load-bearing, not defensive: engine/
        # scripting/sandbox.py's run_with_timeout() always runs the
        # actual script body on its *own* internal worker thread while
        # the caller blocks on .join() -- true even for script load,
        # on_connect, and timer firing, which might look GUI-thread-
        # native from the outside but are not, internally, for the
        # duration of the script code itself. So this emit is *always*
        # a genuine cross-thread signal, auto-queued for the GUI
        # thread's event loop rather than delivered inline -- echo()'s
        # effect shows up on the next event loop tick, not synchronously
        # in the same call stack (imperceptible in a real running app;
        # a test observing it needs QTest.qWait(), see
        # test_scripting_integration.py's echo test for why).
        self._scriptEchoRequested.emit(text, style)

    def _on_script_echo_requested(self, text: str, style: Optional[Style]) -> None:
        seg_style = style if style is not None else DEFAULT_STYLE
        self._insert_finalized_segments([StyledSegment(text + "\n", seg_style)])
        self.activity.emit()

    def _schedule_timer_request(self, timer_request) -> None:
        delay_ms = max(0, int(timer_request.delay_seconds * 1000))
        QTimer.singleShot(delay_ms, lambda cb=timer_request.callback: self._fire_timer_callback(cb))

    def _fire_timer_callback(self, callback) -> None:
        try:
            self.script_world.run_callback(callback)
        except ScriptError as exc:
            self._append_plain(f"[Script error in timer: {exc}]\n")
        except Exception as exc:  # noqa: BLE001 - a script's own bug must not crash the tab
            self._append_plain(f"[Script error in timer: {type(exc).__name__}: {exc}]\n")
        # A timer callback might itself register a new timer (e.g. a
        # "poll every N seconds" pattern) -- already on the GUI thread
        # here, so draining/scheduling directly is safe.
        self._drain_and_schedule_pending_timers()

    def _drain_and_schedule_pending_timers(self) -> None:
        pending = list(self.script_world.pending_timers)
        self.script_world.pending_timers.clear()
        for timer_request in pending:
            self._schedule_timer_request(timer_request)

    def _expand_alias_background(self, text: str) -> None:
        # Runs on a background worker thread (TelnetBridge.
        # run_in_background) -- AliasEngine.expand() can call
        # run_with_timeout, whose blocking wait must never land on the
        # GUI thread, same reasoning as incoming trigger dispatch.
        outcome = self.script_world.aliases.expand(text)
        self._aliasExpansionDone.emit(text, outcome)

    def _on_alias_expansion_done(self, text: str, outcome) -> None:
        if outcome.error:
            self._append_plain(f"[Script error in alias {outcome.alias_name!r}: {outcome.error}]\n")
        elif not outcome.matched:
            self.bridge.send_line(text)
        self._drain_and_schedule_pending_timers()

    def _append_plain(self, text: str) -> None:
        cursor = QTextCursor(self.scrollback.document())
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.scrollback.setTextCursor(cursor)
        self.scrollback.ensureCursorVisible()

    def _set_connection_state(self, state: str) -> None:
        self.connection_state = state
        self.connectionStateChanged.emit(state)

    def _on_connected(self) -> None:
        self._stop_auto_reconnect()
        self._append_plain("Connected.\n")
        self.connected_at = QDateTime.currentDateTime()
        self._set_connection_state("Connected")
        for name, message in self.script_world.fire_connect_callbacks():
            self._append_plain(f"[Script error in on_connect ({name}): {message}]\n")
        self._drain_and_schedule_pending_timers()
        self._fire_autosends()

    # -- auto-reconnect (post-Phase-9 addition) -------------------------
    # Started whenever the connection drops for a reason the user didn't
    # choose (_on_connection_closed/_on_connection_failed); stopped on a
    # successful (re)connect or an explicit user Disconnect. Ticks call
    # reconnect_bridge() directly -- the exact same method the toolbar/
    # menu/hotkey Reconnect action already uses, not a parallel
    # implementation.

    def _start_auto_reconnect(self) -> None:
        if self._auto_reconnect_timer.isActive():
            return  # already scheduled -- e.g. a retry attempt that itself just failed again
        interval_seconds = self.AUTO_RECONNECT_INTERVAL_MS // 1000
        self._append_plain(
            f"[Will automatically try to reconnect every {interval_seconds} seconds. "
            "Click Disconnect to cancel.]\n"
        )
        self._auto_reconnect_timer.start()

    def _stop_auto_reconnect(self) -> None:
        self._auto_reconnect_timer.stop()

    def _auto_reconnect_tick(self) -> None:
        self.reconnect_bridge()

    # -- Phase 8b: world-level auto-sends + character login ------------
    # Verified against Potato's real dispatch (potato.tcl's
    # sendLoginInfoSub), not invented: after login_delay, in this exact
    # order -- firstconnect (only the world's very first-ever connect,
    # tracked by a persisted counter) -> connect -> character login
    # line -> login. Reuses self.bridge.send_line()/_send_to_bridge()
    # directly, the same path normal typed input already uses -- no
    # engine/scripting involvement, since this is fixed saved text, not
    # user-provided code to sandbox.

    def _fire_autosends(self) -> None:
        if self.world is None:
            return
        is_first_connect = self.world.connect_count == 0
        if self.host_window is not None:
            self.host_window.record_world_connected(self.world)
        delay_ms = max(0, int(self.world.login_delay * 1000))
        QTimer.singleShot(delay_ms, lambda: self._send_autosends(is_first_connect))

    def _send_autosends(self, is_first_connect: bool) -> None:
        if self.world is None:
            return
        if is_first_connect and self.world.autosend_firstconnect:
            self._send_autosend_block(self.world.autosend_firstconnect)
        if self.world.autosend_connect:
            self._send_autosend_block(self.world.autosend_connect)
        character = self._resolve_login_character()
        if character is not None:
            self._send_login_line(character)
        if self.world.autosend_login:
            self._send_autosend_block(self.world.autosend_login)

    def _send_autosend_block(self, block: str) -> None:
        # Matches Potato's own dispatch splitting a multi-line autosend
        # block into one send per line -- but sent as literal raw text
        # via _send_to_bridge, deliberately NOT run through MushTato's
        # own "/" command dispatcher the way Potato's send_to (which
        # calls process_input) does. Autosends are automated,
        # non-interactive text; reinterpreting them as client commands
        # would be a real footgun (a saved autosend line that happens
        # to start with "/quit" would close the tab instead of reaching
        # the server) -- the same reasoning the secondary pose/says
        # input box already uses to always bypass command processing.
        for line in block.splitlines():
            if line:
                self._send_to_bridge(line, apply_aliases=False)

    def _resolve_login_character(self) -> Optional[CharacterProfile]:
        # An explicit "Log In as" choice from the address book always
        # wins, for this one connection only -- it never touches
        # world.default_character, which is why that field's own value
        # is never mutated here.
        if self._explicit_character is not None:
            return self._explicit_character
        if self.world is None or not self.world.default_character:
            return None
        return next(
            (c for c in self.world.characters if c.name == self.world.default_character), None
        )

    def _send_login_line(self, character: CharacterProfile) -> None:
        try:
            line = self.world.login_format.format(name=character.name, password=character.password)
        except (KeyError, IndexError):
            self._append_plain(
                f"\n[Invalid login format for this world: {self.world.login_format!r}]\n"
            )
            return
        # Echoed locally with the password masked (matching Potato's
        # own real behavior: sendLoginInfoSub echoes a bullet-masked
        # copy while sending the real string to the server), but the
        # actual line sent to the server has the real password.
        masked = self.world.login_format.format(
            name=character.name, password="●" * len(character.password)
        )
        self._append_plain(masked + "\n")
        self.bridge.send_line(line)

    def _on_connection_closed(self) -> None:
        self._append_plain("\n[Connection closed by server]\n")
        self.input_line.setEnabled(False)
        self.secondary_input.setEnabled(False)
        self.connected_at = None
        self._set_connection_state("Disconnected")
        self.save_script_state()
        self._start_auto_reconnect()

    def _on_connection_failed(self, message: str) -> None:
        self._append_plain(f"\n[Connection failed: {message}]\n")
        self.input_line.setEnabled(False)
        self.secondary_input.setEnabled(False)
        self.connected_at = None
        self._set_connection_state("Disconnected")
        self.save_script_state()
        self._start_auto_reconnect()

    def _send_to_bridge(self, text: str, *, apply_aliases: bool) -> None:
        self._append_plain(text + "\n")
        if apply_aliases:
            # Off the GUI thread -- AliasEngine.expand() can call
            # run_with_timeout, same reasoning as incoming trigger
            # dispatch (see this module's docstring).
            self.bridge.run_in_background(lambda t=text: self._expand_alias_background(t))
        else:
            self.bridge.send_line(text)

    def _on_primary_send(self) -> None:
        text = self.input_line.text()
        self.input_line.clear()
        outcome = self._commands.process(text)
        if outcome.action == "send":
            self._send_to_bridge(outcome.text, apply_aliases=True)
        elif outcome.text:
            self._append_plain(outcome.text + "\n")

    def _on_secondary_send(self) -> None:
        # Always bypasses command processing entirely -- a pose
        # starting with "/" must never be silently reinterpreted.
        text = self.secondary_input.text()
        self.secondary_input.clear()
        self._send_to_bridge(text, apply_aliases=False)

    def spawn_log_window(self) -> SpawnWindow:
        """Pop a new window that live-mirrors this connection's
        incoming text from this point forward. Bound to this one tab
        specifically -- to log a different connection, spawn a
        separate log window from that connection's own tab.
        """
        window = SpawnWindow(f"MushTato — {self.name} — Log", parent=None, theme=self._theme)
        window.closed.connect(lambda: self._remove_spawn_window(window))
        self.spawn_windows.append(window)
        window.resize(500, 400)
        window.show()
        return window

    def _remove_spawn_window(self, window: SpawnWindow) -> None:
        if window in self.spawn_windows:
            self.spawn_windows.remove(window)

    def disconnect_bridge(self) -> None:
        # Explicitly cancels any pending auto-reconnect -- Disconnect
        # is the user's deliberate "stop trying" action, matching real
        # Potato's own behavior (verified against potato-skin.tcl,
        # where the Disconnect button is reused as "cancel reconnect"
        # while a retry is scheduled).
        self._stop_auto_reconnect()
        self.bridge.stop()
        self.input_line.setEnabled(False)
        self.secondary_input.setEnabled(False)
        self.connected_at = None
        self._set_connection_state("Disconnected")
        self._append_plain("\n[Disconnected]\n")
        self.save_script_state()

    def reconnect_bridge(self) -> None:
        # Calls stop() then start() on the *same* bridge instance --
        # TelnetBridge.start() spins up a fresh background thread/loop/
        # client each call, so the signal connections made once above
        # never need redoing.
        self.bridge.stop()
        self.input_line.setEnabled(True)
        self.secondary_input.setEnabled(True)
        self._set_connection_state("Connecting")
        self._append_plain(f"\nReconnecting to {self.host}:{self.port} ...\n")
        self.bridge.start()

    def shutdown(self) -> None:
        """Called by the host shell when this tab is being closed --
        stops the bridge, closes any spawn windows this tab owns, and
        persists this world's script variables one last time.
        """
        self._stop_auto_reconnect()
        self.bridge.stop()
        for spawn in list(self.spawn_windows):
            spawn.close()
        self.save_script_state()

    # -- built-in commands (Phase 7c, moved from MainWindow in Phase 7e) --
    # Every command calls the exact same method its GUI equivalent
    # already calls. /connect, /settings, /theme need the host shell;
    # they degrade to "not available" when host_window is None (only
    # happens in standalone tests, never in the real app).

    def _register_commands(self) -> None:
        # COMMAND_HELP (gui/help/topics.py) is the single source of
        # truth for names + help text -- this loop is what actually
        # wires each name to its real handler, so the registered set
        # and the documented set can never drift apart.
        handlers = {
            "help": self._cmd_help,
            "quit": self._cmd_quit,
            "spawnlog": self._cmd_spawnlog,
            "connect": self._cmd_connect,
            "settings": self._cmd_settings,
            "version": self._cmd_version,
            "theme": self._cmd_theme,
            "disconnect": self._cmd_disconnect,
            "reconnect": self._cmd_reconnect,
        }
        for name, help_text in COMMAND_HELP:
            self._commands.register(name, handlers[name], help_text)

    def _cmd_help(self, args: str) -> Optional[str]:
        name = args.strip().lower()

        if not name:
            if self.host_window is not None:
                self.host_window.show_help()
            topic_slugs = ", ".join(topic.slug for topic in TOPICS)
            command_names = ", ".join(f"/{n}" for n, _ in COMMAND_HELP)
            return (
                "Opening Help window.\n"
                f"Topics ('/help topics' for this list): {topic_slugs}\n"
                f"Commands: {command_names}\n"
                "Type /help [topic] or /help [command] for details on one."
            )

        if name == "topics":
            return "Help topics: " + ", ".join(topic.slug for topic in TOPICS)

        topic = get_topic(name)
        if topic is not None:
            context = HelpContext(
                hotkeys=self.host_window._hotkeys if self.host_window is not None else {},
                theme=self._theme,
            )
            return strip_markdown(topic.render(context))

        command_help = self._commands.command_help_text(name)
        if command_help is not None:
            return f"/{name} - {command_help}"

        return f"No such help topic or command: {name}"

    def _cmd_quit(self, args: str) -> Optional[str]:
        del args
        if self.host_window is not None:
            self.host_window.close_tab(self)
        return None

    def _cmd_spawnlog(self, args: str) -> Optional[str]:
        del args
        self.spawn_log_window()
        return "Spawned a log window."

    def _cmd_connect(self, args: str) -> Optional[str]:
        if self.host_window is None:
            return "Not available in this session (no host window)."
        name = args.strip()
        if not name:
            return "Usage: /connect [world-name]"
        return self.host_window.connect_by_name(name)

    def _cmd_settings(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        self.host_window.open_settings()
        return None

    def _cmd_version(self, args: str) -> Optional[str]:
        del args
        return f"MushTato {mushtato_version()}"

    def _cmd_theme(self, args: str) -> Optional[str]:
        theme = args.strip().lower()
        if theme not in ("dark", "light"):
            return "Usage: /theme [dark|light]"
        if self.host_window is None:
            return "Not available in this session (no host window)."
        return self.host_window.set_theme(theme)

    def _cmd_disconnect(self, args: str) -> Optional[str]:
        del args
        self.disconnect_bridge()
        return None

    def _cmd_reconnect(self, args: str) -> Optional[str]:
        del args
        self.reconnect_bridge()
        return None
