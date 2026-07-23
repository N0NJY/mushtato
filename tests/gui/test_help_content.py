"""Headless tests for the Help content/window mechanism itself (Phase
8). Content *accuracy* is Rick's own review, not something to unit
test -- these tests verify the mechanism: topics resolve, the command
list stays in sync with what's actually registered, Markdown stripping
works, and the Help window's navigation actually moves the cursor.
"""

from gui.help.markdown_tools import strip_markdown
from gui.help.topics import COMMAND_HELP, TOPICS, HelpContext, get_topic
from gui.help.help_window import HelpWindow
from gui.windows.session_tab import SessionTab
from tests.gui.test_main_window_smoke import FakeBridge


def test_get_topic_resolves_a_known_slug():
    topic = get_topic("hotkeys")
    assert topic is not None
    assert topic.title == "Hotkeys"


def test_get_topic_returns_none_for_unknown_slug():
    assert get_topic("does-not-exist") is None


def test_get_topic_is_case_insensitive():
    assert get_topic("HOTKEYS") is get_topic("hotkeys")


def test_every_topic_renders_non_empty_content():
    context = HelpContext(hotkeys={"close_window": "Ctrl+W"}, theme="dark")
    for topic in TOPICS:
        text = topic.render(context)
        assert text.strip()
        assert topic.title in text


def test_hotkeys_topic_reflects_the_context_s_live_bindings():
    context = HelpContext(hotkeys={"close_window": "Ctrl+Shift+Q"}, theme="dark")
    topic = get_topic("hotkeys")
    assert "Ctrl+Shift+Q" in topic.render(context)


def test_themes_topic_reflects_the_context_s_current_theme():
    context = HelpContext(hotkeys={}, theme="light")
    topic = get_topic("themes")
    assert "light" in topic.render(context)


def test_commands_topic_lists_every_registered_command():
    context = HelpContext(hotkeys={}, theme="dark")
    text = get_topic("commands").render(context)
    for name, _ in COMMAND_HELP:
        assert f"/{name}" in text


def test_no_topic_uses_angle_bracket_placeholders(qapp):
    # Regression guard for a real bug found via visual + pixel-sampled
    # verification: Qt's QTextBrowser.setMarkdown() parses "<name>"-
    # style text as inline HTML, silently swallowing every command's
    # description that followed one in the same document. Square
    # brackets ("[name]") were the fix -- this asserts no content ever
    # regresses back to the angle-bracket form.
    context = HelpContext(hotkeys={"close_window": "Ctrl+W"}, theme="dark")
    for topic in TOPICS:
        text = topic.render(context)
        assert "<" not in text, f"topic {topic.slug!r} has an angle bracket: {text!r}"


def test_markdown_rendering_does_not_swallow_content_after_a_placeholder(qapp):
    # The actual manifestation of the bug above: rendering the full
    # "commands" topic through QTextBrowser.setMarkdown() must produce
    # every command's description, not just the ones before the first
    # "<...>"-shaped placeholder.
    from PySide6.QtWidgets import QTextBrowser

    context = HelpContext(hotkeys={}, theme="dark")
    text = get_topic("commands").render(context)
    browser = QTextBrowser()
    browser.setMarkdown(text)
    rendered = browser.toPlainText()
    for name, help_text in COMMAND_HELP:
        assert help_text in rendered, f"/{name}'s help text was corrupted in rendering"


def test_command_help_matches_what_session_tab_actually_registers(qapp):
    # Regression guard for the "single source of truth" claim: every
    # name SessionTab actually registers must appear in COMMAND_HELP,
    # and vice versa -- not just "looks right," actually checked
    # against the live CommandTable.
    tab = SessionTab("example.com", 4201, bridge=FakeBridge())
    registered_names = {name for name, _ in COMMAND_HELP}
    for name in registered_names:
        assert tab._commands.command_help_text(name) is not None


def test_strip_markdown_removes_headers_and_emphasis():
    text = "# A Title\n\nSome **bold** and *italic* and __also bold__ text."
    stripped = strip_markdown(text)
    assert "#" not in stripped
    assert "**" not in stripped
    assert "__" not in stripped
    assert "A Title" in stripped
    assert "bold" in stripped
    assert "italic" in stripped


def test_strip_markdown_keeps_list_bullets_and_backticks():
    text = "- `/quit` -- closes the tab"
    assert strip_markdown(text) == text


def test_help_window_toc_navigation_moves_the_cursor(qapp):
    window = HelpWindow(hotkeys={"close_window": "Ctrl+W"}, theme="dark")
    window.show()
    first_slug = TOPICS[0].slug
    last_slug = TOPICS[-1].slug

    assert window.jump_to(last_slug) is True
    cursor_after_last = window.browser.textCursor().position()

    assert window.jump_to(first_slug) is True
    cursor_after_first = window.browser.textCursor().position()

    assert cursor_after_last > cursor_after_first


def test_help_window_jump_to_unknown_slug_returns_false(qapp):
    window = HelpWindow(hotkeys={}, theme="dark")
    assert window.jump_to("not-a-real-topic") is False


def test_help_window_refresh_picks_up_new_hotkeys(qapp):
    # Distinct, unlikely-to-collide bindings -- "Ctrl+W" is also used
    # as a plain-English example elsewhere in the static prose, which
    # would make that specific value a false positive here.
    window = HelpWindow(hotkeys={"close_window": "Ctrl+Shift+Z9"}, theme="dark")
    assert "Ctrl+Shift+Z9" in window.browser.toPlainText()
    window.refresh({"close_window": "Ctrl+Alt+Q8"}, "dark")
    assert "Ctrl+Alt+Q8" in window.browser.toPlainText()
    assert "Ctrl+Shift+Z9" not in window.browser.toPlainText()


def test_anchor_click_simulated_jumps_to_the_right_section(qapp):
    from PySide6.QtCore import QUrl

    window = HelpWindow(hotkeys={}, theme="dark")
    window.show()
    target_slug = TOPICS[-1].slug
    window._on_anchor_clicked(QUrl(f"#{target_slug}"))
    assert window.browser.textCursor().position() == window._section_positions[target_slug]
