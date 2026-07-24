"""Minimal telnet IAC (option negotiation) handling.

We don't (yet) implement any actual telnet options -- no MCCP, no GMCP,
no NAWS/TTYPE -- so this module's whole job is to recognize negotiation
sequences arriving from the server and answer them the same way for
every option: "no". That keeps a server that offers optional features
(echo suppression, compression, GMCP, ...) from stalling the connection
waiting for a reply we'd otherwise never send, without pretending to
support anything we don't.
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

_NORMAL = 0
_GOT_IAC = 1
_GOT_NEGOTIATION_CMD = 2
_IN_SUBNEGOTIATION = 3
_SUBNEGOTIATION_GOT_IAC = 4


class TelnetNegotiator:
    """Stateful, incremental telnet IAC processor.

    Feed it raw bytes as they arrive from the socket; get back the
    plain application-data bytes (IAC-escaping undone, negotiation
    sequences stripped out) plus any reply bytes that should be written
    back to the server.
    """

    def __init__(self) -> None:
        self._state = _NORMAL
        self._pending_cmd = 0

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
                    reply += bytes((IAC, WONT, option))
                # WONT/DONT from the server are informational; no reply.
                self._state = _NORMAL

            elif self._state == _IN_SUBNEGOTIATION:
                if byte == IAC:
                    self._state = _SUBNEGOTIATION_GOT_IAC
                # Suboption payload bytes are discarded -- we don't
                # support any suboption, so there's nothing to read.

            elif self._state == _SUBNEGOTIATION_GOT_IAC:
                # IAC SE properly ends the block; anything else is
                # treated as ending it too (defensive: never get stuck
                # waiting inside a subnegotiation).
                self._state = _NORMAL

        return bytes(text), bytes(reply)
