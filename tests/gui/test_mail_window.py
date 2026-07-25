"""Headless tests for the Mail Window (Phase 12b) -- a compose/send-
only dialog modeled on Potato's real ::potato::mailWindow.
"""

from engine.mail_format import CUSTOM_FORMAT
from engine.storage import WorldProfile
from gui.windows.mail_window import MailWindow


def make_window(world=None, sent=None, persisted=None):
    sent = sent if sent is not None else []
    window = MailWindow(
        world,
        sent.append,
        persist_world=(persisted.append if persisted is not None else None),
    )
    return window, sent


def test_title_includes_world_name(qapp):
    window, _ = make_window(WorldProfile(name="Estrellita", host="h", port=1))
    assert "Estrellita" in window.windowTitle()


def test_title_without_a_world(qapp):
    window, _ = make_window(None)
    assert window.windowTitle() == "Send Mail"


def test_defaults_come_from_the_worlds_saved_settings(qapp):
    world = WorldProfile(
        name="X",
        host="h",
        port=1,
        mail_format="MUX @mail",
        mail_format_custom="my custom template",
        mail_convert_returns=False,
        mail_convert_returns_to="\\n",
    )
    window, _ = make_window(world)
    assert window.format_combo.currentText() == "MUX @mail"
    assert window.custom_edit.text() == "my custom template"
    assert window.convert_checkbox.isChecked() is False
    assert window.convert_to_edit.text() == "\\n"


def test_defaults_without_a_world_match_potato(qapp):
    window, _ = make_window(None)
    assert window.format_combo.currentText() == "MUSH @mail"
    assert window.convert_checkbox.isChecked() is True
    assert window.convert_to_edit.text() == "%r"


def test_format_list_has_all_six_options(qapp):
    window, _ = make_window()
    items = [window.format_combo.itemText(i) for i in range(window.format_combo.count())]
    assert items == [
        "MUSH @mail",
        "MUX @mail",
        "Multi-Command +mail",
        "MUSE +mail",
        "Myrddin's BB",
        CUSTOM_FORMAT,
    ]


def test_custom_field_only_enabled_when_custom_format_selected(qapp):
    window, _ = make_window()
    assert window.format_combo.currentText() == "MUSH @mail"
    assert window.custom_edit.isEnabled() is False

    window.format_combo.setCurrentText(CUSTOM_FORMAT)
    assert window.custom_edit.isEnabled() is True


def test_muse_format_disables_cc_bcc_and_subject(qapp):
    window, _ = make_window()
    window.format_combo.setCurrentText("MUSE +mail")

    assert window.to_edit.isEnabled() is True
    assert window.cc_edit.isEnabled() is False
    assert window.bcc_edit.isEnabled() is False
    assert window.subject_edit.isEnabled() is False


def test_custom_format_enables_all_four_fields(qapp):
    window, _ = make_window()
    window.format_combo.setCurrentText(CUSTOM_FORMAT)

    assert window.to_edit.isEnabled() is True
    assert window.cc_edit.isEnabled() is True
    assert window.bcc_edit.isEnabled() is True
    assert window.subject_edit.isEnabled() is True


def test_editing_custom_template_updates_field_states_live(qapp):
    window, _ = make_window()
    window.format_combo.setCurrentText(CUSTOM_FORMAT)
    window.custom_edit.setText("+mail %to%=%body%")  # no cc/bcc/subject

    assert window.to_edit.isEnabled() is True
    assert window.cc_edit.isEnabled() is False
    assert window.bcc_edit.isEnabled() is False
    assert window.subject_edit.isEnabled() is False


def test_send_builds_correct_command_for_mush(qapp):
    window, sent = make_window()
    window.to_edit.setText("Bob")
    window.subject_edit.setText("Hi")
    window.body_edit.setPlainText("Hello")

    window._on_send()

    assert sent == ["@mail Bob=Hi/Hello"]


def test_send_builds_three_lines_for_mux(qapp):
    window, sent = make_window()
    window.format_combo.setCurrentText("MUX @mail")
    window.to_edit.setText("Bob")
    window.subject_edit.setText("Hi")
    window.body_edit.setPlainText("Body text")

    window._on_send()

    assert sent == ["@mail Bob=Hi", "-Body text", "--"]


def test_send_persists_format_to_the_world(qapp):
    world = WorldProfile(name="X", host="h", port=1)
    persisted = []
    window, sent = make_window(world, persisted=persisted)
    window.format_combo.setCurrentText("MUX @mail")
    window.to_edit.setText("Bob")
    window.subject_edit.setText("Hi")
    window.body_edit.setPlainText("Body")

    window._on_send()

    assert world.mail_format == "MUX @mail"
    assert persisted == [world]


def test_send_with_custom_format_persists_the_custom_template(qapp):
    world = WorldProfile(name="X", host="h", port=1)
    persisted = []
    window, sent = make_window(world, persisted=persisted)
    window.format_combo.setCurrentText(CUSTOM_FORMAT)
    window.custom_edit.setText("+mail %to%=%body%")
    window.to_edit.setText("Bob")
    window.body_edit.setPlainText("Body")

    window._on_send()

    assert world.mail_format == CUSTOM_FORMAT
    assert world.mail_format_custom == "+mail %to%=%body%"


def test_send_with_built_in_format_does_not_touch_the_saved_custom_template(qapp):
    # Matches Potato's own real behavior exactly: mail_format_custom is
    # only ever updated when Custom was the format actually selected.
    world = WorldProfile(name="X", host="h", port=1, mail_format_custom="original template")
    window, sent = make_window(world)
    window.format_combo.setCurrentText("MUSH @mail")
    window.to_edit.setText("Bob")
    window.subject_edit.setText("Hi")
    window.body_edit.setPlainText("Body")

    window._on_send()

    assert world.mail_format_custom == "original template"


def test_send_without_a_world_does_not_call_persist(qapp):
    persisted = []
    window, sent = make_window(None, persisted=persisted)
    window.to_edit.setText("Bob")
    window.subject_edit.setText("Hi")
    window.body_edit.setPlainText("Body")

    window._on_send()  # must not raise

    assert persisted == []
    assert sent == ["@mail Bob=Hi/Body"]


def test_send_closes_the_window(qapp):
    window, _ = make_window()
    window.to_edit.setText("Bob")
    window.subject_edit.setText("Hi")
    window.body_edit.setPlainText("Body")
    closed = []
    window.closed.connect(lambda: closed.append(1))

    window._on_send()

    assert closed == [1]


def test_cancel_sends_nothing_and_does_not_persist(qapp):
    world = WorldProfile(name="X", host="h", port=1)
    persisted = []
    window, sent = make_window(world, persisted=persisted)
    window.to_edit.setText("Bob")
    window.body_edit.setPlainText("Body")

    window.cancel_button.click()

    assert sent == []
    assert persisted == []


def test_escape_special_characters_transforms_the_body(qapp):
    window, _ = make_window()
    window.body_edit.setPlainText("50% off [today]")

    window._on_escape_special_characters()

    assert window.body_edit.toPlainText() == r"50\% off \[today\]"


def test_edit_menu_actions_operate_on_the_body_widget(qapp):
    window, _ = make_window()
    window.body_edit.setPlainText("hello world")
    window.body_edit.selectAll()
    window.body_edit.copy()

    assert qapp.clipboard().text() == "hello world"


def test_convert_returns_applied_before_send(qapp):
    window, sent = make_window()
    window.to_edit.setText("Bob")
    window.subject_edit.setText("Hi")
    window.body_edit.setPlainText("line one\nline two")

    window._on_send()

    assert sent == ["@mail Bob=Hi/line one%rline two"]


def test_convert_returns_disabled_leaves_newlines(qapp):
    window, sent = make_window()
    window.convert_checkbox.setChecked(False)
    window.to_edit.setText("Bob")
    window.subject_edit.setText("Hi")
    window.body_edit.setPlainText("line one\nline two")

    window._on_send()

    assert sent == ["@mail Bob=Hi/line one\nline two"]
