# Roadmap

Where this project stands and where it is going. This is a community research project — dates
are intentionally omitted, and scope can change. Status reflects what has actually been verified
on real hardware.

> **What this is:** software that makes the GARDENA smart Gateway expose your GARDENA devices as
> local **Matter** devices — usable in Home Assistant, Apple Home, Google Home, and any Matter
> controller, **without the cloud**. The GARDENA cloud and app keep working unchanged (Matter runs
> *in addition*, locally; firmware updates and the app are never cut off).

## ✅ Working today

- **Matter bridge runs directly on the gateway** — no extra hardware, no separate server, fully local.
- **GARDENA smart Sensor II (model 19040) appears as a proper Matter Soil Sensor** — soil moisture
  via the standard **SoilMeasurement cluster (0x0430)**, visible in Home Assistant as "Soil moisture".
  Temperature and battery are also live. Device identity: **"Local Garden / Gardena Matter Bridge"**.
- **Reboot-proof:** the bridge installs into the writable overlay, auto-starts after a power cycle,
  and keeps its pairing (no re-commissioning needed). No firmware flashing — fully reversible.
- **Automated regression harness:** a one-command chip-tool-based test suite verifies all sensor
  attributes against live values from the gateway (oracle diff = 0 for all values).
- **Stable Matter SDK base:** built on the official **stable release v1.5.1.0**, reproducible builds.
- **MQTT frontend** — runs alongside Matter; publishes sensor values to any MQTT broker with
  Home Assistant auto-discovery. Diagnostic values (RF link quality, mower runtime, error codes)
  that don't fit a Matter cluster appear as HA `sensor` entities. → [MQTT documentation](mqtt.md)

## 🔜 Next

- **More device types.** Water valves, smart power sockets, pumps, and robotic mowers (mapped to the
  Matter robotic-vacuum profile, so start/stop/pause/return-home work as real controls).
- **Long-term coexistence hardening** — mDNS via the vendor's system service (no own responder),
  resilient to vendor firmware updates.

## 🧭 Later

- **Easy install paths** for non-technical users — a Home Assistant add-on and a guided installer,
  so no manual SSH or building is required.

## How GARDENA devices map to Matter

Each known GARDENA product becomes one Matter device. High-level view (✅ = proven live, 🟡 = device
verified / planned, ⚪ = planned, not yet hardware-tested):

| GARDENA device | Appears in Matter as | You get | Status |
|---|---|---|---|
| smart Sensor / Sensor II | Soil Sensor | soil moisture, temperature, (light), battery | ✅ (soil moisture as SoilMeasurement 0x0430 · temp + battery chip-tool-verified) |
| Water Control | Water Valve | open/close valve + timer, battery | ⚪ |
| smart Irrigation Control | 6 × Water Valve (one device) | six independent valves | ⚪ |
| smart Power | On/Off plug | switchable socket | ⚪ |
| Pump / Pressure Pump | Pump | pressure & flow sensors (+ on/off) | ⚪ |
| Robotic mower (SILENO) | Robotic Vacuum Cleaner profile | **status (mowing/parked/charging) + battery — read-only**; start/stop later | ✅ (Matter status + battery chip-tool-verified; HA vacuum entity live; write control planned) |

Diagnostic values without a Matter standard (radio link quality, mower runtime) are published via
the MQTT frontend as `diagnostic` entities in Home Assistant. → [MQTT documentation](mqtt.md)

## Tracking progress

Development happens in the open. Issues and contributions are welcome — see
[Contributing](contributing.md).
