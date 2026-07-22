#!/usr/bin/env python3
"""Throwaway dev tool: connect to a MUD/MUSH server and talk to it from
a plain terminal, with ANSI color reconstructed via engine.ansi.

Not part of the shipped product -- this exists only to manually
exercise engine/net and engine/ansi against a real server (e.g. Rick's
RhostMUSH) during Phase 3 development. No GUI, no scripting engine.

Usage:
    python scripts/console_client.py <host> <port>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.ansi import AnsiParser, styled_text_to_ansi  # noqa: E402
from engine.net import TelnetClient  # noqa: E402


async def _receive_loop(client: TelnetClient, parser: AnsiParser) -> None:
    while True:
        chunk = await client.read()
        if chunk is None:
            print("\n[connection closed by server]")
            return
        if chunk:
            segments = parser.feed(chunk)
            if segments:
                sys.stdout.write(styled_text_to_ansi(segments))
                sys.stdout.flush()


async def _send_loop(client: TelnetClient) -> None:
    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if line == "":  # stdin closed (e.g. Ctrl-D)
            return
        await client.send_line(line.rstrip("\n"))


async def _main(host: str, port: int) -> None:
    client = TelnetClient(host, port)
    print(f"Connecting to {host}:{port} ...")
    await client.connect()
    print("Connected. Type lines to send; Ctrl-D or Ctrl-C to quit.\n")

    parser = AnsiParser()
    receive = asyncio.create_task(_receive_loop(client, parser))
    send = asyncio.create_task(_send_loop(client))

    done, pending = await asyncio.wait(
        {receive, send}, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
    await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="MUD/MUSH server hostname or IP")
    parser.add_argument("port", type=int, help="server port")
    args = parser.parse_args()

    try:
        asyncio.run(_main(args.host, args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
