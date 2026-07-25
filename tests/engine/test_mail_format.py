"""Headless tests for engine/mail_format.py -- verified against
Potato's real source (potato.tcl's mailWindowFormatChange/
mailWindowSend, potato-config.tcl's gameMail array), not guessed.
"""

from engine.mail_format import (
    CUSTOM_FORMAT,
    FORMAT_NAMES,
    FORMAT_TEMPLATES,
    build_mail_commands,
    escape_special_characters,
    fields_used_by_template,
)

CUSTOM_TEMPLATE = "writeto %to% %cc% %bcc% about %subject% ;; write %body% ;; send"


def test_format_names_include_all_six_potato_formats():
    assert FORMAT_NAMES == [
        "MUSH @mail",
        "MUX @mail",
        "Multi-Command +mail",
        "MUSE +mail",
        "Myrddin's BB",
        CUSTOM_FORMAT,
    ]


def test_mush_mail_single_line_no_split():
    commands = build_mail_commands(
        FORMAT_TEMPLATES["MUSH @mail"],
        to="Bob",
        cc="",
        bcc="",
        subject="Hi",
        body="Hello",
        convert_returns=True,
        convert_returns_to="%r",
    )
    assert commands == ["@mail Bob=Hi/Hello"]


def test_mux_mail_splits_into_three_lines():
    commands = build_mail_commands(
        FORMAT_TEMPLATES["MUX @mail"],
        to="Bob",
        cc="",
        bcc="",
        subject="Hi",
        body="Body text",
        convert_returns=True,
        convert_returns_to="%r",
    )
    assert commands == ["@mail Bob=Hi", "-Body text", "--"]


def test_multi_command_mail_splits_into_three_lines():
    commands = build_mail_commands(
        FORMAT_TEMPLATES["Multi-Command +mail"],
        to="Bob",
        cc="",
        bcc="",
        subject="Hi",
        body="Body text",
        convert_returns=True,
        convert_returns_to="%r",
    )
    assert commands == ["+mail Bob=Hi", "-Body text", "--"]


def test_muse_mail_has_no_subject_placeholder():
    # MUSE's real template never references %subject% at all -- the
    # subject value is silently never sent, matching Potato's own
    # real (if surprising) behavior exactly.
    assert fields_used_by_template(FORMAT_TEMPLATES["MUSE +mail"]) == ["to"]

    commands = build_mail_commands(
        FORMAT_TEMPLATES["MUSE +mail"],
        to="Bob",
        cc="",
        bcc="",
        subject="this subject is ignored",
        body="Hello",
        convert_returns=True,
        convert_returns_to="%r",
    )
    assert commands == ["+mail Bob=Hello"]
    assert "ignored" not in commands[0]


def test_myrddins_bb_format():
    commands = build_mail_commands(
        FORMAT_TEMPLATES["Myrddin's BB"],
        to="board",
        cc="",
        bcc="",
        subject="Announcement",
        body="Hello everyone",
        convert_returns=True,
        convert_returns_to="%r",
    )
    assert commands == ["+bbpost board/Announcement=Hello everyone"]


def test_custom_format_uses_all_four_fields_and_splits_into_three_lines():
    commands = build_mail_commands(
        CUSTOM_TEMPLATE,
        to="Bob",
        cc="Alice",
        bcc="Carol",
        subject="Hi",
        body="Test message",
        convert_returns=True,
        convert_returns_to="%r",
    )
    assert commands == [
        "writeto Bob Alice Carol about Hi",
        "write Test message",
        "send",
    ]


def test_fields_used_by_template_for_custom_includes_all_four():
    assert fields_used_by_template(CUSTOM_TEMPLATE) == ["to", "cc", "bcc", "subject"]


def test_fields_used_by_template_for_mush_excludes_cc_and_bcc():
    assert fields_used_by_template(FORMAT_TEMPLATES["MUSH @mail"]) == ["to", "subject"]


def test_convert_returns_replaces_newlines_before_substitution():
    commands = build_mail_commands(
        FORMAT_TEMPLATES["MUSH @mail"],
        to="Bob",
        cc="",
        bcc="",
        subject="Hi",
        body="line one\nline two",
        convert_returns=True,
        convert_returns_to="%r",
    )
    assert commands == ["@mail Bob=Hi/line one%rline two"]


def test_convert_returns_disabled_leaves_newlines_in_body():
    commands = build_mail_commands(
        FORMAT_TEMPLATES["MUSH @mail"],
        to="Bob",
        cc="",
        bcc="",
        subject="Hi",
        body="line one\nline two",
        convert_returns=False,
        convert_returns_to="%r",
    )
    assert commands == ["@mail Bob=Hi/line one\nline two"]


def test_literal_double_semicolon_in_user_body_is_not_treated_as_a_split_point():
    # The exact bug this module's docstring warns about: a template
    # with no ";;" of its own must never let literal ";;" typed by the
    # user in their own body text get misread as a split point.
    commands = build_mail_commands(
        FORMAT_TEMPLATES["MUSH @mail"],
        to="Bob",
        cc="",
        bcc="",
        subject="Hi",
        body="meet me at 3;;30pm",
        convert_returns=True,
        convert_returns_to="%r",
    )
    assert commands == ["@mail Bob=Hi/meet me at 3;;30pm"]


def test_literal_double_semicolon_in_user_body_survives_inside_a_split_template():
    # Same claim, but for a template that DOES split (MUX) -- the
    # user's own ";;" inside the body must still just be literal text
    # within whichever piece it landed in, not an extra split point.
    commands = build_mail_commands(
        FORMAT_TEMPLATES["MUX @mail"],
        to="Bob",
        cc="",
        bcc="",
        subject="Hi",
        body="see you at 3;;30",
        convert_returns=True,
        convert_returns_to="%r",
    )
    assert commands == ["@mail Bob=Hi", "-see you at 3;;30", "--"]


def test_escape_special_characters_escapes_softcode_specials():
    result = escape_special_characters("50% off [today] (only), $1 {deal} \\ done ; ok")
    assert result == r"50\% off \[today\] \(only\)\, \$1 \{deal\} \\ done \; ok"


def test_escape_special_characters_converts_tabs():
    assert escape_special_characters("a\tb") == "a%tb"


def test_escape_special_characters_leaves_non_special_punctuation_alone():
    # "!" and "." aren't in Potato's real special-character set -- only
    # the comma here should get escaped.
    assert escape_special_characters("Hello, World! No specials here.") == (
        r"Hello\, World! No specials here."
    )
