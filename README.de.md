# GARDENA Matter & MQTT Bridge

> **Bring das GARDENA smart Gateway dazu, Matter & MQTT zu sprechen — lokal, ohne Cloud.**

[🌍 English](README.md) · 🇩🇪 **Deutsch** · 📖 Vollständige Doku (EN/DE): **[Doku-Site](docs/index.de.md)**

Das **GARDENA smart Gateway (Art. 19005)** zu einem eigenständigen **Matter-Gerät** machen:
GARDENA-Geräte erscheinen lokal in jedem Matter-Fabric (Home Assistant, Apple Home, Google Home)
— **ohne GARDENA-Cloud, ohne zweiten Server**. Der Matter-Stack läuft **direkt auf dem Gateway**.

Zusätzlich zu Matter kann die Bridge **optional jeden Sensorwert per MQTT veröffentlichen** — über
die Home-Assistant-MQTT-Discovery (additiv — Matter läuft weiter, kein zusätzliches Commissioning
nötig). So bekommst du deine Geräte **auf zwei Wegen** in Home Assistant: nativ als Matter und als
reichhaltige MQTT-Entitäten.

> **Status: funktionsfähig.** Die Bridge erkennt automatisch alle GARDENA-Geräte am Gateway
> (Sensoren, Mäher und weitere — automatisch anhand der Modellnummer, keine Konfiguration nötig).
> Bodentemperatur, Bodenfeuchte, Batterie und Mäherstatus erscheinen in Home Assistant.
> Geräte, die während des Betriebs hinzukommen oder verschwinden, werden automatisch berücksichtigt.
> Binary 1,9 MiB, läuft auf dem Gateway, reboot-fest.

> **⚠️ Haftungsausschluss.** Dies ist ein **privates Hobby-Projekt** — die **Nutzung erfolgt vollständig auf
> eigene Gefahr**. Es steht in **keiner Verbindung zu GARDENA oder Husqvarna** und wird von diesen weder
> unterstützt noch befürwortet. „GARDENA" und Produktnamen sind Marken ihrer jeweiligen Inhaber und dienen
> hier nur der Identifikation. Die Software wird **„wie besehen", ohne jegliche Gewährleistung** bereitgestellt;
> für jede Nutzung sowie für etwaige Schäden an Geräten, Gateway, Daten oder Sonstigem bist allein du
> verantwortlich. Siehe [LICENSE](LICENSE).

## Schnell-Installation (Home Assistant)

Repository zu Home Assistant hinzufügen und das Add-on **GARDENA Matter & MQTT Bridge** installieren —
kein SSH, kein Bauen, keine Kommandozeile.

[![Add-on-Repository zu Home Assistant hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FwuselAUT%2Fgardena-matter-mqtt-bridge)

[![GARDENA Matter & MQTT Bridge Add-on in Home Assistant öffnen](https://my.home-assistant.io/badges/supervisor_addon.svg)](https://my.home-assistant.io/redirect/supervisor_addon/?addon=gardena_matter_bridge&repository_url=https%3A%2F%2Fgithub.com%2FwuselAUT%2Fgardena-matter-mqtt-bridge)

Vollständige Schritt-für-Schritt-Anleitung: **[Inbetriebnahme](docs/getting-started.de.md)**.

## Dokumentation

Die Doku ist **zweisprachig (Englisch / Deutsch)** und wird als [MkDocs-Material](https://squidfunk.github.io/mkdocs-material/)-Site
mit Sprachschalter gebaut. **Englisch ist die kanonische Quelle.**

| | |
|---|---|
| 🚀 **[Inbetriebnahme](docs/getting-started.de.md)** | Vom Karton zum funktionierenden Matter-Gerät — Add-on-Install, ohne SSH-/Build-Wissen. |
| 📘 **[Handbuch](docs/manual.de.md)** | Technische Referenz: SSH, Build, Flashen. |
| 📡 **[MQTT](docs/mqtt.de.md)** | Der optionale MQTT-Publisher und die Home-Assistant-MQTT-Discovery. |
| 🔬 **[Technische Lage](docs/technical.de.md)** | Hardware, Software-Architektur, Machbarkeits-Verdict. |
| 🤝 **[Mitwirken](docs/contributing.de.md)** | Was in dieser frühen Phase am meisten hilft. |

### Doku-Site lokal bauen

```bash
pip install -r requirements-docs.txt
mkdocs serve         # http://127.0.0.1:8000  (Sprachschalter oben rechts)
```

Die Site wird über die `docs`-GitHub-Action nach GitHub Pages veröffentlicht, sobald Pages aktiviert
ist (Repo-Variable `ENABLE_PAGES=true` setzen und als Pages-Quelle „GitHub Actions" wählen).

## Getestete Hardware

Diese Bridge wird gegen meine eigene, echte GARDENA-Hardware entwickelt und verifiziert:

- **GARDENA smart Gateway (Art. 19005)** — der Matter-Stack läuft direkt auf diesem Gateway.
- **GARDENA smart Sensoren** — Bodenfeuchte, Temperatur und Batterie. Alle Sensoren im Testset
  werden automatisch erkannt; keine feste Geräteliste im Code.
- **1 × GARDENA SILENO Mähroboter** — Status und Batterie, read-only als Matter-`vacuum`
  (keine Aktuierung, aus Garten-Sicherheit).

Alles andere im Geräte-Modell — **Water Control / Ventile, Irrigation Control, die Druckpumpe,
die smart-Power-Steckdose und weitere Sensor- und Mäher-Varianten** — ist im Code bereits
modelliert, aber **noch nicht an echter Hardware verifiziert**, schlicht weil ich diese Geräte
nicht besitze.

**Wenn du eines davon unterstützt haben möchtest und mir die Hardware leihen oder schicken kannst,
teste ich sie gerne und mache die Integration fertig.** Einfach ein Issue aufmachen, dann klären wir das.

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

## Lizenz

Apache License 2.0 — siehe [LICENSE](LICENSE).
