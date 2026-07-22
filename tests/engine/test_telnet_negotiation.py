"""Headless tests for telnet IAC negotiation -- no live server needed."""

from typing import Tuple

from engine.net.telnet import DO, DONT, IAC, SB, SE, TelnetNegotiator, WILL, WONT


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
