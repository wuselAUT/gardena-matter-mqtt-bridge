# Technical Background & Feasibility

> Publicly curated version of the technical findings.

## Hardware (19005) — confirmed

Source: official Linux/U-Boot board support (`gardena-smart-gateway-mt7688.dts`, present in
mainline Linux **and** U-Boot).

| Component | Value |
|---|---|
| SoC | MediaTek **MT7688** (MIPS 24KEc @ **580 MHz**, 1T1R 802.11n Wi-Fi) |
| RAM | **128 MiB** DDR |
| Flash | **8 MiB** SPI NOR **+ 128 MiB** SPI NAND |
| RF co-processor | **SiM3U167** (868 MHz, Lemonbeat) |
| Ethernet | 10/100 |

There is **no more powerful GARDENA gateway** — the 19005 is the current and only model. The
binding constraint is **RAM (128 MiB)** at runtime and the **writable flash space** (UBI).

## Software architecture (current firmware)

- **Yocto Linux** (currently “scarthgap”/5.0 LTS), root as a **read-only squashfs** on UBI/NAND,
  **A/B boot slots**, writable overlay (`meta-readonly-rootfs-overlay`).
- **Proprietary daemons** (closed binaries, installable via OPKG):
    - `lemonbeatd` — speaks 868 MHz Lemonbeat to the devices (the RF layer)
    - `accessory-server`, `lwm2mserver` — device model / device management (LwM2M)
    - `cloudadapter` — cloud connection (today **AWS IoT**)
    - `fwrolloutd`, `gateway-config-backend/-frontend`
- The cloud part runs over **AWS IoT**, no longer over Seluxit/Shadoway. Older reverse
  engineering (2019) is largely obsolete for the current firmware.
- **RF device → gateway:** Lemonbeat (868 MHz), proprietary/encrypted — handled by the gateway
  and **does not** need to be re-implemented for Variant A.

## Open vs. proprietary — the decisive boundary

| Open (buildable, in the public BSP) | Closed (binary only, via OPKG) |
|---|---|
| Yocto BSP, U-Boot, kernel (`linux-yocto-tiny`) | `lemonbeatd` (RF) |
| Base image `gardena-image-foss-bnw` | `accessory-server`, `lwm2mserver` |
| Wi-Fi provisioning, tests (`meta-gardena`) | `cloudadapter` (AWS IoT) |
| `meta-distribution`, `meta-swupdate`, `meta-aws` | `fwrolloutd`, `gateway-config-*` |
| `meta-readonly-rootfs-overlay` | |

The real Lemonbeat radio firmware in the public repo is only a **closed dummy stub**. Even
Husqvarna’s own proprietary packages do **not all** fit into the writable filesystem — adding a
Matter stack requires a **UBI volume resize** (“must be done with great care”).

## Feasibility verdict (Variant A)

**Feasible** — thanks to the official BSP, A/B slots and official SSH access, better supported
than initially assumed. Three real challenges, in descending order of uncertainty:

1. **Local device interface — solved.** `lemonbeatd` maintains a self-describing filesystem under
   `/var/lib/lemonbeatd/` (the LsDL layer). The bridge reads device schemas and live sensor values
   directly from that directory tree — no IPC socket, no reverse engineering. Linux `inotify`
   delivers value updates instantly as files are written by the daemon.
2. **Matter port to MIPS.** `connectedhomeip` does not target MIPS 24KEc; doable as a recipe via
   the Yocto BSP, but a real porting project (OpenSSL/mbedTLS, softfloat). 580 MHz single core →
   commissioning/crypto slow, but functional.
3. **Space & RAM.** Grow the UBI volumes; 128 MiB RAM alongside the running daemons is tight.

## Rejected / alternative approaches

- **Variant B (separate server):** a local Matter server on an extra box + redirection. Simpler,
  but a separate server — does not match the goal. Stays as a fallback.
- **`shadoway.conf` → deGardenServer (obsolete):** an empty, abandoned shell; targets the old
  Seluxit protocol, which no longer applies on the current AWS IoT firmware.

## Data layer: how the bridge reads sensor values

`lemonbeatd` maintains a self-describing filesystem under `/var/lib/lemonbeatd/` — one
subdirectory per paired device (named by the device's SGTIN). Each device directory contains:

- **`Device_descriptionID_<n>.json`** — device metadata: serial number (SGTIN), name, type
- **`Value_description/<id>.json`** — value schema: name, data format, unit, range, permissions
- **`Value/Value_<id>r.json`** — current value: `{"id": N, "timestamp": <epoch_ms>, "value": "<str>"}`

The bridge discovers all paired devices at startup, reads their schemas, and loads the current
values from this directory tree. It then installs Linux `inotify` watches on each device's
`Value/` directory. When `lemonbeatd` writes a new measurement to disk, inotify delivers the
event immediately and the bridge updates the corresponding Matter attribute without any polling.

```
/var/lib/lemonbeatd/
  Device_descriptionID_1/
    Device_descriptionID_1.json        ← SGTIN, device name/type
    Value_description/
      12345.json                       ← schema: "soil_temperature", number, °C, –40..85
      12346.json                       ← schema: "soil_moisture", number, %, 0..100
      ...
    Value/
      Value_12345r.json                ← {"id":12345,"timestamp":1750123456789,"value":"31"}
      Value_12346r.json                ← {"id":12346,"timestamp":1750123456789,"value":"70"}
```

Key value names used:

| LsDL value name | Meaning | Unit |
|---|---|---|
| `soil_moisture` | Soil humidity | % |
| `soil_temperature` | Soil temperature | °C |
| `battery_level` | Battery level | % |
| `mower_status` | Mower operational status | numeric (0–18) |

The bridge opens **no IPC socket** — it never connects to `lemonbeatd-command.ipc` or any other
Unix domain socket belonging to the vendor daemons. Reads are purely passive filesystem reads.
The Gardena cloud connection (`cloudadapter`) stays active at all times — the bridge is purely
additive and does not interfere with app usage or OTA firmware updates.

## Matter device model

Each physical GARDENA smart Sensor maps to **one Matter Bridged Endpoint** (Soil Sensor, device
type 0x0045) with three clusters:

```
GARDENA smart Sensor (...0001)   ← one Matter device (Soil Sensor 0x0045)
  ├─ SoilMeasurement           (0x0430)  soil_moisture    [% direct, 0–100]
  ├─ TemperatureMeasurement    (0x0402)  soil_temperature [°C × 100]
  └─ PowerSource               (0x002F)  battery_level    [% × 2]
```

**Cluster 0x0430 (`SoilMeasurement`)** is part of the Matter 1.5 standard — available since
`connectedhomeip v1.5.1.0`. Home Assistant renders it as "Soil moisture" with `device_class MOISTURE`.
The `SoilMoistureMeasuredValue` attribute (0x0001) carries the value as a direct percentage (0–100),
**not** multiplied by 100 (unlike `TemperatureMeasurement`).

**Verified (chip-tool):**
```
soilmeasurement read soil-moisture-measured-value → SoilMoistureMeasuredValue: 70
temperaturemeasurement read measured-value        → MeasuredValue: 2900  (= 29 °C × 100)
powersource read bat-percent-remaining            → BatPercentRemaining: 106  (= 53 % × 2)
```

**Device identity:** the bridge identifies itself as **"Local Garden / Gardena Matter Bridge"**
with VendorId 0xFFF1 / ProductId 0x8000 (CSA test credentials from the SDK's example DAC).
Each bridged endpoint carries the genuine product name (e.g. "GARDENA smart Sensor (…0001)").

**Lawnmower endpoint:** the lawnmower is exposed as a *Robotic Vacuum Cleaner* device (0x0074)
with five clusters: `Identify` (0x0003, mandatory for the RVC device type), `RvcRunMode` (0x0054),
`RvcOperationalState` (0x0061), `PowerSource` (0x002F), and `Descriptor` (0x001D).
`SupportedModes` reports two modes: *Idle* (tag 0x4000) and *Cleaning* (tag 0x4001).
The endpoint is strictly **read-only**: no actuation path exists in the binary.
`Identify` has no physical effect (IdentifyType = None; write requests are rejected).

This matches how the official Gardena cloud app presents the sensor: one device with multiple
readings. The Matter model mirrors this exactly.

## Resources / links

- Official BSP: `github.com/husqvarnagroup/smart-garden-gateway-public`
- Source packages: `opensource.smart.gardena.dev`
- Official restore images: `gateway.iot.sg.dss.husqvarnagroup.net`
- Mainline DTS: `gardena-smart-gateway-mt7688.dts` (Linux & U-Boot)
- Old RE wiki (2019): `github.com/gardena-smart-reverse-engineering` (Lemonbeat/HW useful, cloud
  part obsolete)
- Matter SDK: `connectedhomeip`
- Local websocket daemon (reference for device model): `github.com/husqvarnagroup/smart-garden-gateway-websocketd`
- Device model reference: `github.com/cloudless-garden/gardena-smart-local-api`
