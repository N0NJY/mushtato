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

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import re2

from PySide6.QtCore import QDateTime, QTimer, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QInputDialog,
    QLineEdit,
    QSizePolicy,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from engine.ansi import DEFAULT_STYLE, Style, StyledSegment
from engine.commands import CommandTable
from engine.net import CertificateStore, HostKeyStore
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
    ssh_known_hosts_path,
    ssl_known_certs_path,
    world_script_path,
)

from ..fonts import resolve_input_font, resolve_scrollback_font
from ..help.markdown_tools import strip_markdown
from ..help.topics import COMMAND_HELP, HelpContext, TOPICS, get_topic
from ..theme import apply_scrollback_theme
from ..version import mushtato_version
from .find_bar import FindBar
from .history_line_edit import HistoryLineEdit
from .mail_window import MailWindow
from .spawn_window import SpawnWindow
from .ssh_bridge import SshBridge
from .styled_text_qt import append_styled_segments, replace_tail
from .telnet_bridge import TelnetBridge
from .upload_dialog import UploadDialog
from .upload_session import UploadSession

# "/ssh [-p PORT] user@host" -- both "-p 505" and squished "-p505" are
# accepted, matching common CLI ssh usage (real OpenSSH's own getopt
# parsing accepts both forms too). Port defaults to 22 (the standard
# SSH port) when omitted, exactly like real ssh.
_SSH_COMMAND_RE = re.compile(r"^\s*(?:-p\s*(?P<port>\d+)\s+)?(?P<user>[^@\s]+)@(?P<host>\S+)\s*$")

# "-c<char>:<pass>" -- one token, no spaces, matching how every other
# /addworld token is a single whitespace-separated word.
_ADDWORLD_CHARACTER_FLAG_RE = re.compile(r"^-c(?P<char>[^:\s]+):(?P<password>\S+)$")


def parse_addworld_command(
    args: str,
) -> Optional[Tuple[str, str, int, bool, Optional[Tuple[str, str]]]]:
    """Parse a typed ``/addworld [-x] [-c[char]:[pass]] [name] [host]
    [port]`` command's argument text into ``(name, host, port, use_ssl,
    character)`` -- ``character`` is ``(name, password)`` or ``None``.
    Returns ``None`` if the shape doesn't match at all (wrong number of
    positional tokens, a non-numeric port, or a malformed flag). A
    standalone, pure function (like parse_ssh_command above)
    specifically so it's directly unit-testable without constructing a
    whole SessionTab.

    Flags may appear anywhere among the tokens, not just before the
    positional args -- ``-x``/``-c...`` are recognized by shape and
    everything else is treated as positional, in order.
    """
    use_ssl = False
    character: Optional[Tuple[str, str]] = None
    positional: List[str] = []
    for token in args.split():
        if token == "-x":
            use_ssl = True
            continue
        match = _ADDWORLD_CHARACTER_FLAG_RE.match(token)
        if match:
            character = (match.group("char"), match.group("password"))
            continue
        positional.append(token)
    if len(positional) != 3:
        return None
    name, host, port_text = positional
    if not port_text.isdigit():
        return None
    return name, host, int(port_text), use_ssl, character


# "[-d<seconds>] <count>|i <command>" -- the delay flag (if present) must
# come first, unlike /addworld's flags -- <command> is free text and could
# itself start with something flag-shaped, so only a fixed flag position
# is unambiguous. "i"/"I" for <count> means "repeat indefinitely" (TF's
# own real /repeat has the identical "i" convention).
_REPEAT_RE = re.compile(
    r"^(?:-d(?P<delay>[0-9]*\.?[0-9]+)\s+)?(?P<count>[iI]|\d+)\s+(?P<command>\S.*)$"
)


def parse_repeat_command(args: str) -> Optional[Tuple[Optional[int], float, str]]:
    """Parse a typed ``/repeat [-d[seconds]] [count]|i [command]``
    command's argument text into ``(count, delay_seconds, command)`` --
    ``count`` is ``None`` for an indefinite ("i") repeat. Returns
    ``None`` if the shape doesn't match at all (no command text, a
    zero/malformed count). A standalone, pure function (like
    parse_ssh_command/parse_addworld_command above) specifically so
    it's directly unit-testable without constructing a whole
    SessionTab.
    """
    match = _REPEAT_RE.match(args)
    if match is None:
        return None
    count_text = match.group("count")
    count: Optional[int]
    if count_text.lower() == "i":
        count = None
    else:
        count = int(count_text)
        if count < 1:
            return None
    delay_seconds = float(match.group("delay")) if match.group("delay") else 0.0
    return count, delay_seconds, match.group("command")


def parse_ssh_command(args: str) -> Optional[Tuple[str, int, str]]:
    """Parse a typed ``/ssh`` command's argument text into
    ``(host, port, username)``, or ``None`` if it doesn't match the
    expected ``[-p PORT] user@host`` shape at all. A standalone, pure
    function (no Qt, no SessionTab instance needed) specifically so it
    can be unit-tested directly against its exact parsing rules.
    """
    match = _SSH_COMMAND_RE.match(args)
    if not match:
        return None
    port = int(match.group("port")) if match.group("port") else 22
    return match.group("host"), port, match.group("user")


def _split_input_lines(text: str) -> List[str]:
    """Split an input box's entire current content into individual
    lines to send, one call per Enter press -- matches real Potato's
    own ``send_mushage`` (grabs the whole box, splits on newline, sends
    each line separately, then clears the box), verified against its
    real source before writing this rather than assumed.

    A single trailing newline (routine when pasting a block copied
    elsewhere, which commonly ends with one) is not treated as its own
    extra blank line to send -- matches Potato's own real
    ``process_input`` loop, which naturally stops once the remaining
    text is empty rather than processing a dangling empty segment after
    the final real newline. A genuine *interior* blank line (a real
    blank line in the middle of a paste) is still sent as its own blank
    line, and a single Enter on a genuinely empty box still sends one
    blank line, exactly as before this feature existed -- neither case
    is "a trailing newline," so neither is stripped.
    """
    lines = text.split("\n")
    if len(lines) > 1 and lines[-1] == "":
        lines = lines[:-1]
    return lines


def _is_authentication_failure(message: str) -> bool:
    """True if ``message`` (as built by SshBridge's generic-exception
    handler, ``f"{type(exc).__name__}: {exc}"``) names asyncssh's real
    ``PermissionDenied`` exception -- i.e. bad credentials, not a
    network-level problem. A standalone function (like
    parse_ssh_command above) specifically so it's directly unit-
    testable without constructing a whole SessionTab.
    """
    return message.startswith("PermissionDenied")


class _RepeatProcess:
    """One active ``/repeat`` -- a small bundle of the command to fire,
    how many times (``None`` means indefinite), the delay between
    firings, and the QTimer driving it. Always a *singleShot* timer,
    rescheduled after every firing rather than a repeating interval
    timer -- even with a 0-second delay, this still yields to the Qt
    event loop between sends (via ``QTimer.start(0)``, not a tight
    synchronous loop), which is what makes an indefinite repeat
    actually stoppable by ``/stoprepeat`` rather than freezing the GUI
    forever once started.
    """

    def __init__(self, repeat_id: int, command: str, total_count: Optional[int], delay_seconds: float) -> None:
        self.id = repeat_id
        self.command = command
        self.total_count = total_count
        self.remaining = total_count
        self.delay_seconds = delay_seconds
        self.timer = QTimer()
        self.timer.setSingleShot(True)


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
        host: str = "",
        port: int = 0,
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
        logs_dir_override=None,  # Phase 11: passed straight through to each spawn window; see spawn_log_window()
        upload_last_dir: str = "",  # shared "next Upload dialog's starting directory" preference
        host_key_store: Optional[HostKeyStore] = None,  # for /ssh and /ssh-forget; see _host_key_store()
        cert_store: Optional[CertificateStore] = None,  # for SSL and /ssl-forget; see _cert_store()
    ) -> None:
        super().__init__()
        # host=="" is a "blank tab" -- no bridge yet, established later by
        # a typed /connect <host> <port> or /ssh command (see
        # _connect_telnet/_connect_ssh below). Every pre-existing caller
        # (MainWindow.open_tab, every test) always passes a real host, so
        # this default only ever activates via the new open_blank_tab().
        self.host = host
        self.port = port
        # Falls back to world.name before host:port -- every real call
        # site (AddressBookWindow) already passes name=world.name
        # explicitly too, but this closes off the same gap for any
        # caller that doesn't remember to: whenever a world is known,
        # its own address-book name should always win over a bare
        # host:port, not just when a caller happens to also pass it
        # separately.
        self.name = name or (world.name if world is not None else None) or (
            f"{host}:{port}" if host else "New Tab"
        )
        # Set once a Character login line actually fires (_send_autosends
        # -> _set_character_name) -- empty for a tab with no resolved
        # Character (no default_character, no explicit Log In as choice,
        # or an SSH/blank tab, none of which have a MU* Character
        # concept at all). Deliberately never cleared on disconnect --
        # auto-reconnect commonly succeeds again with the same Character
        # moments later, and flickering the tab label off and back on
        # for that would be more distracting than useful.
        self.character_name: str = ""
        self.host_window = host_window
        self.world = world
        self._script_store_path_override = script_store_path
        self._logs_dir_override = logs_dir_override
        self._host_key_store_override = host_key_store
        self._explicit_character = character
        self._cert_store_override = cert_store
        self._theme = theme if theme is not None else DEFAULT_THEME
        self.connected_at: Optional[QDateTime] = None
        # Per-tab, never persisted (checkpointed 2026-07-27: always starts
        # off) -- see _prefix_with_timestamp/set_show_timestamps below.
        self.show_timestamps: bool = False
        self.bridge = None  # set below (blank tab) or by _start_bridge (connected)
        self.connection_state = "Connecting" if host else "Disconnected"
        self.spawn_windows: List[SpawnWindow] = []
        # One per tab, not a list like spawn_windows -- matches Potato's
        # real .mailWindow$c behavior (opening a second re-shows the
        # existing one), a deliberate difference from the Text Editor's
        # unlimited-simultaneous-windows precedent (Phase 12b checkpoint).
        self.mail_window: Optional[MailWindow] = None
        # One per tab, same reasoning as mail_window above -- matches
        # Potato's real "already uploading -> show progress instead of
        # a new file picker" behavior (uploadWindow's dispatcher).
        self.upload_session: Optional[UploadSession] = None
        self._upload_last_dir = upload_last_dir
        # Item 11 (2026-07-28): /repeat processes, tab-scoped (per the
        # checkpoint decision) -- matches every other per-connection
        # resource on this tab (upload_session, mail_window) rather than
        # a single app-wide registry. Keyed by a small per-tab integer
        # id (TF's own real /repeat also returns/uses a numeric id, its
        # "pid"), not reused after a repeat finishes/is stopped.
        self._repeat_processes: Dict[int, _RepeatProcess] = {}
        self._next_repeat_id = 1
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
        # only one that checks for built-in "/" commands (Phase 7c) and
        # applies alias expansion (`_process_typed_line` ->
        # `_send_to_bridge(apply_aliases=True)` -> `AliasEngine.expand()`).
        # `secondary_input` is for longer free-form text (poses/says); it
        # bypasses *both* -- a pose starting with "/" or a word that
        # happens to match an alias must never be silently reinterpreted,
        # same reasoning for both. Both boxes are multi-line-capable
        # (HistoryLineEdit, Potato-parity multi-line paste -- see that
        # module's own docstring) -- on Return, whichever box's
        # `_on_primary_send`/`_on_secondary_send` handler fires splits
        # the box's *entire* current content into individual lines
        # (`_split_input_lines`) and runs each one through the exact
        # same per-line pipeline a single typed line already used,
        # matching real Potato's own send_mushage exactly (grab the
        # whole box, split on newline, send each line separately, then
        # clear the box) rather than a parallel multi-line-specific path.
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
        # Persisted per-world when this tab has one (post-1.1.0), or
        # globally as a fallback for a world-less tab -- so the *next*
        # tab you open for the same world (or, world-less, any tab) --
        # this session or a future one -- starts at whatever height you
        # last dragged to. Deliberately does NOT resize already-open
        # tabs live when another tab is dragged; see
        # MainWindow.record_splitter_sizes's docstring.
        self.splitter.splitterMoved.connect(self._on_splitter_moved)
        # Debounces the per-world save specifically (see
        # _on_splitter_moved) -- that path does a full address-book
        # reload/save, much more expensive than the world-less path's
        # in-memory-only MainWindow.record_splitter_sizes, which has its
        # own separate debounce timer already.
        self._splitter_save_timer = QTimer(self)
        self._splitter_save_timer.setSingleShot(True)
        self._splitter_save_timer.setInterval(400)
        self._splitter_save_timer.timeout.connect(self._save_splitter_sizes_for_world_now)

        # Phase 11: hidden by default, toggled via Ctrl+F/Edit > Find...
        # (MainWindow) or /find. Operates on this tab's own scrollback
        # specifically -- each tab searches its own content.
        self.find_bar = FindBar(self.scrollback, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.find_bar)
        layout.addWidget(self.splitter)

        apply_scrollback_theme(self.scrollback, self._theme)

        self._commands = CommandTable()
        self._register_commands()

        # -- Phase 9: scripting --------------------------------------
        # Unconditional, even for a world with zero saved scripts --
        # one uniform pipeline for every tab, no "scripting active or
        # not" branch. send() is a lazy closure (self.bridge may not
        # exist yet -- either this hasn't reached bridge construction
        # below, or this is a still-blank tab with no bridge at all).
        self.script_world = ScriptWorld(
            send=lambda text: self.bridge.send_line(text) if self.bridge is not None else None,
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
        # runtime path just omits this argument.
        if host:
            default_bridge = bridge if bridge is not None else TelnetBridge(
                host,
                port,
                nop_keepalive=world.nop_keepalive if world is not None else False,
                use_ssl=world.use_ssl if world is not None else False,
                cert_store=self._cert_store(),
                naws_enabled=world.telnet_naws if world is not None else False,
                term_enabled=world.telnet_term if world is not None else False,
                host2=world.host2 if world is not None else "",
                port2=world.port2 if world is not None else 0,
                use_ssl2=world.use_ssl2 if world is not None else False,
                proxy_host=world.proxy_host if world is not None else "",
                proxy_port=world.proxy_port if world is not None else 0,
            )
            self._start_bridge(default_bridge, host, port, f"Connecting to {host}:{port} ...\n")
        else:
            self._append_plain(
                "[Blank tab. Type /connect <host> <port>, or "
                "/ssh [-p port] user@host, to begin.]\n"
            )

    def _host_key_store(self) -> HostKeyStore:
        """Resolves to the real per-user known-hosts file (engine/
        storage/paths.ssh_known_hosts_path) unless a test explicitly
        overrode it at construction -- the same dependency-injection
        pattern _script_store_path() already uses, so tests never touch
        the real user data directory just by exercising /ssh.
        """
        if self._host_key_store_override is not None:
            return self._host_key_store_override
        return HostKeyStore(ssh_known_hosts_path())

    def _cert_store(self) -> CertificateStore:
        """Resolves to the real per-user SSL certificate store (engine/
        storage/paths.ssl_known_certs_path) unless a test explicitly
        overrode it at construction -- identical dependency-injection
        pattern to _host_key_store() above.
        """
        if self._cert_store_override is not None:
            return self._cert_store_override
        return CertificateStore(ssl_known_certs_path())

    def _start_bridge(self, bridge, host: str, port: int, connecting_message: str) -> None:
        """Wire up and start ``bridge`` (a TelnetBridge or SshBridge --
        anything implementing the same start/send_line/stop/
        set_on_text + connected/connectionClosed/connectionFailed
        contract) as this tab's active connection. Called from
        __init__ for the normal (non-blank) construction path, and
        from _connect_telnet/_connect_ssh when a previously-blank tab
        establishes its first connection.
        """
        self.bridge = bridge
        self.host = host
        self.port = port
        self.bridge.set_on_text(self._on_raw_incoming_text)
        self.bridge.connected.connect(self._on_connected)
        self.bridge.connectionClosed.connect(self._on_connection_closed)
        self.bridge.connectionFailed.connect(self._on_connection_failed)

        self._append_plain(connecting_message)
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
        if self.host_window is None:
            return
        if self.world is not None:
            # Debounced on this tab's own timer, not called directly --
            # this path does a full address-book reload/save, which
            # must not happen on every raw pixel of a drag.
            self._splitter_save_timer.start()
        else:
            self.host_window.record_splitter_sizes(self.splitter.sizes())

    def _save_splitter_sizes_for_world_now(self) -> None:
        if self.host_window is not None and self.world is not None:
            self.host_window.save_splitter_sizes_for_world(self.world, self.splitter.sizes())

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
                segments = self._prefix_with_timestamp(finalized.segments)
                self._insert_finalized_segments(segments, restore_preview=False)
                for spawn in self.spawn_windows:
                    spawn.receive_segments(segments)
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

    # -- Timestamps (checkpointed 2026-07-27): a per-tab, non-persisted
    # toggle. Every *finalized* line (real server text and script echo()
    # output alike -- both funnel through _insert_finalized_segments)
    # gets a compact "[HH:mm:ss] " prefix when enabled; the still-
    # updating "preview" of an incomplete trailing line deliberately
    # does NOT get one, since it's re-rendered repeatedly as more of the
    # same not-yet-finished line arrives and isn't a real, settled event
    # yet. Toggling itself inserts a full-date marker line (see
    # set_show_timestamps) rather than silently starting/stopping --
    # Rick's own explicit ask, so a saved log's compact per-line times
    # can still be pinned to a real calendar date.

    def _timestamp_prefix_segment(self) -> StyledSegment:
        now = QDateTime.currentDateTime().toString("HH:mm:ss")
        return StyledSegment(f"[{now}] ", DEFAULT_STYLE)

    def _prefix_with_timestamp(self, segments: List[StyledSegment]) -> List[StyledSegment]:
        if not self.show_timestamps:
            return segments
        return [self._timestamp_prefix_segment()] + list(segments)

    def set_show_timestamps(self, enabled: bool) -> None:
        """Toggles per-line timestamps for this tab -- reused identically
        by MainWindow's View menu action and the /timestamps command, not
        a parallel implementation of either. A no-op if already in the
        requested state, so an incidental duplicate call (e.g. re-
        syncing the menu checkbox) can never double-announce.
        """
        if enabled == self.show_timestamps:
            return
        self.show_timestamps = enabled
        # The status bar clock (MainWindow._update_clock) already
        # established this exact "dd/MM/yyyy - HH:mm:ss" display format
        # -- reused here rather than inventing a second one. Inserted via
        # _append_plain_raw, not _append_plain, so this marker line is
        # never itself also prefixed with the compact per-line time --
        # it already carries a full date/time inline.
        now = QDateTime.currentDateTime().toString("dd/MM/yyyy - HH:mm:ss")
        state = "enabled" if enabled else "disabled"
        self._append_plain_raw(f"[Timestamps {state} -- {now}]\n")

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
        segments = self._prefix_with_timestamp([StyledSegment(text + "\n", seg_style)])
        self._insert_finalized_segments(segments)
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
        """Inserts a MushTato-originated system notice (connect/
        disconnect/error messages) -- also timestamped when enabled
        (checkpointed 2026-07-27), same as real server text. A leading
        run of newlines (several call sites use "\\n[...]\\n" to force a
        blank line before a notice) is preserved *before* the timestamp
        prefix rather than after it, so the visible bracketed message
        still reads "[HH:mm:ss] [...]" on its own line, not a stray
        timestamped blank line followed by the real message.
        """
        if self.show_timestamps:
            leading_newlines = ""
            rest = text
            while rest.startswith("\n"):
                leading_newlines += "\n"
                rest = rest[1:]
            now = QDateTime.currentDateTime().toString("HH:mm:ss")
            text = f"{leading_newlines}[{now}] {rest}"
        self._append_plain_raw(text)

    def _append_plain_raw(self, text: str) -> None:
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
        if self.world.protocol != "telnet":
            # Auto-sends/character-login are MU*-specific raw softcode
            # login lines -- meaningless (and actively confusing) typed
            # into a real SSH shell session, so they're skipped entirely
            # for a non-Telnet world. connect_count is still tracked
            # above regardless of protocol -- that's just a connection
            # tally, not MU*-specific.
            return
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
            self._set_character_name(character.name)
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

    def _tab_label(self) -> str:
        """The tab bar's label for this tab -- ``name`` alone, or
        ``name`` plus a second line naming the logged-in Character once
        one's known. Rendered as two real lines by
        ``gui.windows.two_line_tab_bar.TwoLineTabBar`` (plain QTabBar
        text with an embedded newline doesn't grow tab height to fit a
        second line, confirmed directly -- see that module).
        """
        if self.character_name:
            return f"{self.name}\n{self.character_name}"
        return self.name

    def _set_character_name(self, name: str) -> None:
        if self.character_name != name:
            self.character_name = name
            self.titleChanged.emit(self._tab_label())

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

    def _cancel_upload_if_running(self) -> None:
        # A dropped/closed connection would otherwise let an in-flight
        # UploadSession keep "sending" into a bridge whose send_line()
        # silently no-ops once stopped -- the progress window would
        # reach 100% and report success despite nothing after the drop
        # ever reaching the server. Cancelling here makes that failure
        # visible instead of silently swallowed.
        if self.upload_session is not None:
            self.upload_session.cancel()

    def _cancel_all_repeats(self) -> None:
        # Same reasoning as _cancel_upload_if_running above, and the
        # same checkpointed answer (2026-07-28): a /repeat whose tab
        # has closed or disconnected has nowhere left to send to --
        # leaving it running would silently no-op every firing (the
        # same failure class Upload's own cancel-on-disconnect fix
        # exists to prevent) rather than making the stop visible.
        for process in list(self._repeat_processes.values()):
            process.timer.stop()
        self._repeat_processes.clear()

    def _fire_repeat(self, repeat_id: int) -> None:
        process = self._repeat_processes.get(repeat_id)
        if process is None:
            return  # already stopped via /stoprepeat, or cancelled
        self._process_typed_line(process.command)
        if process.total_count is not None:
            process.remaining -= 1
            if process.remaining <= 0:
                del self._repeat_processes[repeat_id]
                self._append_plain(f"[/repeat #{repeat_id} finished]\n")
                return
        process.timer.start(int(process.delay_seconds * 1000))

    def _on_connection_closed(self) -> None:
        self._append_plain("\n[Connection closed by server]\n")
        self.input_line.setEnabled(False)
        self.secondary_input.setEnabled(False)
        self.connected_at = None
        self._set_connection_state("Disconnected")
        self._cancel_upload_if_running()
        self._cancel_all_repeats()
        self.save_script_state()
        self._start_auto_reconnect()

    def _on_connection_failed(self, message: str) -> None:
        self._append_plain(f"\n[Connection failed: {message}]\n")
        self.input_line.setEnabled(False)
        self.secondary_input.setEnabled(False)
        self.connected_at = None
        self._set_connection_state("Disconnected")
        self._cancel_upload_if_running()
        self._cancel_all_repeats()
        self.save_script_state()
        if _is_authentication_failure(message):
            # Retrying with the exact same (bad) credentials every 30s,
            # forever, can never succeed -- unlike a genuine dropped
            # network connection, which auto-reconnect exists for.
            # Confirmed as real, real-world behavior (not hypothetical)
            # by deliberately testing a wrong SSH password: it looped
            # indefinitely until manually disconnected. Rick's explicit
            # checkpoint choice: don't auto-reconnect in this one case.
            self._append_plain(
                "[Not retrying automatically -- this looks like a login/"
                "authentication failure, and the same credentials would "
                "only fail again. Reconnect manually (or /ssh again with "
                "the right password) once that's sorted.]\n"
            )
            return
        self._start_auto_reconnect()

    def _send_to_bridge(self, text: str, *, apply_aliases: bool) -> None:
        if self.bridge is None:
            self._append_plain(
                "[Not connected. Use /connect <host> <port> or /ssh [-p port] user@host.]\n"
            )
            return
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
        for line in _split_input_lines(text):
            self._process_typed_line(line)

    def _process_typed_line(self, text: str) -> None:
        # Factored out of _on_primary_send (Item 11) so a /repeat's
        # scheduled firing goes through the *exact same* command/alias/
        # send pipeline a manually-typed line in the primary input box
        # already does -- a repeated command can itself be a "/"
        # command, not just plain server-bound text.
        outcome = self._commands.process(text)
        if outcome.action == "send":
            self._send_to_bridge(outcome.text, apply_aliases=True)
        elif outcome.text:
            self._append_plain(outcome.text + "\n")

    def _on_secondary_send(self) -> None:
        # Always bypasses command processing entirely -- a pose
        # starting with "/" must never be silently reinterpreted, for
        # every line of a multi-line paste, not just the first.
        text = self.secondary_input.text()
        self.secondary_input.clear()
        for line in _split_input_lines(text):
            self._send_to_bridge(line, apply_aliases=False)

    def toggle_find_bar(self) -> None:
        """Show the find bar (focused, ready to type) if hidden, or
        hide it (clearing highlights) if already shown -- the same
        toggle behavior Ctrl+F conventionally has in text editors/
        browsers.

        Checks ``isHidden()``, not ``isVisible()`` -- a real bug caught
        by a headless test, not just a style preference:
        ``isVisible()`` depends on the *entire* ancestor chain actually
        being on-screen, which is false whenever this tab isn't the
        QTabWidget's current tab (its page is hidden by the tab widget
        itself). Using it here would have made toggling on a
        background tab always re-open instead of closing an
        already-open find bar. ``isHidden()`` reflects only this
        widget's own explicit shown/hidden state, independent of
        whether an ancestor happens to be on-screen right now.
        """
        if self.find_bar.isHidden():
            self.find_bar.open_bar()
        else:
            self.find_bar.close_bar()

    def spawn_log_window(self) -> SpawnWindow:
        """Pop a new window that live-mirrors this connection's
        incoming text from this point forward. Bound to this one tab
        specifically -- to log a different connection, spawn a
        separate log window from that connection's own tab.
        """
        window = SpawnWindow(
            f"MushTato — {self.name} — Log",
            parent=None,
            theme=self._theme,
            logs_dir_override=self._logs_dir_override,
        )
        window.closed.connect(lambda: self._remove_spawn_window(window))
        self.spawn_windows.append(window)
        window.resize(500, 400)
        window.show()
        return window

    def _remove_spawn_window(self, window: SpawnWindow) -> None:
        if window in self.spawn_windows:
            self.spawn_windows.remove(window)

    def open_mail_window(self) -> MailWindow:
        """Open this tab's compose/send mail window -- one per tab
        (Potato's real ``.mailWindow$c`` behavior), not a new window
        every call: re-shows the existing one if already open, rather
        than opening a second.
        """
        if self.mail_window is not None:
            self.mail_window.show()
            self.mail_window.raise_()
            self.mail_window.activateWindow()
            return self.mail_window

        window = MailWindow(
            self.world,
            lambda text: self._send_to_bridge(text, apply_aliases=False),
            persist_world=self._persist_mail_settings,
        )
        window.closed.connect(self._on_mail_window_closed)
        self.mail_window = window
        window.show()
        return window

    def _on_mail_window_closed(self) -> None:
        self.mail_window = None

    def _persist_mail_settings(self, world: WorldProfile) -> None:
        if self.host_window is not None:
            self.host_window.save_mail_settings_for_world(world)

    def open_upload_dialog(self) -> None:
        """Open the Upload file-picker/options dialog -- or, if an
        upload is already running on this tab, just show its progress
        window instead, matching Potato's real ``uploadWindow``
        dispatcher (only one upload in flight per connection at a
        time).
        """
        if self.upload_session is not None:
            self.upload_session.show_progress_window()
            return
        if self.connection_state != "Connected":
            self._append_plain("[Not connected.]\n")
            return

        dialog = UploadDialog(self, initial_dir=self._upload_last_dir)
        if not dialog.exec():
            return

        filepath = dialog.selected_file()
        try:
            text = Path(filepath).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self._append_plain(f'[Unable to open file "{filepath}": {exc}]\n')
            return

        self._upload_last_dir = dialog.selected_directory()
        if self.host_window is not None:
            self.host_window.record_upload_last_dir(self._upload_last_dir)

        self._append_plain(f'[Uploading file "{filepath}"...]\n')
        session = UploadSession(
            filepath,
            text.splitlines(),
            dialog.options(),
            send_line=lambda t: self._send_to_bridge(t, apply_aliases=False),
            add_to_history=self.input_line.remember,
            parent=self,
        )
        session.finished.connect(self._on_upload_finished)
        self.upload_session = session
        session.start()
        session.show_progress_window()

    def _on_upload_finished(self, completed: bool) -> None:
        if self.upload_session is not None:
            file_name = Path(self.upload_session.file_path).name
            if completed:
                self._append_plain(f'[Upload of "{file_name}" complete.]\n')
            else:
                self._append_plain(f'[Upload of "{file_name}" cancelled.]\n')
        self.upload_session = None

    def disconnect_bridge(self) -> None:
        # Explicitly cancels any pending auto-reconnect -- Disconnect
        # is the user's deliberate "stop trying" action, matching real
        # Potato's own behavior (verified against potato-skin.tcl,
        # where the Disconnect button is reused as "cancel reconnect"
        # while a retry is scheduled).
        if self.bridge is None:
            self._append_plain("[Not connected.]\n")
            return
        self._stop_auto_reconnect()
        self._cancel_upload_if_running()
        self._cancel_all_repeats()
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
        if self.bridge is None:
            self._append_plain(
                "[Nothing to reconnect -- use /connect <host> <port> or "
                "/ssh [-p port] user@host first.]\n"
            )
            return
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
        self._cancel_upload_if_running()
        self._cancel_all_repeats()
        if self.bridge is not None:
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
            "editor": self._cmd_editor,
            "mail": self._cmd_mail,
            "upload": self._cmd_upload,
            "ssh": self._cmd_ssh,
            "ssh-forget": self._cmd_ssh_forget,
            "ssl-forget": self._cmd_ssl_forget,
            "timestamps": self._cmd_timestamps,
            "newtab": self._cmd_newtab,
            "addressbook": self._cmd_addressbook,
            "exit": self._cmd_exit,
            "errorlog": self._cmd_errorlog,
            "about": self._cmd_about,
            "cut": self._cmd_cut,
            "copy": self._cmd_copy,
            "paste": self._cmd_paste,
            "undo": self._cmd_undo,
            "redo": self._cmd_redo,
            "selectall": self._cmd_selectall,
            "find": self._cmd_find,
            "addworld": self._cmd_addworld,
            "worlds": self._cmd_worlds,
            "tabs": self._cmd_tabs,
            "vars": self._cmd_vars,
            "recall": self._cmd_recall,
            "repeat": self._cmd_repeat,
            "repeats": self._cmd_repeats,
            "stoprepeat": self._cmd_stoprepeat,
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
        tokens = args.split()
        # A blank tab's raw "host port" form -- distinguished from a
        # saved-world-name lookup by shape (exactly two tokens, the
        # second numeric), not by connection state, so it also works
        # to open a genuinely new connection on an already-blank tab
        # regardless of whether a host_window exists.
        if len(tokens) == 2 and tokens[1].isdigit():
            if self.bridge is not None:
                return "This tab is already connected."
            self._connect_telnet(tokens[0], int(tokens[1]))
            return None
        if self.host_window is None:
            return "Not available in this session (no host window)."
        name = args.strip()
        if not name:
            return "Usage: /connect <world-name>  or  /connect <host> <port>"
        return self.host_window.connect_by_name(name)

    def _connect_telnet(self, host: str, port: int) -> None:
        """Establishes this (previously blank) tab's Telnet connection
        -- the raw "/connect host port" counterpart to the address
        book's Connect button, for a tab with no saved world at all.
        """
        self.name = f"{host}:{port}"
        self.titleChanged.emit(self._tab_label())
        self._start_bridge(TelnetBridge(host, port), host, port, f"Connecting to {host}:{port} ...\n")

    def _cmd_ssh(self, args: str) -> Optional[str]:
        if self.bridge is not None:
            return "This tab is already connected."
        parsed = parse_ssh_command(args)
        if parsed is None:
            return "Usage: /ssh [-p port] user@host"
        host, port, username = parsed
        password, ok = QInputDialog.getText(
            self,
            "SSH Password",
            f"Password for {username}@{host}:{port}:",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return "SSH connect cancelled."
        self._connect_ssh(host, port, username, password)
        return None

    def _connect_ssh(self, host: str, port: int, username: str, password: str) -> None:
        self.name = f"{username}@{host}"
        self.titleChanged.emit(self._tab_label())
        bridge = SshBridge(host, port, username, password, self._host_key_store())
        self._start_bridge(
            bridge, host, port, f"Connecting via SSH to {username}@{host}:{port} ...\n"
        )

    def _cmd_ssh_forget(self, args: str) -> Optional[str]:
        target = args.strip()
        if not target:
            return "Usage: /ssh-forget <host>[:port]"
        if ":" in target:
            host, _, port_text = target.rpartition(":")
            if not port_text.isdigit():
                return f"Invalid port in {target!r}."
            port = int(port_text)
        else:
            host, port = target, 22
        if self._host_key_store().forget(host, port):
            return (
                f"Forgot the saved host key for {host}:{port}. "
                "The next connect will trust whatever key the server offers."
            )
        return f"No saved host key found for {host}:{port}."

    def _cmd_ssl_forget(self, args: str) -> Optional[str]:
        target = args.strip()
        # Unlike /ssh-forget, there's no universal default port to fall
        # back to here (SSH conventionally runs on 22; MU*s run on all
        # sorts of ports) -- host:port is required explicitly.
        if ":" not in target:
            return "Usage: /ssl-forget <host>:<port>"
        host, _, port_text = target.rpartition(":")
        if not host or not port_text.isdigit():
            return "Usage: /ssl-forget <host>:<port>"
        port = int(port_text)
        if self._cert_store().forget(host, port):
            return (
                f"Forgot the saved certificate for {host}:{port}. "
                "The next connect will trust whatever certificate the server offers."
            )
        return f"No saved certificate found for {host}:{port}."

    def _cmd_settings(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        self.host_window.open_settings()
        return None

    def _cmd_editor(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        self.host_window.open_text_editor()
        return "Opened a new Text Editor window."

    def _cmd_mail(self, args: str) -> Optional[str]:
        # Tab-scoped, like /spawnlog -- doesn't need host_window at all
        # (Mail Window is owned by this tab directly, one per tab).
        del args
        self.open_mail_window()
        return "Opened the Mail Window."

    def _cmd_upload(self, args: str) -> Optional[str]:
        # Tab-scoped, like /spawnlog and /mail -- doesn't need
        # host_window (owned by this tab directly, one per tab).
        del args
        self.open_upload_dialog()
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

    def _cmd_timestamps(self, args: str) -> Optional[str]:
        value = args.strip().lower()
        if value not in ("on", "off"):
            return "Usage: /timestamps [on|off]"
        self.set_show_timestamps(value == "on")
        return None

    def _cmd_disconnect(self, args: str) -> Optional[str]:
        del args
        self.disconnect_bridge()
        return None

    def _cmd_reconnect(self, args: str) -> Optional[str]:
        del args
        self.reconnect_bridge()
        return None

    # -- Item 10 (2026-07-28): dual-access commands for every GUI menu
    # action that had none yet, plus Address Book quick-add/listing,
    # tab/session introspection, and scrollback recall. Every command
    # below with a GUI equivalent calls the exact same MainWindow method
    # its menu item/hotkey already calls -- never a parallel
    # implementation, same principle as every command above.

    def _cmd_newtab(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        self.host_window.open_blank_tab()
        return "Opened a new blank tab."

    def _cmd_addressbook(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        self.host_window._show_address_book()
        return None

    def _cmd_exit(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        self.host_window._exit_application()
        return None

    def _cmd_errorlog(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        self.host_window.show_error_log()
        return None

    def _cmd_about(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        self.host_window._show_about()
        return None

    # Cut/Copy/Paste/Undo/Redo/Select All: dispatched by MainWindow's
    # existing _dispatch_focused_edit_action, exactly like the Edit
    # menu's own items -- these act on whatever currently has keyboard
    # focus, which in practice is usually the input line the command
    # was just typed into (see the Edit Menu help topic).

    def _cmd_cut(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        self.host_window._dispatch_focused_edit_action("cut")
        return None

    def _cmd_copy(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        self.host_window._dispatch_focused_edit_action("copy")
        return None

    def _cmd_paste(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        self.host_window._dispatch_focused_edit_action("paste")
        return None

    def _cmd_undo(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        self.host_window._dispatch_focused_edit_action("undo")
        return None

    def _cmd_redo(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        self.host_window._dispatch_focused_edit_action("redo")
        return None

    def _cmd_selectall(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        self.host_window._dispatch_focused_edit_action("selectAll")
        return None

    def _cmd_find(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        self.host_window._toggle_find_on_current_tab()
        return None

    def _cmd_addworld(self, args: str) -> Optional[str]:
        if self.host_window is None:
            return "Not available in this session (no host window)."
        parsed = parse_addworld_command(args)
        if parsed is None:
            return "Usage: /addworld [-x] [-c[char]:[pass]] [name] [host] [port]"
        name, host, port, use_ssl, character = parsed
        characters: List[CharacterProfile] = []
        default_character = ""
        if character is not None:
            char_name, char_password = character
            characters.append(CharacterProfile(name=char_name, password=char_password))
            default_character = char_name
        profile = WorldProfile(
            name=name,
            host=host,
            port=port,
            use_ssl=use_ssl,
            characters=characters,
            default_character=default_character,
        )
        return self.host_window.add_world_to_address_book(profile)

    def _cmd_worlds(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        return self.host_window.worlds_summary_text()

    def _cmd_tabs(self, args: str) -> Optional[str]:
        del args
        if self.host_window is None:
            return "Not available in this session (no host window)."
        tab_widget = self.host_window.tab_widget
        lines = []
        for index in range(tab_widget.count()):
            tab = tab_widget.widget(index)
            marker = "*" if tab is self else " "
            address = f"{tab.host}:{tab.port}" if tab.host else "(blank, not connected)"
            lines.append(f"{marker} {tab.name} -- {address} -- {tab.connection_state}")
        if not lines:
            return "No tabs open."
        return "Open tabs ('*' marks this one):\n" + "\n".join(lines)

    def _cmd_vars(self, args: str) -> Optional[str]:
        del args
        variables = self.script_world.variables
        if not variables:
            return "No script variables set on this tab."
        lines = [f"{name} = {value!r}" for name, value in sorted(variables.items())]
        return "Script variables on this tab:\n" + "\n".join(lines)

    def _cmd_recall(self, args: str) -> Optional[str]:
        pattern = args.strip()
        if not pattern:
            return "Usage: /recall [pattern]"
        try:
            compiled = re2.compile(pattern)
        except re2.error as exc:
            return f"Invalid pattern: {exc}"
        matches = [
            line for line in self.scrollback.toPlainText().split("\n") if compiled.search(line)
        ]
        if not matches:
            return f"No lines matched: {pattern}"
        self._append_plain(f"--- /recall {pattern} ({len(matches)} match(es)) ---")
        for line in matches:
            self._append_plain(line)
        return None

    # -- Item 11 (2026-07-28): /repeat and its /repeats/`/stoprepeat
    # companions -- a background, cancelable, tab-scoped repeat-process
    # mechanism, modeled loosely on TinyFugue's real /repeat/`/ps`/`/kill`
    # trio (see tf-help's "processes" topic) but scoped down to this
    # project's own naming convention (plain nouns, matching /tabs/
    # /worlds/vars rather than TF's Unix-y "/ps"/"/kill"). Each fired
    # repetition goes through _process_typed_line -- the exact same
    # command/alias/send pipeline manually typing a line into the
    # primary input box already uses, so a repeated <command> can
    # itself be a "/" command, not only plain server-bound text.

    def _cmd_repeat(self, args: str) -> Optional[str]:
        parsed = parse_repeat_command(args)
        if parsed is None:
            return "Usage: /repeat [-d[seconds]] [count]|i [command]"
        count, delay_seconds, command = parsed
        repeat_id = self._next_repeat_id
        self._next_repeat_id += 1
        process = _RepeatProcess(repeat_id, command, count, delay_seconds)
        process.timer.timeout.connect(lambda rid=repeat_id: self._fire_repeat(rid))
        self._repeat_processes[repeat_id] = process
        # The first firing happens immediately, not after the first
        # delay -- a deliberate simplification of TF's own real default
        # (which delays the first run too, unless its separate -n flag
        # is given); "repeat this now, N times" is the more expected
        # v1 behavior and needed no second flag to get there.
        self._fire_repeat(repeat_id)
        return None

    def _cmd_repeats(self, args: str) -> Optional[str]:
        del args
        if not self._repeat_processes:
            return "No active /repeat processes on this tab."
        lines = []
        for repeat_id, process in sorted(self._repeat_processes.items()):
            remaining = (
                "indefinite"
                if process.total_count is None
                else f"{process.remaining}/{process.total_count}"
            )
            lines.append(
                f"#{repeat_id} -- {remaining} remaining, every {process.delay_seconds}s -- {process.command}"
            )
        return "Active /repeat processes:\n" + "\n".join(lines)

    def _cmd_stoprepeat(self, args: str) -> Optional[str]:
        text = args.strip()
        if not text.isdigit():
            return "Usage: /stoprepeat [id]"
        repeat_id = int(text)
        process = self._repeat_processes.pop(repeat_id, None)
        if process is None:
            return f"No such /repeat process: #{repeat_id}"
        process.timer.stop()
        return f"Stopped /repeat #{repeat_id}."
