# Getting Started

> **From the box to a working Matter device — for ordinary smart-home tinkerers.**
> No soldering, no UART, no programming knowledge required.

!!! warning "Warranty"
    Custom software on the gateway **voids the warranty**. There is a safety net (A/B slots, a
    way back), but use it **at your own risk**.

## What you end up with

Your **GARDENA smart Gateway** appears as a **Matter device** in your smart home — the GARDENA
devices (sensors, mower …) **local and cloud-free**, usable at the same time in **Home
Assistant, Apple Home and Google Home**. No second box, no GARDENA cloud.

## Prerequisites

- **GARDENA smart Gateway Art. 19005**, on the LAN (or Wi-Fi set up), powered.
- The **device ID** from the sticker on the bottom. The **first 8 characters of the ID = the
  login password** (same for SSH and the gateway web interface).
- A running **Home Assistant** installation (for the add-on path below).
- A **Matter-capable smart home**: Home Assistant 2024.10+, Apple Home or Google Home.

## Home Assistant add-on — 1-click setup

The easiest way: add the repository in Home Assistant and let the add-on deploy the bridge
to your gateway automatically — no SSH, no building, no command line.

### Step 1 — Add the repository

Click the badge below or go to **Home Assistant → Settings → Add-ons → Add-on store** →
tap the three-dot menu → **Repositories** → paste the URL:

```
https://github.com/wuselAUT/gardena-matter-bridge
```

[![Add add-on repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FwuselAUT%2Fgardena-matter-bridge)

!!! note "Honest ~3 steps, not 1"
    Home Assistant cannot install a third-party add-on without your confirmation. After
    clicking the badge, you confirm **"Add repository?"**, then find and install the add-on,
    then start it — roughly 3 confirmed steps. Still much easier than SSH.

### Step 2 — Install and configure

1. Find **"GARDENA Matter Bridge"** in the add-on store and click **Install**.
2. Go to the add-on's **Configuration** tab and fill in:
   - **Gateway address**: IP or hostname of your gateway (e.g. `192.168.1.100` or
     `GARDENA-ab1234` — find it in your router).
   - **Device ID**: the full ID from the sticker on the gateway underside
     (e.g. `a1b2c3d4-e5f6-…`). The login password is derived automatically from the
     first 8 characters; you don't type the password separately.
3. Leave all other options at their defaults for now.
4. Click **Save**.

### Step 3 — Deploy and pair

1. Go to the add-on's **Info** tab → click **Start**.
2. Open the add-on's **Web UI** (the sidebar item "GARDENA Matter" or the "Open Web UI"
   button). The status page shows the deploy progress and, once done, the **pairing QR
   code** and the **11-digit manual code**.
3. In Home Assistant: **Settings → Devices & Services → + Add integration → Matter**.
   Scan the QR code or enter the manual code.
4. Home Assistant commissions the device. After a few seconds, the gateway and its GARDENA
   devices appear as entities.

**Done** — no SSH, no command line.

!!! tip "Gateway web UI"
    The gateway's own built-in web interface also shows the pairing QR code and a
    Matter on/off toggle. Open it in your browser:
    ```
    https://<gateway-ip>/assets/matter.html
    ```
    Accept the self-signed certificate warning once. Log in with the gateway password
    (first 8 characters of the device ID).

## Pair the gateway in your smart-home app

### Home Assistant

- **Settings → Devices & Services → Matter → Add device**
- Scan the QR code **or** enter the 11-digit manual code.
- Two to three entities appear per GARDENA device.

### Apple Home

- **+** → **Add Accessory** → **More options** → scan the QR code.
- Apple shows **"This accessory is not certified"** — tap **"Add Anyway"**.
  This is expected for a hobby project (see [Certificates](#matter-certificates)).

### Google Home

- **+** → **Set up device** → **Works with Google** → **Matter** → scan the QR code.
- Google requires a developer registration for test-vendor devices — see
  [Certificates](#matter-certificates).

## Unique pairing code per gateway

Each gateway generates its own **random, unique pairing code** the first time the bridge
starts. The code is derived from a cryptographic key (Spake2+ verifier) and stored on the
gateway's persistent storage — it is **never re-used across devices** and **never stored as
plain text** in the process list.

The QR code and 11-digit manual code shown in the web UI are unique to **this specific
gateway**. Two gateways → two different codes.

The code remains **stable across reboots, add-on updates, and OTA firmware updates** as long
as you do not perform a deliberate [virgin reset](manual.md#virgin-reset).

## Survives a power cut ✅

All commissioning data and configuration live in the gateway's **persistent storage**.
After a power cut or reboot, the gateway restarts automatically and is **immediately ready
again** — **no re-pairing needed**.

## Uninstall / back to original

Remove the bridge via the add-on (the add-on's "Uninstall from gateway" button or the
"Restore original" option). The original Slot A system is never touched; you can always
switch back by resetting the boot slot — see [Manual](manual.md) §5.

## Matter certificates and the "uncertified device" notice

This bridge is a **hobby project** and is **not CSA-certified**. It uses the Matter SDK's
**test attestation** (test vendor ID `0xFFF1`). Every Matter controller therefore treats
it as a **development / uncertified device**. What that means per ecosystem:

### Home Assistant — two options

**Option A — Quick setup (toggle on):** Enable **"Enable test-net DCL usage"** in the HA
Matter Server settings (Settings → Devices & Services → Matter Server → Configure). This
lets HA fetch the test PAA root certificates that the bridge's attestation chain connects
to. When adding the device you may also have to confirm an **"uncertified device"** prompt.

**Option B — Own PAA root (toggle off):** The release package includes a project-specific
PAA root certificate (`gardena-paa-cert.pem`). When you add this file to the HA Matter
Server's credential store, Home Assistant validates the bridge's attestation chain
**locally** — without contacting the test DCL. **"Enable test-net DCL usage" can stay
off.**

Steps for Option B:

1. **Download** `gardena-paa-cert.pem` from the
   [latest release](https://github.com/wuselAUT/gardena-matter-bridge/releases).

2. **Add it to the HA Matter Server credential store.** The Matter Server reads from
   `--paa-root-cert-dir` (default `/data/credentials`):

   ```bash
   # Example via HA SSH add-on or terminal
   cp gardena-paa-cert.pem /data/credentials/gardena-paa-cert.pem
   ```

   If you run `python-matter-server` directly, use the directory passed as
   `--paa-root-cert-dir`.

3. **Restart the HA Matter Server** (add-on restart or
   `systemctl restart matter-server`).

4. **Leave "Enable test-net DCL usage" off** in the Matter Server settings.

5. **Commission the bridge** — HA validates the attestation chain against your locally
   added PAA root, no DCL lookup needed.

!!! note "Option B caveats"
    - The **"uncertified device"** prompt may still appear — it is controlled by the
      Certification Declaration (CD), which remains test-signed. Only a paid CSA
      certification removes it. Option B only eliminates the need for the *DCL toggle*.
    - Option B does **not** help with Apple Home or Google Home — they use their own
      trust models (see below). The per-ecosystem rules there remain unchanged.
    - Re-commissioning is required after switching between Option A and B.

### Apple Home — works, with a warning

Apple Home accepts the test vendor ID `0xFFF1`. During setup it shows
**"This accessory is not certified"** — tap **"Add Anyway"**. No extra configuration
needed. The own PAA root from Option B above has no effect here.

### Google Home — extra step required

Google Home is the strictest: a test-VID device only commissions if you register a
matching **Matter integration (test VID/PID) in the
[Google Home Developer Console](https://developers.home.google.com/)**. Without that
registration, Google Home rejects it as **"Not a Matter-certified device."** The own
PAA root has no effect here.

### Fully warning-free?

Only **real CSA certification** (paid membership, a registered vendor ID and
certification testing) removes the warning across all ecosystems — out of scope for a
hobby project. The recommended, fully-functional path is **Home Assistant** (Option A
or B above); you can then share the device to **Apple Home / Google Home** via Matter
**multi-admin**, where the same per-ecosystem rules above apply.

## Help

- **Gateway not found**: look up the IP address in your router and enter it manually.
- **Commissioning fails**: keep the gateway and the smart-home hub on the **same network**;
  mDNS/Bonjour must work on the network.
- **"Uncertified device" prompt**: see [Matter certificates](#matter-certificates) above.
- More details + technical background: [Manual](manual.md).

## MQTT frontend (optional)

The MQTT publisher runs alongside the Matter bridge — independently, both always active.
Enable it in the add-on configuration and point it at your MQTT broker.
Full setup guide: [MQTT](mqtt.md).
