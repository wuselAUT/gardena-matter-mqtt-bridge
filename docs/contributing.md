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

## Reporting a problem — and the data that helps us fix it

The biggest blocker to fixing a bug is **not being able to see what your gateway sees**. The bridge
runs locally on your gateway, so a good report lets us reason about your exact setup. When something
doesn't work, please open an issue with:

- **Versions:** the add-on version (shown in the add-on UI footer), your Home Assistant version, and
  the gateway firmware version.
- **What you expected vs. what happened** — which device, which value, and whether it's Matter, MQTT
  or both.
- **The bridge log:** `journalctl -u gardena-matter-bridge -n 200 --no-pager` — the bridge's own
  service log on the gateway; it shows device discovery and errors.
- **For MQTT problems:** whether saving the MQTT settings succeeded, and — if MQTT is on — the
  discovered topics and one sample payload, e.g. `mosquitto_sub -h <broker> -t 'gardena/#' -v`.

> **Redact secrets first.** Device IDs, serial numbers / SGTINs, the sticker password,
> pairing/setup codes and broker passwords must be removed or masked before you paste anything.

## Help support a new GARDENA device (capture its data layer)

The bridge is generic: it reads each device's schema and live values straight from the
self-describing **LsDL filesystem** that `lemonbeatd` keeps at **`/var/lib/lemonbeatd/`** on the
gateway (see the [technical docs](technical.md#data-layer-how-the-bridge-reads-sensor-values)). That
directory is exactly what we need to map a device we don't own yet — water control / valves, pressure
pumps, smart power plugs, other sensors or mowers.

If you have such a device and SSH access to your gateway, the most useful thing you can send is a
**redacted snapshot of that directory tree** while the device is paired and reporting:

```bash
# 1) structure + file names (no values yet)
find /var/lib/lemonbeatd -type f | sort

# 2) the contents, so we can see the schema and how values are encoded
#    — redact every serial / SGTIN / address before sharing
```

Attach it to an issue describing the device model. With that we can add the mapping and hand you a
build to re-test — and you will have unlocked that device for everyone who owns the same one.

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
