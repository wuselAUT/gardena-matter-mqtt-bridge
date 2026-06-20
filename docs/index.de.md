# GARDENA Matter Bridge

> **Mach das GARDENA smart Gateway Matter-fähig — lokal, ohne Cloud.**

Das **GARDENA smart Gateway (Art. 19005)** zu einem eigenständigen **Matter-Gerät** machen:
GARDENA-Geräte erscheinen lokal in jedem Matter-Fabric (Home Assistant, Apple Home, Google
Home) — **ohne GARDENA-Cloud, ohne zweiten Server**. Der Matter-Stack läuft **direkt auf dem
Gateway**.

!!! success "Status: alle GARDENA-Geräte erscheinen in Home Assistant"
    Die Bridge ist vollständig funktionsfähig. Nach dem Commissioning erscheinen **alle
    GARDENA-Geräte als Kind-Geräte in HA**:

    - **2 × GARDENA smart Sensor** → Bodentemperatur + Batterie (Bodenfeuchte ab HA 2026.7)
    - **1 × GARDENA SILENO Mäher** → erscheint als `vacuum`-Entity (read-only, keine Aktuierung)

    Build ✅ · Permanente Installation ✅ · Reboot-fest (systemd-Service) ✅ ·
    `BridgedDeviceBasicInformation` (0x0039) auf jedem gebridgten Endpoint ✅ ·
    Matter-Interview konform ✅ · Binary 1,9 MiB stripped, RSS ~5 MiB.

    Re-Pairing nötig bei Upgrade von einem älteren Build (Cluster-Struktur geändert).

!!! tip "Willst du es einfach in Betrieb nehmen?"
    → **[Inbetriebnahme](getting-started.de.md)** — Add-on-Repository hinzufügen,
    Geräte-ID + Aufkleber-Passwort eingeben, fertig. Kein SSH, kein Bauen.
    Technische Referenz: [Handbuch](manual.de.md).

## Warum das plausibel ist

Husqvarna liefert ein **offizielles, baubares BSP** und unterstützt Custom-Firmware praktisch:

- Offenes BSP / U-Boot / Yocto: [`husqvarnagroup/smart-garden-gateway-public`](https://github.com/husqvarnagroup/smart-garden-gateway-public)
- **A/B-Boot-Slots** + offizielle Recovery-Images → geringes Brick-Risiko
- Offizieller **SSH-Zugang über LAN** (kein UART, kein Exploit nötig)

## Hardware (Art. 19005)

| Komponente | Wert |
|---|---|
| SoC | MediaTek MT7688 (MIPS 24KEc @ 580 MHz) |
| RAM | 128 MiB |
| Flash | 8 MiB SPI NOR + 128 MiB SPI NAND |
| Funk | SiM3U167 (868 MHz, Lemonbeat) — wird vom Gateway selbst gehandhabt |

Die bindenden Engpässe sind **RAM (128 MiB)** zur Laufzeit und der beschreibbare **UBI-Flash**.

## Der Ansatz (Variante A)

```
GARDENA-Geräte ──868 MHz Lemonbeat──▶ lemonbeatd (auf dem Gateway)
                                           │  liest LsDL-Dateisystem (inotify)
                                           ▼
                              Matter-Bridge-App (C++, MIPS-Cross-Build)
                                           │
                                           ▼
                             Matter-Fabric (HA / Apple / Google)
```

Geflasht wird in **Slot B**; Slot A bleibt als unangetastetes Original-Fallback.

Volle technische Lage und offene Herausforderungen: [Technische Lage](technical.de.md).
Nutzungs-/Build-Anleitung: [Handbuch](manual.de.md).

## Feature-Status

| Feature | Status | Ergebnis |
|---|---|---|
| Datenschicht-Recon | ✅ | LsDL-Dateisystem als primäre Datenquelle bestätigt, kein IPC-Socket nötig |
| MIPS-Cross-Build | ✅ | Cross-Build bewiesen, Binary 1,9 MiB stripped, fp_abi=0 Soft-Float |
| SDK gepinnt | ✅ | On-Device-Start, connectedhomeip v1.5.1.0 gepinnt |
| Sensoren in HA | ✅ | 2 Sensoren, Bodentemperatur + Batterie via `BridgedDeviceBasicInformation` |
| Mäher als vacuum | ✅ | SILENO → `vacuum`-Entity (read-only, keine Aktuierung) |
| Permanente Installation | ✅ | Overlay-Install, systemd-Service, reboot-fest |
| Gateway-Web-UI | ✅ | Statische `matter.html` + kompilierter Toggle (0 RAM idle) |
| Konformitäts-Harness | ✅ | chip-tool E2E-Harness + Voll-Wildcard-Interview-Check |
| MQTT-Frontend | ✅ | Parallel zu Matter, HA MQTT-Discovery — [Doku](mqtt.de.md) |
| HA-Add-on | ✅ | 1-Klick-Install per Add-on-Repository, Auto-Deploy auf das Gateway |

## Verbleibende Herausforderungen

1. **Bodenfeuchte-Anzeige**: `SoilMeasurement`-Cluster (0x0430) ist in der Bridge;
   HA rendert ihn als `sensor.soil_moisture` ab HA 2026.7.
2. **Weitere Gerätetypen**: Wasserventile, smart Power, Pumpen — generisch designt,
   aber ungetestet (keine Hardware). Community-Beiträge willkommen.

## Mitwirken

Siehe [Mitwirken](contributing.de.md). Das Projekt ist früh — Recon-Daten vom eigenen Gateway,
Build-Experimente und Hinweise auf Vorarbeiten sind besonders wertvoll.

## Lizenz

Apache License 2.0 — siehe [LICENSE](../LICENSE).
