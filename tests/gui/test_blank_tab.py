"""Headless tests for SessionTab's blank/unconnected initial state and
the /connect <host> <port>, /ssh, and /ssh-forget commands built on top
of it -- the "open blank tab, type a connection" workflow.

Real TelnetBridge/SshBridge construction is monkeypatched to return a
FakeBridge for these tests -- the point here is proving the blank-tab
state machine and command parsing/dispatch wire up correctly, not
re-proving real networking (already covered by
test_telnet_bridge_integration.py / test_ssh_bridge_integration.py and
test_ssh_client.py).
"""

from pathlib import Path

import gui.windows.session_tab as session_tab_module
from engine.net import HostKeyStore
from gui.windows.session_tab import SessionTab, _is_authentication_failure, parse_ssh_command
from tests.gui.test_main_window_smoke import FakeBridge


def make_blank_tab(**kwargs) -> SessionTab:
    return SessionTab(host_window=None, **kwargs)


# -- parse_ssh_command (pure, no Qt needed) ------------------------------


def test_parse_ssh_command_with_explicit_port():
    assert parse_ssh_command("-p 505 rickn0njy@silvren.com") == (
        "silvren.com",
        505,
        "rickn0njy",
    )


def test_parse_ssh_command_with_squished_port():
    assert parse_ssh_command("-p505 rickn0njy@silvren.com") == (
        "silvren.com",
        505,
        "rickn0njy",
    )


def test_parse_ssh_command_defaults_to_port_22():
    assert parse_ssh_command("rickn0njy@silvren.com") == ("silvren.com", 22, "rickn0njy")


def test_parse_ssh_command_rejects_malformed_input():
    assert parse_ssh_command("not-a-valid-command") is None
    assert parse_ssh_command("") is None
    assert parse_ssh_command("-p 505") is None  # no user@host at all


# -- _is_authentication_failure (pure, no Qt needed) ---------------------


def test_is_authentication_failure_recognizes_permission_denied():
    assert _is_authentication_failure(
        "PermissionDenied: Permission denied for user x on host y"
    ) is True


def test_is_authentication_failure_rejects_other_messages():
    assert _is_authentication_failure("OSError: Connection refused") is False
    assert _is_authentication_failure("network unreachable") is False
    assert _is_authentication_failure("") is False


# -- blank tab construction ------------------------------------------------


def test_blank_tab_starts_with_no_bridge(qapp):
    tab = make_blank_tab()
    assert tab.bridge is None
    assert tab.connection_state == "Disconnected"
    assert tab.name == "New Tab"
    assert "[Blank tab." in tab.scrollback.toPlainText()


def test_typing_plain_text_on_a_blank_tab_reports_not_connected(qapp):
    tab = make_blank_tab()
    tab.input_line.setText("look")
    tab.input_line.returnPressed.emit()
    assert "[Not connected." in tab.scrollback.toPlainText()


def test_disconnect_on_a_blank_tab_reports_not_connected(qapp):
    tab = make_blank_tab()
    tab.disconnect_bridge()
    assert "[Not connected.]" in tab.scrollback.toPlainText()


def test_reconnect_on_a_blank_tab_reports_nothing_to_reconnect(qapp):
    tab = make_blank_tab()
    tab.reconnect_bridge()
    assert "Nothing to reconnect" in tab.scrollback.toPlainText()


def test_shutdown_on_a_blank_tab_does_not_crash(qapp):
    tab = make_blank_tab()
    tab.shutdown()  # must not raise


# -- /connect <host> <port> on a blank tab -------------------------------


def test_connect_host_port_establishes_a_telnet_bridge(qapp, monkeypatch):
    monkeypatch.setattr(session_tab_module, "TelnetBridge", lambda host, port: FakeBridge())
    tab = make_blank_tab()
    titles = []
    tab.titleChanged.connect(titles.append)

    outcome = tab._commands.process("/connect example.com 4201")

    assert outcome.action == "handled"
    assert tab.bridge is not None
    assert tab.host == "example.com"
    assert tab.port == 4201
    assert tab.name == "example.com:4201"
    assert titles == ["example.com:4201"]


def test_connect_host_port_refuses_when_already_connected(qapp, monkeypatch):
    monkeypatch.setattr(session_tab_module, "TelnetBridge", lambda host, port: FakeBridge())
    tab = make_blank_tab()
    tab._commands.process("/connect example.com 4201")
    first_bridge = tab.bridge

    outcome = tab._commands.process("/connect other.example.com 4202")

    assert outcome.text == "This tab is already connected."
    assert tab.bridge is first_bridge


def test_connect_by_world_name_is_unaffected(qapp):
    # A single non-numeric-second-token argument still falls through to
    # the existing world-name lookup path, unchanged.
    calls = []

    class FakeHostWindow:
        def connect_by_name(self, name):
            calls.append(name)
            return f"Connecting to {name}..."

    tab = SessionTab("example.com", 4201, bridge=FakeBridge(), host_window=FakeHostWindow())
    outcome = tab._commands.process("/connect MyWorld")

    assert calls == ["MyWorld"]
    assert outcome.text == "Connecting to MyWorld..."


# -- /ssh on a blank tab --------------------------------------------------


def test_ssh_command_prompts_for_password_and_connects(qapp, monkeypatch, tmp_path: Path):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("secret", True))
    )
    captured = {}

    def fake_ssh_bridge(host, port, username, password, store):
        captured["host"] = host
        captured["port"] = port
        captured["username"] = username
        captured["password"] = password
        captured["store"] = store
        return FakeBridge()

    monkeypatch.setattr(session_tab_module, "SshBridge", fake_ssh_bridge)

    store = HostKeyStore(tmp_path / "known_hosts.json")
    tab = make_blank_tab(host_key_store=store)
    titles = []
    tab.titleChanged.connect(titles.append)

    outcome = tab._commands.process("/ssh -p 505 rickn0njy@silvren.com")

    assert outcome.action == "handled"
    assert captured == {
        "host": "silvren.com",
        "port": 505,
        "username": "rickn0njy",
        "password": "secret",
        "store": store,
    }
    assert tab.bridge is not None
    assert tab.name == "rickn0njy@silvren.com"
    assert titles == ["rickn0njy@silvren.com"]


def test_ssh_command_cancelled_password_prompt_does_not_connect(qapp, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))
    monkeypatch.setattr(
        session_tab_module, "SshBridge", lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("SshBridge should never be constructed when the prompt is cancelled")
        )
    )

    tab = make_blank_tab()
    outcome = tab._commands.process("/ssh user@example.com")

    assert outcome.text == "SSH connect cancelled."
    assert tab.bridge is None


def test_ssh_command_with_malformed_args_shows_usage(qapp):
    tab = make_blank_tab()
    outcome = tab._commands.process("/ssh not-valid")
    assert outcome.text == "Usage: /ssh [-p port] user@host"


def test_ssh_refuses_when_already_connected(qapp):
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())
    outcome = tab._commands.process("/ssh user@example.com")
    assert outcome.text == "This tab is already connected."


# -- /ssh-forget -----------------------------------------------------------


def test_ssh_forget_removes_a_saved_entry(qapp, tmp_path: Path):
    store = HostKeyStore(tmp_path / "known_hosts.json")
    import asyncssh

    key = asyncssh.generate_private_key("ssh-ed25519").convert_to_public()
    store.check("silvren.com", 505, key)  # seed a trusted entry

    tab = make_blank_tab(host_key_store=store)
    outcome = tab._commands.process("/ssh-forget silvren.com:505")

    assert "Forgot the saved host key" in outcome.text
    assert store.forget("silvren.com", 505) is False  # already gone


def test_ssh_forget_with_no_saved_entry(qapp, tmp_path: Path):
    store = HostKeyStore(tmp_path / "known_hosts.json")
    tab = make_blank_tab(host_key_store=store)
    outcome = tab._commands.process("/ssh-forget silvren.com:505")
    assert "No saved host key found" in outcome.text


def test_ssh_forget_defaults_to_port_22(qapp, tmp_path: Path):
    store = HostKeyStore(tmp_path / "known_hosts.json")
    import asyncssh

    key = asyncssh.generate_private_key("ssh-ed25519").convert_to_public()
    store.check("example.com", 22, key)

    tab = make_blank_tab(host_key_store=store)
    outcome = tab._commands.process("/ssh-forget example.com")

    assert "Forgot the saved host key" in outcome.text


def test_ssh_forget_with_invalid_port_reports_it(qapp, tmp_path: Path):
    store = HostKeyStore(tmp_path / "known_hosts.json")
    tab = make_blank_tab(host_key_store=store)
    outcome = tab._commands.process("/ssh-forget example.com:notaport")
    assert "Invalid port" in outcome.text


def test_ssh_forget_usage_with_no_args(qapp):
    tab = make_blank_tab()
    outcome = tab._commands.process("/ssh-forget")
    assert outcome.text == "Usage: /ssh-forget <host>[:port]"


def test_host_key_store_defaults_to_the_real_path_when_not_overridden(qapp):
    # A structural check, not a real-disk-touching one: confirms the
    # dependency-injection wiring itself (the override attribute), the
    # same pattern _script_store_path() already uses -- this test never
    # actually calls _host_key_store() without an override, so it can't
    # leak to the real ~/.local/share/MushTato/ssh_known_hosts.json.
    tab = make_blank_tab()
    assert tab._host_key_store_override is None
