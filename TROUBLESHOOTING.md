# Troubleshooting / FAQ

This same content is also available inside the app: **Help menu → Help →
FAQ / Troubleshooting**, or type `/help faq` into any tab's command box.

## Connection problems

**"Connection failed" / "Connection refused" right after connecting**
- Double-check the host and port — a typo in either is the most common
  cause. Most MUD/MUSH servers use a specific non-standard port (not 80 or
  443), so check the world's own listing for the exact port.
- The server may simply be down. Try again later, or check the game's own
  website/Discord for a status update.
- A firewall (yours, your network's, or a VPN) may be blocking outbound
  connections on that port. Corporate/school/public networks often block
  non-standard ports entirely.

**Connection hangs, never says "Connected" or "failed"**
- Usually a firewall silently dropping the connection rather than
  rejecting it outright (no response either way). Try a different network
  (e.g. mobile hotspot) to confirm.
- Use **File → Reconnect** or type `/reconnect` once you suspect this —
  it's the same action either way (see the in-app Help's Sessions & Tabs
  and Built-in Commands topics).

**"Connection closed by server" shortly after connecting**
- Some servers close idle/guest connections after inactivity, or reject
  connections from behind certain proxies/VPNs. Try reconnecting, and
  check the server's own connection message (if any) for a stated reason.

**Can't resolve the hostname at all**
- Check for typos in the world's hostname (e.g. `example.com` vs.
  `mush.example.com`).
- If your network uses a custom/restrictive DNS, try connecting by numeric
  IP address if the world's listing provides one.

**A tab went quiet and I never saw "[Connection lost]"**
- MushTato relies on the operating system's TCP keepalive to notice a
  silently-dead connection (one where neither side ever sends a clean
  close — e.g. your own network drops, or a router loses power) — this
  normally takes about 15-20 seconds. A very restrictive firewall/NAT can
  still swallow those low-level keepalive probes on some networks; turning
  on that world's **Keepalive** option (World Properties → Connection)
  adds an application-level nudge (a Telnet no-op sent every 60 seconds)
  that can help in that case.
- Once a drop is detected, MushTato automatically retries reconnecting
  every 30 seconds — no need to reconnect by hand. It keeps retrying
  indefinitely until either a retry succeeds or you click **Disconnect**
  (File menu, toolbar, or `/disconnect`) to give up on it. See the in-app
  Help's Sessions & Tabs topic.

## Installation / launch problems

**Windows: "Windows protected your PC" (SmartScreen)**
- Expected — MushTato isn't signed with a paid code-signing certificate.
  Click **More info → Run anyway**. See `INSTALL.md`.

**macOS: "MushTato can't be opened because it is from an unidentified developer"**
- Expected — the app is unsigned and not notarized (a deliberate, budget-
  driven choice, not an oversight — see `SPEC.md` section 8). Right-click
  (or Control-click) the app → **Open** → **Open** again. See `INSTALL.md`.

**Linux: "could not load the Qt platform plugin \"xcb\""**
- The build bundles its own copy of `libxcb-cursor0` and its usual
  companions, so this shouldn't normally happen — but on an unusually
  minimal system, install them yourself:
  ```
  sudo apt-get install libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 \
      libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
      libxcb-shape0 libxcb-xfixes0 libxcb-xinerama0
  ```
  (Debian/Ubuntu package names; other distros have equivalents under
  different names.) See `INSTALL.md`.

## General questions

**Where are my saved worlds/settings stored?**
See `INSTALL.md`'s "Removing your data" section for the exact per-OS
path.

**Does MushTato support scripting/triggers/macros yet?**
Yes — triggers, gags, highlights, aliases, timers, and persistent
per-world variables, written in sandboxed Python. Manage scripts via
Address Book → select a world → Properties... → Scripts. See the
in-app Help's Scripting topic for the full API and how errors/
auto-disabled triggers are surfaced.

**Why did my saved hotkey stop working / a hotkey doesn't do anything?**
Hotkeys are configured in **Options → Settings...**; changes apply
immediately in the same session. Check there for the current binding —
see the in-app Help's Hotkeys topic for the full current list.

**A toolbar/menu item does nothing when I click it**
Some items (Upload, Mail Window) are shown disabled (grayed out) on
purpose — they're modeled on real Potato features MushTato doesn't
have working equivalents for yet, not broken buttons. See the in-app
Help's Menus & Toolbar topic.

**Can I have more than one Text Editor window open at once?**
Yes — unlike the Address Book, Help, and Error Log windows (one
reused window each), Tools → Editor always opens a brand-new,
independent window every time, so you can draft several things at
once.

**Where did the Error Log come from, and what does it show?**
Tools → Error Log shows genuinely *unhandled* exceptions only — not a
duplicate of errors already shown directly in a tab's scrollback
(script/trigger/connection errors stay exactly where they already
were). See the in-app Help's Menus & Toolbar topic.

**Does MushTato make URLs in the scrollback clickable?**
Yes — any `http://` or `https://` URL in a tab's scrollback (or a spawned
log window mirroring it) is shown underlined in a distinct color; clicking
it opens your system's default web browser. Purely a display-layer
feature — it doesn't change what the server sent or what triggers see.

**I checked "auto-login" on a world but nothing happens at startup**
Auto-login also requires that world to have a default Character set
(Properties... → Basic, or just add its first Character on the
Characters page, which auto-selects it as the default) — a checked box
with no default Character is inert, since there'd be nothing to log in
as. If a world's row shows no checkbox at all, that's the same cause:
set a default Character first and the checkbox appears. See the in-app
Help's Address Book topic.
