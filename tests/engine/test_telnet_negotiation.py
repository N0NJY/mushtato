"""Headless tests for telnet IAC negotiation -- no live server needed."""

from typing import Tuple

from engine.net.telnet import (
    DO,
    DONT,
    IAC,
    NAWS,
    SB,
    SE,
    TTYPE,
    TTYPE_IS,
    TTYPE_SEND,
    TelnetNegotiator,
    WILL,
    WONT,
)


def test_plain_text_passes_through_unchanged():
    neg = TelnetNegotiator()
    clean, reply = neg.feed(b"hello world\r\n")
    assert clean == b"hello world\r\n"
    assert reply == b""


def test_will_option_is_refused_with_dont():
    neg = TelnetNegotiator()
    clean, reply = neg.feed(bytes((IAC, WILL, 1)))  # option 1 = ECHO
    assert clean == b""
    assert reply == bytes((IAC, DONT, 1))


def test_do_option_is_refused_with_wont():
    neg = TelnetNegotiator()
    clean, reply = neg.feed(bytes((IAC, DO, 31)))  # option 31 = NAWS
    assert clean == b""
    assert reply == bytes((IAC, WONT, 31))


def test_wont_and_dont_get_no_reply():
    neg = TelnetNegotiator()
    clean, reply = neg.feed(bytes((IAC, WONT, 1, IAC, DONT, 31)))
    assert clean == b""
    assert reply == b""


def test_escaped_iac_byte_is_preserved_as_literal_data():
    neg = TelnetNegotiator()
    clean, reply = neg.feed(bytes((ord("a"), IAC, IAC, ord("b"))))
    assert clean == bytes((ord("a"), IAC, ord("b")))
    assert reply == b""


def test_escaped_iac_byte_split_across_feed_calls():
    # The two 0xFF bytes of an escaped IAC IAC can themselves land in
    # separate reads; state must carry over correctly either way.
    neg = TelnetNegotiator()
    clean1, reply1 = neg.feed(bytes((ord("a"), IAC)))
    assert clean1 == b"a"
    assert reply1 == b""

    clean2, reply2 = neg.feed(bytes((IAC, ord("b"))))
    assert clean2 == bytes((IAC, ord("b")))
    assert reply2 == b""


def test_subnegotiation_block_is_skipped_without_reply():
    neg = TelnetNegotiator()
    data = bytes((IAC, SB, 24, 1, IAC, SE)) + b"visible text"
    clean, reply = neg.feed(data)
    assert clean == b"visible text"
    assert reply == b""


def test_negotiation_split_across_feed_calls():
    neg = TelnetNegotiator()
    clean1, reply1 = neg.feed(bytes((IAC, WILL)))
    assert clean1 == b""
    assert reply1 == b""

    clean2, reply2 = neg.feed(bytes((1,)) + b"hi")
    assert clean2 == b"hi"
    assert reply2 == bytes((IAC, DONT, 1))


def test_go_ahead_is_consumed_without_hanging():
    neg = TelnetNegotiator()
    clean, reply = neg.feed(b"HP: 100> " + bytes((IAC, 249)))  # IAC GA
    assert clean == b"HP: 100> "
    assert reply == b""


def _feed_byte_at_a_time(neg: TelnetNegotiator, data: bytes) -> Tuple[bytes, bytes]:
    """Feed ``data`` to ``neg`` one byte per call -- the most extreme
    version of "split across separate asyncio reads", exercising every
    possible split point in the sequence at once.
    """
    clean = bytearray()
    reply = bytearray()
    for byte in data:
        chunk_clean, chunk_reply = neg.feed(bytes((byte,)))
        clean += chunk_clean
        reply += chunk_reply
    return bytes(clean), bytes(reply)


def test_will_sequence_split_byte_at_a_time():
    data = bytes((IAC, WILL, 1)) + b"hi"
    whole_clean, whole_reply = TelnetNegotiator().feed(data)
    piecewise_clean, piecewise_reply = _feed_byte_at_a_time(TelnetNegotiator(), data)

    assert piecewise_clean == whole_clean == b"hi"
    assert piecewise_reply == whole_reply == bytes((IAC, DONT, 1))


def test_do_sequence_split_byte_at_a_time():
    data = bytes((IAC, DO, 31)) + b"hi"
    whole_clean, whole_reply = TelnetNegotiator().feed(data)
    piecewise_clean, piecewise_reply = _feed_byte_at_a_time(TelnetNegotiator(), data)

    assert piecewise_clean == whole_clean == b"hi"
    assert piecewise_reply == whole_reply == bytes((IAC, WONT, 31))


def test_subnegotiation_split_byte_at_a_time():
    data = bytes((IAC, SB, 24, 1, IAC, SE)) + b"visible text"
    whole_clean, whole_reply = TelnetNegotiator().feed(data)
    piecewise_clean, piecewise_reply = _feed_byte_at_a_time(TelnetNegotiator(), data)

    assert piecewise_clean == whole_clean == b"visible text"
    assert piecewise_reply == whole_reply == b""


# -- NAWS/TTYPE (item 7 of the SSL/proxy/NAWS plan), both opt-in ---------
# and both disabled by default -- every test above already proves the
# disabled/default behavior is completely unchanged (NAWS/TTYPE's own
# option codes, 31 and 24, are exercised by test_do_option_is_refused_
# with_wont and test_subnegotiation_block_is_skipped_without_reply
# respectively, both still passing unmodified).


def test_naws_do_when_enabled_replies_will_then_sends_fixed_width_height():
    neg = TelnetNegotiator(naws_enabled=True)
    clean, reply = neg.feed(bytes((IAC, DO, NAWS)))

    assert clean == b""
    assert reply == bytes((IAC, WILL, NAWS)) + bytes((IAC, SB, NAWS, 0, 80, 0, 24, IAC, SE))


def test_naws_uses_custom_width_and_height():
    neg = TelnetNegotiator(naws_enabled=True, naws_width=132, naws_height=43)
    _, reply = neg.feed(bytes((IAC, DO, NAWS)))

    assert reply == bytes((IAC, WILL, NAWS)) + bytes((IAC, SB, NAWS, 0, 132, 0, 43, IAC, SE))


def test_naws_subnegotiation_escapes_a_literal_0xff_width_or_height_byte():
    # A width/height of exactly 255 produces a literal 0xFF low byte,
    # which must be doubled (IAC IAC) inside the subnegotiation payload
    # -- the same escaping rule that applies to ordinary application
    # data, verified explicitly rather than assumed safe because the
    # fixed defaults (80x24) never actually exercise this path.
    neg = TelnetNegotiator(naws_enabled=True, naws_width=255, naws_height=24)
    _, reply = neg.feed(bytes((IAC, DO, NAWS)))

    assert reply == bytes((IAC, WILL, NAWS)) + bytes(
        (IAC, SB, NAWS, 0, IAC, IAC, 0, 24, IAC, SE)
    )


def test_naws_do_when_disabled_is_unaffected_by_width_height_kwargs():
    # Passing naws_width/height without naws_enabled=True must behave
    # identically to the plain default-refuse case -- these kwargs are
    # inert unless naws is actually enabled.
    neg = TelnetNegotiator(naws_width=132, naws_height=43)
    clean, reply = neg.feed(bytes((IAC, DO, NAWS)))

    assert clean == b""
    assert reply == bytes((IAC, WONT, NAWS))


def test_ttype_do_when_enabled_replies_will_only_no_immediate_subnegotiation():
    neg = TelnetNegotiator(term_enabled=True)
    clean, reply = neg.feed(bytes((IAC, DO, TTYPE)))

    assert clean == b""
    assert reply == bytes((IAC, WILL, TTYPE))


def test_ttype_send_request_when_enabled_replies_with_client_name():
    neg = TelnetNegotiator(term_enabled=True)
    neg.feed(bytes((IAC, DO, TTYPE)))

    _, reply = neg.feed(bytes((IAC, SB, TTYPE, TTYPE_SEND, IAC, SE)))

    assert reply == bytes((IAC, SB, TTYPE, TTYPE_IS)) + b"MushTato" + bytes((IAC, SE))


def test_ttype_uses_custom_term_name():
    neg = TelnetNegotiator(term_enabled=True, term_name="MyClient")
    neg.feed(bytes((IAC, DO, TTYPE)))

    _, reply = neg.feed(bytes((IAC, SB, TTYPE, TTYPE_SEND, IAC, SE)))

    assert reply == bytes((IAC, SB, TTYPE, TTYPE_IS)) + b"MyClient" + bytes((IAC, SE))


def test_ttype_name_with_a_space_is_mapped_to_an_underscore():
    # Matches Potato's own real behavior (a raw space in a TTYPE
    # payload is nonstandard -- TTYPE names are conventionally single
    # tokens).
    neg = TelnetNegotiator(term_enabled=True, term_name="My Client")
    neg.feed(bytes((IAC, DO, TTYPE)))

    _, reply = neg.feed(bytes((IAC, SB, TTYPE, TTYPE_SEND, IAC, SE)))

    assert reply == bytes((IAC, SB, TTYPE, TTYPE_IS)) + b"My_Client" + bytes((IAC, SE))


def test_ttype_send_request_ignored_when_disabled():
    neg = TelnetNegotiator()  # term_enabled=False, the default
    clean_do, reply_do = neg.feed(bytes((IAC, DO, TTYPE)))
    assert reply_do == bytes((IAC, WONT, TTYPE))

    clean_send, reply_send = neg.feed(bytes((IAC, SB, TTYPE, TTYPE_SEND, IAC, SE)))
    assert clean_send == b""
    assert reply_send == b""


def test_naws_do_split_byte_at_a_time():
    data = bytes((IAC, DO, NAWS)) + b"hi"
    whole_clean, whole_reply = TelnetNegotiator(naws_enabled=True).feed(data)
    piecewise_clean, piecewise_reply = _feed_byte_at_a_time(
        TelnetNegotiator(naws_enabled=True), data
    )

    assert piecewise_clean == whole_clean == b"hi"
    assert piecewise_reply == whole_reply


def test_ttype_send_sequence_split_byte_at_a_time():
    do_data = bytes((IAC, DO, TTYPE))
    send_data = bytes((IAC, SB, TTYPE, TTYPE_SEND, IAC, SE)) + b"hi"

    whole = TelnetNegotiator(term_enabled=True)
    whole.feed(do_data)
    whole_clean, whole_reply = whole.feed(send_data)

    piecewise = TelnetNegotiator(term_enabled=True)
    _feed_byte_at_a_time(piecewise, do_data)
    piecewise_clean, piecewise_reply = _feed_byte_at_a_time(piecewise, send_data)

    assert piecewise_clean == whole_clean == b"hi"
    assert piecewise_reply == whole_reply == bytes(
        (IAC, SB, TTYPE, TTYPE_IS)
    ) + b"MushTato" + bytes((IAC, SE))
