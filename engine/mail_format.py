"""Mail command formatting (Phase 12b): pure string logic behind the
Mail Window, verified against Potato's real source
(``potato.tcl``'s ``mailWindow``/``mailWindowFormatChange``/
``mailWindowSend``, ``potato-config.tcl``'s ``gameMail`` array) rather
than guessed. Kept Qt-free (CLAUDE.md rule 2) so it's headlessly
testable without a QApplication.
"""

from __future__ import annotations

from typing import List

# Verified against potato-config.tcl's gameMail array -- Potato's own
# real built-in mail-format command templates, replicated verbatim.
# "Custom" isn't listed here: its template is per-world user data
# (WorldProfile.mail_format_custom), not a fixed constant.
FORMAT_TEMPLATES = {
    "MUSH @mail": "@mail %to%=%subject%/%body%",
    "MUX @mail": "@mail %to%=%subject% ;; -%body% ;; --",
    "Multi-Command +mail": "+mail %to%=%subject% ;; -%body% ;; --",
    "MUSE +mail": "+mail %to%=%body%",
    "Myrddin's BB": "+bbpost %to%/%subject%=%body%",
}

CUSTOM_FORMAT = "Custom"

FORMAT_NAMES = list(FORMAT_TEMPLATES) + [CUSTOM_FORMAT]

_PLACEHOLDER_FIELDS = ("to", "cc", "bcc", "subject")

# The exact same delimiter Potato's own mailWindowSend uses ("\b", a
# literal backspace) to mark template-level ";;" split points before
# any user-supplied text is substituted in -- not an arbitrary choice.
_SPLIT_SENTINEL = "\b"

# % ; [ ] ( ) , ^ $ { } \ -- verified against Potato's real escapeChars
# (called with its own defaults, specials=1, from the Mail Window's
# File > Escape Special Characters action).
_SPECIAL_CHARS = "".join(chr(code) for code in (37, 59, 91, 93, 40, 41, 44, 94, 36, 123, 125, 92))


def fields_used_by_template(template: str) -> List[str]:
    """Which of to/cc/bcc/subject actually appear as placeholders in
    ``template`` -- drives the compose window's per-field enable/
    disable behavior, verified against ``mailWindowFormatChange``'s
    own ``string first "%$field%" $format`` check.
    """
    return [field for field in _PLACEHOLDER_FIELDS if f"%{field}%" in template]


def build_mail_commands(
    template: str,
    *,
    to: str,
    cc: str,
    bcc: str,
    subject: str,
    body: str,
    convert_returns: bool,
    convert_returns_to: str,
) -> List[str]:
    """Returns the list of raw lines to send to the server for one
    piece of mail, given the (already-resolved) command ``template``.

    Order matters and is verified against ``mailWindowSend``'s own
    implementation, not arbitrary: ``;;`` (bare or space-surrounded)
    in the *template* is converted to a sentinel *before* any
    placeholder substitution happens, and only *then* are
    %to%/%cc%/%bcc%/%subject%/%body% substituted in -- doing it the
    other way around (substitute first, split second) would let a
    literal ";;" typed by the user in their own subject/body text get
    misinterpreted as an extra split point, fragmenting their message.
    Only placeholders the template actually references get
    substituted (matching ``mailWindowFormatChange``'s own enable/
    disable check) -- though since an unreferenced placeholder would
    never appear in the template text anyway, this is a no-op either
    way, not a real behavioral difference.
    """
    text = body
    if convert_returns:
        text = text.replace("\n", convert_returns_to)

    delimited = template.replace(" ;; ", _SPLIT_SENTINEL).replace(";;", _SPLIT_SENTINEL)

    values = {"to": to, "cc": cc, "bcc": bcc, "subject": subject}
    substituted = delimited.replace("%body%", text)
    for field_name in _PLACEHOLDER_FIELDS:
        placeholder = f"%{field_name}%"
        if placeholder in substituted:
            substituted = substituted.replace(placeholder, values[field_name])

    return substituted.split(_SPLIT_SENTINEL)


def escape_special_characters(text: str) -> str:
    """Backslash-escapes MU*-softcode-special characters (and converts
    tabs to ``%t``) -- verified against Potato's real ``escapeChars``.
    """
    result = []
    for ch in text:
        if ch == "\t":
            result.append("%t")
        elif ch in _SPECIAL_CHARS:
            result.append("\\" + ch)
        else:
            result.append(ch)
    return "".join(result)
