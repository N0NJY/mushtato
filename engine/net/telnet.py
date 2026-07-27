"""Minimal telnet IAC (option negotiation) handling.

We don't implement most telnet options -- no MCCP, no GMCP -- so this
module's default job is to recognize negotiation sequences arriving
from the server and answer them the same way for every option: "no".
That keeps a server that offers optional features (echo suppression,
compression, GMCP, ...) from stalling the connection waiting for a
reply we'd otherwise never send, without pretending to support
anything we don't.

Item 7 of the SSL/proxy/NAWS plan (2026-07-27) adds real, optional
support for exactly two options, both per-connection opt-in (default
off, matching every option's prior behavior exactly when not enabled):
NAWS (RFC 1073, reports terminal width/height) and TTYPE (RFC 1091,
reports a client-identifying name string). Checkpointed: NAWS reports
a *fixed* configured width/height, not a value computed from real
window size -- MushTato's scrollback has no actual "columns" concept
at all (a resizable pane, not a fixed-width terminal emulation), and
verified real Potato's own NAWS implementation does the same (a fixed
configured width, a hardcoded height of 24), not something it computes.
"""

from __future__ import annotations

from typing import Tuple

IAC = 255
DONT = 254
DO = 253
WONT = 252
WILL = 251
SB = 250
SE = 240
NOP = 241  # RFC 854 "no operation" -- used as a keepalive with no visible server effect

NAWS = 31  # RFC 1073
TTYPE = 24  # RFC 1091
TTYPE_IS = 0
TTYPE_SEND = 1

DEFAULT_NAWS_WIDTH = 80
DEFAULT_NAWS_HEIGHT = 24
DEFAULT_TERM_NAME = "MushTato"

_NORMAL = 0
_GOT_IAC = 1
_GOT_NEGOTIATION_CMD = 2
_IN_SUBNEGOTIATION = 3
_SUBNEGOTIATION_GOT_IAC = 4


def _escape_iac(payload: bytes) -> bytes:
    """Doubles any literal 0xFF byte in ``payload`` -- required inside
    a subnegotiation block for the same reason it's required in
    ordinary application data (an unescaped 0xFF would be read as the
    start of a new IAC sequence). Defensive, matching Potato's own real
    NAWS implementation doing the same even though the actual fixed
    width/height/name values used here are always well below 255 in
    practice.
    """
    return payload.replace(bytes((IAC,)), bytes((IAC, IAC)))


class TelnetNegotiator:
    """Stateful, incremental telnet IAC processor.

    Feed it raw bytes as they arrive from the socket; get back the
    plain application-data bytes (IAC-escaping undone, negotiation
    sequences stripped out) plus any reply bytes that should be written
    back to the server.
    """

    def __init__(
        self,
        *,
        naws_enabled: bool = False,
        naws_width: int = DEFAULT_NAWS_WIDTH,
        naws_height: int = DEFAULT_NAWS_HEIGHT,
        term_enabled: bool = False,
        term_name: str = DEFAULT_TERM_NAME,
    ) -> None:
        self._state = _NORMAL
        self._pending_cmd = 0
        self._sub_buffer = bytearray()
        self._naws_enabled = naws_enabled
        self._naws_width = naws_width
        self._naws_height = naws_height
        self._term_enabled = term_enabled
        self._term_name = term_name

    def feed(self, data: bytes) -> Tuple[bytes, bytes]:
        """Process a chunk of incoming bytes.

        Returns ``(clean_text, reply)``: ``clean_text`` is application
        data safe to decode and display; ``reply`` is bytes (possibly
        empty) that should be written back to the server immediately.
        """
        text = bytearray()
        reply = bytearray()

        for byte in data:
            if self._state == _NORMAL:
                if byte == IAC:
                    self._state = _GOT_IAC
                else:
                    text.append(byte)

            elif self._state == _GOT_IAC:
                if byte == IAC:
                    text.append(IAC)  # escaped literal 0xFF in the data
                    self._state = _NORMAL
                elif byte in (WILL, WONT, DO, DONT):
                    self._pending_cmd = byte
                    self._state = _GOT_NEGOTIATION_CMD
                elif byte == SB:
                    self._sub_buffer = bytearray()
                    self._state = _IN_SUBNEGOTIATION
                else:
                    # A stray SE, or a no-option command (NOP, Data
                    # Mark, Break, IP, AO, AYT, EC, EL, GA -- RFC 854).
                    # Nothing to reply to; just consume it.
                    self._state = _NORMAL

            elif self._state == _GOT_NEGOTIATION_CMD:
                option = byte
                if self._pending_cmd == WILL:
                    reply += bytes((IAC, DONT, option))
                elif self._pending_cmd == DO:
                    if option == NAWS and self._naws_enabled:
                        reply += bytes((IAC, WILL, NAWS))
                        reply += self._naws_subnegotiation()
                    elif option == TTYPE and self._term_enabled:
                        reply += bytes((IAC, WILL, TTYPE))
                        # No subnegotiation sent yet here -- TTYPE (unlike
                        # NAWS) is server-initiated: we wait for the
                        # server's own SB TTYPE SEND request below before
                        # replying with the actual name.
                    else:
                        reply += bytes((IAC, WONT, option))
                # WONT/DONT from the server are informational; no reply.
                self._state = _NORMAL

            elif self._state == _IN_SUBNEGOTIATION:
                if byte == IAC:
                    self._state = _SUBNEGOTIATION_GOT_IAC
                else:
                    self._sub_buffer.append(byte)

            elif self._state == _SUBNEGOTIATION_GOT_IAC:
                if byte == IAC:
                    self._sub_buffer.append(IAC)  # escaped literal 0xFF in the payload
                    self._state = _IN_SUBNEGOTIATION
                else:
                    # IAC SE properly ends the block; anything else is
                    # treated as ending it too (defensive: never get
                    # stuck waiting inside a subnegotiation) -- but only
                    # a real IAC SE's buffered payload gets acted on.
                    if byte == SE:
                        reply += self._handle_subnegotiation(bytes(self._sub_buffer))
                    self._sub_buffer = bytearray()
                    self._state = _NORMAL

        return bytes(text), bytes(reply)

    def _naws_subnegotiation(self) -> bytes:
        payload = bytes(
            (
                self._naws_width // 256,
                self._naws_width % 256,
                self._naws_height // 256,
                self._naws_height % 256,
            )
        )
        return bytes((IAC, SB, NAWS)) + _escape_iac(payload) + bytes((IAC, SE))

    def _handle_subnegotiation(self, payload: bytes) -> bytes:
        if not payload:
            return b""
        option, rest = payload[0], payload[1:]
        if option == TTYPE and self._term_enabled and rest[:1] == bytes((TTYPE_SEND,)):
            name = self._term_name.replace(" ", "_").encode("ascii", errors="replace")
            return bytes((IAC, SB, TTYPE, TTYPE_IS)) + _escape_iac(name) + bytes((IAC, SE))
        return b""
