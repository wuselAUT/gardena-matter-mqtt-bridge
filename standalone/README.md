# Gardena Matter Bridge — Standalone Installer

**EN:** Windows installer that puts the Gardena Matter Bridge on your gateway — no Home Assistant required.

**DE:** Windows-Installer, der die Gardena Matter Bridge auf das Gateway bringt — ohne Home Assistant.

---

## What it does / Was es tut

The installer discovers your GARDENA Smart Gateway on the local network (via ARP/MAC or mDNS),
authenticates using the Device ID printed on the sticker on the underside of the gateway,
and deploys the Gardena Matter Bridge software directly onto the gateway.

After installation, the gateway appears as a Matter bridge device that can be paired with any
Matter-compatible controller (Apple Home, Google Home, Amazon Alexa, Home Assistant, and others).

Der Installer findet das GARDENA Smart Gateway im lokalen Netz (via ARP/MAC oder mDNS),
authentifiziert sich mit der Geräte-ID vom Aufkleber auf der Unterseite des Gateways und
installiert die Gardena Matter Bridge direkt auf dem Gateway.

Nach der Installation erscheint das Gateway als Matter-Bridge, die mit jedem Matter-fähigen
Controller (Apple Home, Google Home, Amazon Alexa, Home Assistant u.a.) gekoppelt werden kann.

---

## Requirements / Voraussetzungen

- **Windows 10 or 11** with the built-in **OpenSSH Client** enabled
  - Settings → Apps → Optional Features → Add a feature → **OpenSSH Client**
  - No PuTTY, Git Bash, or WSL required — only Windows built-in tools are used
  - `curl` is pre-installed on Windows 10/11
- **Network access** to the GARDENA Smart Gateway (same local network / LAN)
- **Device ID / Geräte-ID** from the sticker on the underside of the gateway
  (format: `a1b2c3d4-e5f6-7890-abcd-ef1234567890` — NOT the `GARDENA-XXXXXX` hostname)

---

## Usage / Verwendung

1. Download `gardena-installer-windows.exe` from the [Releases](../releases) page.
2. Double-click the `.exe` (or run it in a terminal / Eingabeaufforderung).
3. Follow the interactive prompts:
   - The installer searches for your gateway automatically.
   - Enter the Device ID from the sticker when prompted.
   - Confirm and wait 1–2 minutes for the deployment to complete.
4. A browser window opens to `https://<gateway-ip>/assets/matter.html` for Matter pairing.

---

## Building from source / Aus dem Quellcode bauen

### Prerequisites / Voraussetzungen

```
pip install pyinstaller
```

Python 3.9 or newer is required.

### Build command / Build-Befehl

Run from the repository root:

```
pyinstaller standalone/gardena-installer.spec
```

The output is `dist/gardena-installer-windows.exe` (single self-contained executable).

The spec file expects the following layout relative to the repository root:

```
standalone/
  gardena_installer/
  gardena-installer.spec
gardena_matter_bridge/
  orchestrate.py
  bridge-release.lock
```

To override the source of `orchestrate.py` or `bridge-release.lock`, place copies of those
files directly next to `gardena-installer.spec` — they take precedence over
`gardena_matter_bridge/`.

---

## Platforms / Plattformen

| Platform | Status |
|---|---|
| Windows 10 / 11 | Supported / Unterstützt |
| macOS | Planned / Geplant |
| Linux | Planned / Geplant |

---

## Log file / Log-Datei

The installer writes a log to `~/gardena-install.log` for troubleshooting.

Der Installer schreibt ein Log nach `~/gardena-install.log` zur Fehlersuche.
