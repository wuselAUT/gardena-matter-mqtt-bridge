# GARDENA Matter Bridge

> **Make the GARDENA smart Gateway speak Matter — locally, without the cloud.**

Turn the **GARDENA smart Gateway (Art. 19005)** into a standalone **Matter device**: your
GARDENA devices show up locally in any Matter fabric (Home Assistant, Apple Home, Google
Home) — **no GARDENA cloud, no second server**. The Matter stack runs **directly on the
gateway**.

!!! success "Status: all GARDENA devices appear in Home Assistant"
    The bridge is fully functional on the gateway. After commissioning, **all GARDENA
    devices show up as child devices in HA**:

    - **2 × GARDENA smart Sensor** → soil temperature + battery (soil moisture from HA 2026.7)
    - **1 × GARDENA SILENO mower** → appears as a `vacuum` entity (read-only, no actuation)

    Build ✅ · Persistent install ✅ · Reboot-safe (systemd service) ✅ ·
    `BridgedDeviceBasicInformation` (0x0039) on every bridged endpoint ✅ ·
    Matter interview conformant ✅ · Binary 1.9 MiB stripped, RSS ~5 MiB.

    Re-pairing required if upgrading from an earlier build (cluster structure changed).

!!! tip "Just want to get it running?"
    → **[Getting Started](getting-started.md)** — add the HA add-on repository,
    enter the device ID and sticker password, done. No SSH, no building.
    Technical reference: [Manual](manual.md).

## Why this is plausible

Husqvarna ships an **official, buildable BSP** and supports custom firmware in practice:

- Open BSP / U-Boot / Yocto: [`husqvarnagroup/smart-garden-gateway-public`](https://github.com/husqvarnagroup/smart-garden-gateway-public)
- **A/B boot slots** + official recovery images → low brick risk
- Official **SSH access over LAN** (no UART, no exploit needed)

## Hardware (Art. 19005)

| Component | Value |
|---|---|
| SoC | MediaTek MT7688 (MIPS 24KEc @ 580 MHz) |
| RAM | 128 MiB |
| Flash | 8 MiB SPI NOR + 128 MiB SPI NAND |
| Radio | SiM3U167 (868 MHz, Lemonbeat) — handled by the gateway itself |

The binding constraints are **RAM (128 MiB)** at runtime and the writable **UBI flash**.

## The approach (Variant A)

```
GARDENA devices ──868 MHz Lemonbeat──▶ lemonbeatd (on the gateway)
                                           │  reads LsDL filesystem (inotify)
                                           ▼
                                 Matter bridge app (C++, MIPS cross-build)
                                           │
                                           ▼
                              Matter fabric (HA / Apple / Google)
```

Flashing goes into **Slot B**; Slot A stays as the untouched original fallback.

Full technical picture and open challenges: [Technical Background](technical.md).
User/build instructions: [Manual](manual.md).

## Feature status

| Feature | Status | Key results |
|---|---|---|
| Data layer recon | ✅ | LsDL filesystem confirmed as primary data source, no IPC socket needed |
| MIPS cross-build | ✅ | Cross-build proven, binary 1.9 MiB stripped, soft-float fp_abi=0 |
| SDK pinned | ✅ | On-device start, connectedhomeip v1.5.1.0 pinned |
| Sensors in HA | ✅ | 2 sensors, soil temperature + battery via `BridgedDeviceBasicInformation` |
| Mower as vacuum | ✅ | SILENO → `vacuum` entity (read-only, no actuation) |
| Persistent install | ✅ | Overlay install, systemd service, reboot-safe |
| Gateway web UI | ✅ | Static `matter.html` + compiled toggle (0 RAM idle) |
| Conformance harness | ✅ | chip-tool E2E harness + full wildcard interview check |
| MQTT frontend | ✅ | Parallel to Matter, HA MQTT-Discovery — [docs](mqtt.md) |
| HA add-on | ✅ | 1-click install via add-on repository, auto-deploy to gateway |

## Remaining challenges

1. **Soil moisture rendering**: `SoilMeasurement` cluster (0x0430) is in the bridge;
   HA renders it as `sensor.soil_moisture` starting with HA 2026.7.
2. **More device types**: water valves, smart Power, pumps — designed generically,
   untested (no hardware). Community contributions welcome.

## Contributing

See [Contributing](contributing.md). The project is early — recon data from your own gateway,
build experiments, and pointers to prior work are especially valuable.

## License

Apache License 2.0 — see [LICENSE](../LICENSE).
