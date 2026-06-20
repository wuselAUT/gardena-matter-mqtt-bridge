# Contributing

Contributions are welcome — this is a hobby project and there is plenty of room to help.

## Hardware for testing (the most helpful contribution!)

The bridge is **generic**, but it can only be *verified* against the GARDENA devices we
physically have (soil sensors + a SILENO mower). By far the most useful thing you can
contribute is **access to other GARDENA smart-system hardware** so it can be mapped,
tested and integrated:

- water control / valves, smart power plugs, pressure pumps, other sensors or mowers, …
- **Lend or donate** such a device, **or** help **test and capture its data layer** on
  your own gateway so the mapping can be added.

Open an issue describing the device (model — keep any SGTIN/serial **redacted**) and we
will coordinate.

## Other ways to help

- **Test reports** from your own setup (which devices, what worked / didn't). See the
  troubleshooting section in the add-on docs for what to include — and **redact secrets**.
- **Bug reports and fixes**, documentation improvements, translations.
- Build / test experiments on the cross-compile toolchain.

## Please note

- **Never post device IDs, passwords, pairing/setup codes or keys** in issues/PRs — redact them.
- The bridge installs into the gateway's **writable overlay** (no flashing, reversible via the
  uninstall scripts), but it remains a hobby project: **no warranty, use at your own risk.**
- Apple Home and Google Home were **not tested** — treat other Matter controllers as experimental.
- Please back technical discussion with a source (command output, repo link, commit).

## Documentation language

The docs are bilingual (English / German). **English is the canonical source** — make content
changes in the English file first (`docs/<page>.md`), then follow up in the German one
(`docs/<page>.de.md`). The German version may lag briefly.
