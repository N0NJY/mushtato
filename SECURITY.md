# Security Policy

MushTato is a free, open-source, single-maintainer hobby project. This
policy is deliberately simple and honest about what that means for
response times — please read "What to expect" below before reporting.

## Supported versions

Only the **latest released version** is supported with security fixes.
There's no long-term-support branch — please update to the
[latest release](https://github.com/N0NJY/mushtato/releases/latest)
before reporting an issue, in case it's already fixed.

## Reporting a vulnerability

**Please do not open a public issue for a security vulnerability.**

Use GitHub's private reporting instead: go to this repo's
[**Security** tab → **Report a vulnerability**](https://github.com/N0NJY/mushtato/security/advisories/new).
This opens a private draft advisory that only the maintainer can see until
it's resolved and you both agree to disclose it.

Please include:
- What version of MushTato you're running (`/version`, or Help → About)
- Your OS
- Steps to reproduce, or a minimal example script/trigger if the issue is
  in the scripting sandbox
- What you'd expect to happen vs. what actually happens

## What to expect

This is maintained by one person in their spare time — there's no
dedicated security team and no contractual SLA. In good faith:
- I'll acknowledge a report as soon as I can, typically within a few days.
- I'll credit you in the fix's changelog/release notes, unless you'd
  rather stay anonymous.
- I'd ask for a reasonable amount of time to ship a fix before any public
  disclosure — for a project this size, that's a conversation, not a fixed
  clock.

## Scope

Things that are genuinely in scope:
- The **scripting sandbox** (`engine/scripting/`, RestrictedPython +
  `google-re2`) — anything that lets a script escape its restrictions,
  access the filesystem/network/subprocess unexpectedly, or otherwise do
  something the sandbox is supposed to prevent.
- The **networking layer** (`engine/net/`) — Telnet/SSH/SSL/SOCKS4
  handling, including anything a malicious server could exploit against a
  connecting client.
- Credential handling — how saved Character passwords, SSH host keys, and
  SSL certificates are stored and used.

## Known, accepted limitations (please don't report these — they're already tracked)

- **A CPU-bound infinite loop in a script isn't forcibly killed.** Script
  execution runs under a best-effort watchdog timeout, but Python's GIL
  means a true busy loop (`while True: pass`) in a trigger/alias callback
  can't actually be preempted from the outside. This is a known,
  documented gap (see `SPEC.md` section 8) — the real fix is running
  script execution in an isolated subprocess, which is more than a small
  patch. It's a local availability/annoyance issue (your own tab hangs),
  not a remote-exploit vector.
- **SSH host keys and SSL certificates use trust-on-first-use, not a
  certificate authority.** This is deliberate — most MU*s and many
  personal shell accounts use self-signed certificates, so CA-based
  verification would just fail outright. MushTato pins on first connect
  and refuses a changed key/cert unless you explicitly run
  `/ssh-forget`/`/ssl-forget`. If you believe the trust-on-first-use model
  itself has a flaw (not just "it isn't a CA"), that's worth reporting.
- **SSH input is line-buffered, not a full character-mode terminal.**
  Not a security issue, just a functional limitation worth knowing about
  so it isn't mistaken for one.

## Out of scope

- Vulnerabilities in a third-party MU*/MUD/SSH server you connect *to* —
  that's the server operator's responsibility, not MushTato's.
- Social engineering, or reports that require physical access to a
  machine already running MushTato with a script the user chose to run
  themselves (trusted-mode execution is opt-in, explicit, and documented
  as intentionally unrestricted — see `SPEC.md` section 8).
