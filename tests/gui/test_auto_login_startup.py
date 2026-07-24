"""Headless tests for auto-login-on-startup (post-Character-picker
addition): any saved world with its auto-login checkbox set *and* a
default_character chosen opens and logs in automatically when the app
starts -- no confirmation prompt (Rick's explicit call), one world at a
time, in address-book order.
"""

from engine.storage import CharacterProfile, WorldProfile
from gui.app import auto_login_all, worlds_to_auto_login


def make_world(**kwargs):
    defaults = dict(name="W", host="h", port=1)
    defaults.update(kwargs)
    return WorldProfile(**defaults)


def test_worlds_to_auto_login_requires_both_flag_and_default_character():
    flagged_no_default = make_world(name="A", auto_login=True, default_character="")
    default_not_flagged = make_world(name="B", auto_login=False, default_character="Thoran")
    both = make_world(
        name="C",
        auto_login=True,
        default_character="Thoran",
        characters=[CharacterProfile(name="Thoran")],
    )
    neither = make_world(name="D")

    result = worlds_to_auto_login([flagged_no_default, default_not_flagged, both, neither])

    assert result == [both]


def test_worlds_to_auto_login_preserves_address_book_order():
    first = make_world(name="First", auto_login=True, default_character="X")
    second = make_world(name="Second", auto_login=True, default_character="Y")

    assert worlds_to_auto_login([first, second]) == [first, second]


class FakeHostWindow:
    def __init__(self) -> None:
        self.open_tab_calls = []

    def open_tab(self, host, port, *, name=None, bridge=None, world=None, character=None):
        self.open_tab_calls.append((host, port, name, world, character))
        return (host, port, name)


def test_auto_login_all_opens_each_flagged_world_in_order():
    worlds = [
        make_world(name="First", host="a.example.com", port=1, auto_login=True, default_character="X"),
        make_world(name="Second", host="b.example.com", port=2, auto_login=True, default_character="Y"),
    ]
    host = FakeHostWindow()

    auto_login_all(host, worlds)

    assert host.open_tab_calls == [
        ("a.example.com", 1, "First", worlds[0], None),
        ("b.example.com", 2, "Second", worlds[1], None),
    ]


def test_auto_login_all_does_nothing_for_an_empty_list():
    host = FakeHostWindow()

    auto_login_all(host, [])

    assert host.open_tab_calls == []
