# Manual

> Usage and build guide. The **technical reference** behind Getting Started.

!!! warning "Warranty"
    Custom firmware voids the warranty. Every step targets the **inactive A/B slot** so the
    original stays bootable. **At your own risk.**

!!! tip "Just want to get it running?"
    → **[Getting Started](getting-started.md)** takes you from the box to a running Matter device
    in **two simple paths** (Home Assistant **or** a standalone installer) — no SSH/build
    knowledge. **This manual is the technical reference** behind it (SSH, build, flashing,
    adapter, Slot-B advanced path).

## 1. Prerequisites

- GARDENA smart Gateway **Art. 19005**, on the LAN, powered.
- The **device ID** from the bottom (format `GARDENA-xxxxxx`). The SSH password is the
  **first 8 characters of the ID**.
- An SSH key pair (`ssh-keygen -t ed25519`).
- For the firmware build: a **Linux host** (native, VM or WSL2) — Yocto does not build on Windows.

## 2. Enable SSH access

The official way via the gateway’s local HTTPS API — no UART, no exploit:

```bash
gateway=GARDENA-123456
password=1234abcd          # first 8 characters of the ID

# 1) get a session
session=$(curl -H 'Content-Type: application/json' \
  -d '{"password": "'"$password"'"}' --insecure https://$gateway/login | jq -r .session)

# 2) register your own public key
curl -X POST -H "X-session: $session" -H 'Content-Type: application/json' \
  -d '{"key": "'"$(cat ~/.ssh/id_ed25519.pub)"'"}' --insecure https://$gateway/ssh_access_credentials

# 3) enable SSH
curl -X PUT -H "X-session: $session" -H 'Content-Type: application/json' \
  -d '{"enable": true}' --insecure https://$gateway/ssh_access_enable

# 4) log in
ssh root@$gateway
```

**UART fallback:** port **J7**, **115200 8N1, 3.3 V**; press **“X”** in the U-Boot shell right
after power-on.

## 3. Recon — get to know the device

After the first login, capture the resource and interface situation:

```bash
cat /proc/cpuinfo          # SoC
free -m                    # free RAM at runtime (binding constraint)
df -h ; cat /proc/mtd      # flash / UBI partitions
ps ; ss -tlnp              # running daemons, open local ports/sockets
```

Of particular interest: whether `lwm2mserver` / `accessory-server` offer a **local** interface
(port/socket/D-Bus) — that is the planned docking point of the bridge.

## 4. Build & flash custom firmware

```bash
# Build (on the Linux host)
git clone --recurse-submodules https://github.com/husqvarnagroup/smart-garden-gateway-public
cd smart-garden-gateway-public
scripts/bbwrapper.sh mt7688 gardena-image-foss-bnw linux-yocto-tiny
```

Flash via U-Boot + TFTP into the **inactive** A/B slot:

```
run do_toggle_bootslot
env save
ubi part nand
dhcp fitImage-gardena-sg-mt7688.bin && ubi write ${fileaddr} kernel${bootslot} ${filesize}
dhcp gardena-image-foss-bnw-gardena-sg-mt7688.squashfs-xz && ubi write ${fileaddr} rootfs${bootslot} ${filesize}
reset
```

## 5. Rollback / recovery

Switch the boot slot back — the original in Slot A stays untouched:

```bash
fw_setenv bootslot $(( 1 - $(fw_printenv -n bootslot) )); reboot
```

Official images for restoring live on Husqvarna’s server
(`gateway.iot.sg.dss.husqvarnagroup.net`).

## 6. gardena-adapter: deploy & use

The **gardena-adapter** is a Python bridge between the internal `lwm2mserver` EventBus and a
stable **local JSON API** (Unix socket). It is the building block the later Matter bridge is
built on: it provides device inventory, connection status and sensor resources without touching
the running stack. Read-only.

### 6.1 Prerequisites

- GARDENA smart Gateway 19005 with firmware ≥ 10.4.4 (`bnw-zephyr` image)
- SSH access set up (→ §2)
- Python 3.12 on the device (already pre-installed)
- `lwm2mserver` running (standard operation)

### 6.2 Copy the adapter onto the gateway

The adapter lives in the private workshop repo under `adapter/`.
Copy it onto the gateway (no flash, no OPKG needed — overlay or /tmp is enough for development):

```bash
# On the development machine (Linux/WSL):
# Transfer files one by one via SSH pipe (scp/sftp is not available on this device)
GATEWAY=root@<gateway-ip>   # example IP — replace with your gateway's address
DEST=/tmp/gardena-adapter

ssh $GATEWAY "mkdir -p $DEST/adapter"

for f in __init__.py eventbus_client.py state.py api.py gardena_adapter.py; do
    python3 -c "
import base64, sys
data = open('adapter/$f','rb').read()
b64  = base64.b64encode(data).decode()
print(f\"python3 -c \\\"import base64; open('$DEST/adapter/$f','wb').write(base64.b64decode('{b64}'))\\\"\")
" | ssh $GATEWAY sh
done
```

!!! tip "Alternative"
    On systems with `rsync` over the SSH protocol, or where `/usr/libexec/sftp-server` is
    present, `scp -r adapter/ $GATEWAY:$DEST/` is enough.

### 6.3 Start the adapter

```bash
ssh root@<gateway-ip>

# Configuration
PYTHONPATH=/tmp/gardena-adapter

# In the foreground (development)
cd /tmp/gardena-adapter
PYTHONPATH=/tmp/gardena-adapter python3 -m adapter.gardena_adapter \
    --socket /tmp/gardena-adapter.sock \
    --log-level INFO

# In the background (dev operation)
PYTHONPATH=/tmp/gardena-adapter python3 -m adapter.gardena_adapter \
    --socket /tmp/gardena-adapter.sock &
```

The adapter:

1. Reads the inventory via `list-lemonbeat-devices` (at start + every 5 min)
2. Connects to the EventBus PUB socket and receives device events passively
3. Opens the local JSON API socket at `--socket` (default: `/tmp/gardena-adapter.sock`)

Log messages appear on stderr. It is ready when this line appears:

```
GardenaAdapter: alle Komponenten gestartet, API auf /tmp/gardena-adapter.sock
```

**Quick verification test** (`--once`, single run + JSON report):

```bash
PYTHONPATH=/tmp/gardena-adapter python3 -m adapter.gardena_adapter --once
# Exit code 0 = all basic checks OK
```

### 6.4 Query the local API

The API speaks **newline JSON** (send one JSON line, receive one JSON line), consistent with the
EventBus style.

**General query pattern:**

```bash
# With Python (recommended)
python3 -c "
import sys, json, socket
sys.path.insert(0, '/tmp/gardena-adapter')
from adapter.api import query_api
result = query_api({'cmd': 'COMMAND', ...})
print(json.dumps(result, indent=2))
"

# Directly with echo + socat (if socat is available)
echo '{"cmd":"health"}' | socat - UNIX-CONNECT:/tmp/gardena-adapter.sock
```

#### `list_devices` — list all devices

```bash
python3 -c "
import sys, json
sys.path.insert(0, '/tmp/gardena-adapter')
from adapter.api import query_api
print(json.dumps(query_api({'cmd':'list_devices'}), indent=2))
"
```

Example response:

```json
[
  {"address":"fc00::6:0000:0000:0001","name":"SG Mower LONA","sgtin":"300000...","online":null,"last_seen_ts":null},
  {"address":"fc00::6:0000:0000:0002","name":"SG Sensor 2","sgtin":"300001...","online":false,"last_seen_ts":1781471595},
  {"address":"fc00::6:0000:0000:0003","name":"SG Sensor 2","sgtin":"300001...","online":false,"last_seen_ts":1781471595}
]
```

#### `read` — read a resource (EventBus proxy)

```bash
# connection_status (locally cached, immediate response)
python3 -c "
import sys, json
sys.path.insert(0, '/tmp/gardena-adapter')
from adapter.api import query_api
result = query_api({
    'cmd': 'read',
    'address': 'fc00::6:0000:0000:0002',   # sensor address
    'path': 'connection_status'
})
print(json.dumps(result, indent=2))
"
```

Example response:

```json
{
  "success": true,
  "payload": {
    "0": {"online": {"vb": false, "ts": 1781471595}},
    "_urn": "urn:oma:lwm2m:x:28171"
  }
}
```

- `online.vb`: `true` = device awake, `false` = sleeping (wake-on-radio)
- `online.ts`: Unix epoch of the last connection check

```bash
# IPSO resource (requires a device wakeup, up to 30s wait)
python3 -c "
import sys, json
sys.path.insert(0, '/tmp/gardena-adapter')
from adapter.api import query_api
result = query_api({
    'cmd': 'read',
    'address': 'fc00::6:0000:0000:0002',
    'path': '/3303/0/5700'    # IPSO Temperature Sensor Value
})
print(json.dumps(result, indent=2))
"
# If the device is sleeping: {"success": false, "error": "Device '...' not connected"}
```

#### `get_device` — full device cache snapshot

```bash
python3 -c "
import sys, json
sys.path.insert(0, '/tmp/gardena-adapter')
from adapter.api import query_api
result = query_api({
    'cmd': 'get_device',
    'address': 'fc00::6:0000:0000:0002'
})
print(json.dumps(result, indent=2))
"
```

The response contains: `address`, `name`, `sgtin`, `online`, `last_seen_ts`,
`resources` (last-seen resources), `last_sequence`.

#### `health` — adapter status

```bash
python3 -c "
import sys, json
sys.path.insert(0, '/tmp/gardena-adapter')
from adapter.api import query_api
print(json.dumps(query_api({'cmd':'health'}), indent=2))
"
```

Example response:

```json
{
  "eventbus_connected": true,
  "device_count": 3,
  "uptime_s": 46.9,
  "last_sequence": 18
}
```

### 6.5 Known limits

| Limitation | Explanation |
|---|---|
| Read-only | No write/execute commands; the mower is not actively addressed |
| IPSO mapping incomplete | Sensor resources (temperature, humidity) can only be mapped after a real wakeup cycle |
| `online: null` right after start | Filled only after the first EventBus event or `read connection_status` |
| No persistent state | Empty cache on adapter restart (inventory back after ~5s) |

## 7. Use the Matter bridge

### 7.1 Supported devices and data points

The Matter bridge automatically discovers **all GARDENA devices** connected to the gateway
and bridges them based on the model number. Supported device types:

| Device type | Matter representation | Status |
|---|---|---|
| smart Sensor II (Art. 19040) | Soil Sensor (SoilMeasurement + Temperature + Battery) | verified |
| smart Sensor (Art. 18845) | Soil Sensor + Illuminance | mapped, not yet hw-verified |
| Robotic mower (SILENO / LONA) | Robotic Vacuum Cleaner (status + battery, read-only) | verified |
| Water Control / Irrigation Control | Water Valve (status only, read-only) | mapped, not yet hw-verified |
| smart Power (plug) | On/Off Plug-in Unit (status only, read-only) | mapped, not yet hw-verified |
| Pump | Pump (status only, read-only) | mapped, not yet hw-verified |
| Unknown model | BridgedBasicInfo-only stub (reachable indicator, no data) | — |

Devices that appear on the gateway while the bridge is running are added dynamically
(no restart required). Devices that disappear are removed from the Matter fabric accordingly.

### 7.2 Device naming

Each sensor is assigned a unique, human-readable name based on the official product name and
a short identifier derived from its internal hardware ID:

- `GARDENA smart Sensor (...0001)`
- `GARDENA smart Sensor (...0002)`

You can rename these freely in Home Assistant, Apple Home or Google Home after commissioning.
The bridge name is only the initial label.

### 7.3 Build the bridge

#### Prerequisites

- Build host: Linux (native, VM or WSL2), Ubuntu 22.04+
- The Husqvarna Yocto SDK (OldSoft toolchain) built from the BSP — see the private workshop
  repo for full build instructions
- SSH access to the gateway (→ §2)

#### Matter SDK

The bridge is built against **connectedhomeip `v1.5.1.0`** (tag `v1.5.1.0`,
SHA `abcc720b48c5e59c0edcfe65c516f76ca9448aa3`). This is the stable Matter 1.5 SDK — the first
version to include the `SoilMeasurement` cluster (0x0430) needed for correct soil humidity
mapping in future releases.

Clone:

```bash
git clone --branch v1.5.1.0 --depth 1 --recurse-submodules --shallow-submodules \
    https://github.com/project-chip/connectedhomeip.git ~/gardena-matter-build/connectedhomeip
```

#### Build

```bash
# On the build host (e.g. ubuntu-server):
bash matter/build_bridge_app.sh ~/gardena-matter-build 3
```

This runs the GN + ninja cross-build with the OldSoft MIPS toolchain. The result is a stripped
MIPS soft-float binary (~2 MiB, soft-float fp_abi=0 — required by the MT7688 kernel).

### 7.4 Persistent installation (recommended — survives reboot)

The **persistent install** places the bridge in the gateway’s writable overlay
(`/usr/local/lib/gardena-matter/`) and registers it as a systemd service that starts
automatically on every boot. The GARDENA cloud connection and OTA updates are unaffected.

```bash
# From the build host (or any machine with SSH access to the gateway):
bash matter/install_bridge.sh ~/gardena-matter-build/out/mips-bridge/chip-bridge-app.stripped <gateway-ip>
```

The script:
1. Stops any running bridge instance cleanly
2. Copies binary + C++ runtime libraries to `/usr/local/lib/gardena-matter/` (persistent overlay)
3. Writes a launcher script (`runbridge.sh`) that sets `LD_LIBRARY_PATH` and passes `--KVS`
4. Installs `/etc/systemd/system/gardena-matter-bridge.service` and runs `systemctl enable`
5. The service’s `ExecStartPre` sets the `iptables`/`ip6tables` firewall rule for UDP 5540
   (Matter commissioning port) on every boot — idempotent, no vendor config files touched
6. Starts the service

The commissioning data (pairing fabric) lives in `/var/lib/gardena-matter/chip_kvs` —
it **survives the install and every subsequent reboot**. No re-pairing required.

**To uninstall** (clean rollback, commissioning data preserved):

```bash
bash matter/uninstall_bridge.sh <gateway-ip>
```

This stops the service, removes the binary/libs/launcher, disables the unit, and removes the
firewall rules. The KVS (`/var/lib/gardena-matter/chip_kvs`) is intentionally left in place
— if you reinstall the bridge later it will re-join the same Matter fabric without re-pairing.

**Verified behaviour after a gateway reboot:**
- Bridge autostart: `active (running)` without any manual action
- Firewall rule: UDP 5540 ACCEPT active (set by `ExecStartPre`)
- HA reconnects via CASE session resumption — no QR code / manual code entry required
- mDNS: the bridge coexists with the vendor `mdnsd` (bridge uses its own mDNS on `eth0`/`wlan0`;
  PPP interface `ppp0` is filtered out to avoid mesh-internal advertisement)

### 7.4a Firmware updates — what to expect

The bridge installation lives in the gateway's **writable overlay** (a separate UBI volume that is
not touched by normal firmware updates). A regular Husqvarna gateway OTA swaps only the read-only
squashfs root; the overlay — and therefore the bridge binary, configuration, and pairing data —
**survives intact by design**.

A built-in restore service (`gardena-matter-restore.service`) runs on every boot and automatically
restores any missing files from a local backup copy. In normal OTA scenarios no manual action is
needed.

**After a firmware update, it is good practice to quickly verify:**
- The bridge service is still active: `systemctl is-active gardena-matter-bridge`
- The web UI is reachable: `https://<gateway-ip>/assets/matter.html` responds with HTTP 200
- Home Assistant still shows your devices with plausible sensor values

**Honest boundary:** A factory reset (or resurrection reset) wipes the entire overlay,
including the bridge and its backup. In that case a fresh installation is required and
re-pairing in Home Assistant is needed. This is the only scenario where the bridge does
not survive a gateway operation automatically.

### 7.5 Temporary deploy (development / quick test)

If you just want to test a new build without making it permanent:

```bash
bash matter/deploy_bridge.sh ~/gardena-matter-build/out/mips-bridge/chip-bridge-app.stripped <gateway-ip>
```

The bridge runs from `/tmp` and disappears on the next reboot. The KVS
(`/var/lib/gardena-matter/chip_kvs`) survives even in this mode — no re-pairing needed after
re-running `deploy_bridge.sh`.

The bridge reads sensor data from the lemonbeatd device-description files under
`/var/lib/lemonbeatd/` using inotify — no IPC socket is opened, no cloud traffic is generated.
The Gardena cloud connection stays active and fully undisturbed.

### 7.6 Commission into Home Assistant

1. Note the QR payload or manual code from the deploy/install output.
2. Open the browser UI (`https://<gateway-ip>/assets/matter.html`) and log in.
3. Click **"Activate Pairing"** — a 180-second commissioning window opens on the bridge.
4. In HA: **Settings → Devices & Services → Matter → Add device** (while the countdown is running).
5. Scan the QR code **or** enter the manual code.
6. Expected result: **two devices** appear — `GARDENA smart Sensor (...0001)` and
   `GARDENA smart Sensor (...0002)` — each with three entities (temperature, humidity, battery).

> **Without the browser UI:** The commissioning window is also open immediately after the bridge
> starts (first boot / after restart). In that case you can skip the "Activate Pairing" step and
> commission directly from the deploy/install log output.

> **Note:** If an entity is missing after pairing, the bridge may not have received the first
> sensor reading yet. The sensors sleep most of the time and report approximately every 30 minutes.
> Re-pairing after a short wait (or after tapping the sensor to wake it) fixes this.

### 7.7 Commission into Apple Home / Google Home

Apple Home and Google Home support Matter commissioning from the same QR code or manual code.
The bridge is a standard Matter bridge device — no vendor-specific app required.

### 7.8 Known limits

| Limitation | Details |
|---|---|
| Sensors sleep | Soil sensors report every ~30 min (battery-operated). Values in HA may lag behind. |
| Battery readings infrequent | Battery level updates ~once per hour. The bridge uses 50 % as a placeholder until the first real reading arrives. |
| Soil humidity label | HA shows "Humidity" (Matter standard label) — the value is soil moisture. The bridge uses the SoilMeasurement cluster (0x0430, Matter 1.5+) for correct mapping. |
| RF link quality | Not exposed via Matter (no standard cluster for this). |
| mDNS coexistence | The bridge uses minimal-mDNS alongside the vendor `mdnsd`. Stable in practice; a cleaner platform-mDNS integration (via `astro-dnssd`) is planned for a future release. |
| Actuation (valve open/close, pump, mower start) | Read-only / status only in this release. Actuation is a planned follow-up. |
| Non-testset devices (Water Control, Pump, Plug, Sensor I) | Mapped to the correct Matter device type but not yet hardware-verified. |
| Commissioning in HA: user action | The QR/code pairing step must be performed by the user — the bridge provides the data, the user does the pairing. |
