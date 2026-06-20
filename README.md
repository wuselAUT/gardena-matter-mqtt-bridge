# GARDENA Matter & MQTT Bridge

> **Make the GARDENA smart Gateway speak Matter & MQTT — local, no cloud.**

🌍 **English** · [🇩🇪 Deutsch](README.de.md) · 📖 Full docs (EN/DE): **[Docs site](docs/index.md)**

Turn the **GARDENA smart Gateway (Art. 19005)** into a standalone **Matter device**:
your GARDENA devices appear locally in any Matter fabric (Home Assistant, Apple Home, Google Home)
— **no GARDENA cloud, no second server**. The Matter stack runs **directly on the gateway**.

On top of Matter, the bridge can **optionally publish every sensor value over MQTT** using Home
Assistant MQTT discovery (additive — Matter keeps working, no extra commissioning needed). So you
get your devices into Home Assistant **two ways**: native Matter, and rich MQTT entities.

> **Status: working.** The bridge automatically discovers every GARDENA device on the gateway
> (sensors, mowers and more — recognised from the model number, no configuration needed).
> Soil temperature, soil moisture, battery and mower status appear in Home Assistant.
> Devices that come or go during operation are picked up automatically.
> Binary ~1.9 MiB, runs on the gateway, reboot-proof.

> **⚠️ Disclaimer.** This is a **private hobby project** — **use entirely at your own risk**.
> It is **not affiliated with GARDENA or Husqvarna** and is neither supported nor endorsed by them.
> "GARDENA" and product names are trademarks of their respective owners and are used here only for
> identification. The software is provided **"as is", without any warranty**; you alone are
> responsible for any use and for any damage to devices, gateway, data or otherwise.
> See [LICENSE](LICENSE).

## Quick install (Home Assistant)

Add the repository to Home Assistant and install the **GARDENA Matter & MQTT Bridge** add-on —
no SSH, no building, no command line.

[![Add the add-on repository to your Home Assistant.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FwuselAUT%2Fgardena-matter-mqtt-bridge)

[![Open the GARDENA Matter & MQTT Bridge add-on in your Home Assistant.](https://my.home-assistant.io/badges/supervisor_addon.svg)](https://my.home-assistant.io/redirect/supervisor_addon/?addon=gardena_matter_bridge&repository_url=https%3A%2F%2Fgithub.com%2FwuselAUT%2Fgardena-matter-mqtt-bridge)

Full step-by-step walkthrough: **[Getting started](docs/getting-started.md)**.

## Documentation

The docs are **bilingual (English / German)** and built as a [MkDocs Material](https://squidfunk.github.io/mkdocs-material/)
site with a language switcher. **English is the canonical source.**

| | |
|---|---|
| 🚀 **[Getting started](docs/getting-started.md)** | From the box to a working Matter device — add-on install, no SSH/build knowledge. |
| 📘 **[Manual](docs/manual.md)** | Technical reference: SSH, build, flashing. |
| 📡 **[MQTT](docs/mqtt.md)** | The optional MQTT publisher and Home Assistant MQTT discovery. |
| 🔬 **[Technical status](docs/technical.md)** | Hardware, software architecture, feasibility verdict. |
| 🤝 **[Contributing](docs/contributing.md)** | What helps most at this early stage. |

### Build the docs site locally

```bash
pip install -r requirements-docs.txt
mkdocs serve         # http://127.0.0.1:8000  (language switcher, top right)
```

The site is published to GitHub Pages by the `docs` GitHub Action once Pages is enabled
(set the repository variable `ENABLE_PAGES=true` and select the "GitHub Actions" Pages source).

## Tested hardware

This bridge is developed and verified against my own, real GARDENA hardware:

- **GARDENA smart Gateway (Art. 19005)** — the Matter stack runs directly on this gateway.
- **GARDENA smart sensors** — soil moisture, temperature and battery. Every sensor in the test
  set is discovered automatically; there is no fixed device list in the code.
- **1 × GARDENA SILENO robotic mower** — status and battery, read-only as a Matter `vacuum`
  (no actuation, for garden safety).

Everything else in the device model — **water control / valves, irrigation control, the pressure
pump, the smart power plug and further sensor and mower variants** — is already modelled in code,
but **not yet verified against real hardware**, simply because I do not own those devices.

**If you want one of them supported and can lend or send me the hardware, I am happy to test it
and finish the integration.** Just open an issue and we'll sort it out.

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
                                           │  reads the LsDL filesystem (inotify)
                                           ▼
                              Matter bridge app (C++, MIPS cross-build)
                                           │
                                           ▼
                             Matter fabric (HA / Apple / Google)
```

We deploy into **slot B**; slot A stays as an untouched original fallback.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
