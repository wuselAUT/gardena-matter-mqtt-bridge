# Roadmap

Wo das Projekt steht und wohin es geht. Dies ist ein Community-Forschungsprojekt — Daten sind
bewusst weggelassen, und der Umfang kann sich ändern. Der Status spiegelt wider, was tatsächlich
auf echter Hardware verifiziert wurde.

> **Worum es geht:** Software, die das GARDENA smart Gateway dazu bringt, deine GARDENA-Geräte als
> lokale **Matter**-Geräte bereitzustellen — nutzbar in Home Assistant, Apple Home, Google Home und
> jedem Matter-Controller, **ohne Cloud**. Die GARDENA-Cloud und die App funktionieren unverändert
> weiter (Matter läuft *zusätzlich*, lokal; Firmware-Updates und die App werden nie gekappt).

## ✅ Funktioniert heute

- **Die Matter-Bridge läuft direkt auf dem Gateway** — keine Zusatzhardware, kein separater Server, rein lokal.
- **GARDENA smart Sensor II (Modell 19040) erscheint als echter Matter-Bodensensor** — Bodenfeuchte
  über den Standard-**SoilMeasurement-Cluster (0x0430)**, in Home Assistant als „Soil moisture" sichtbar.
  Temperatur und Batterie sind ebenfalls live. Geräte-Identität: **„Local Garden / Gardena Matter Bridge"**.
- **Reboot-fest:** Die Bridge installiert sich ins beschreibbare Overlay, startet nach einem Power-Cycle
  automatisch und behält ihr Pairing (kein erneutes Commissioning nötig). Kein Firmware-Flashen — vollständig reversibel.
- **Automatisiertes Regressions-Harness:** Ein-Kommando chip-tool-Testsuite prüft alle Sensor-Attribute
  gegen Live-Werte vom Gateway (Oracle-Abweichung = 0 für alle Werte).
- **Stabile Matter-SDK-Basis:** Gebaut auf dem offiziellen **stabilen Release v1.5.1.0**, reproduzierbare Builds.
- **MQTT-Frontend** — läuft neben Matter; veröffentlicht Sensorwerte an jeden MQTT-Broker mit
  Home-Assistant-Auto-Discovery. Diagnose-Werte (Funkverbindungsqualität, Mäher-Laufzeit,
  Fehlercodes), die in keinen Matter-Cluster passen, erscheinen als HA-`sensor`-Entitäten.
  → [MQTT-Dokumentation](mqtt.de.md)

## 🔜 Als Nächstes

- **Mehr Gerätetypen.** Wasserventile, schaltbare Steckdosen, Pumpen und Mähroboter (auf das
  Matter-Saugroboter-Profil abgebildet, sodass Start/Stopp/Pause/Heimfahrt als echte Steuerung funktionieren).
- **Langzeit-Koexistenz-Härtung** — mDNS über den Hersteller-System-Service (kein eigener Responder),
  robust gegen Hersteller-Firmware-Updates.

## 🧭 Später

- **Einfache Installationswege** für nicht-technische Nutzer — ein Home-Assistant-Add-on und ein
  geführter Installer, sodass kein manuelles SSH oder Bauen nötig ist.

## Wie GARDENA-Geräte auf Matter abgebildet werden

Jedes bekannte GARDENA-Produkt wird zu einem Matter-Gerät. Übersicht (✅ = live bewiesen,
🟡 = gerätegeprüft / geplant, ⚪ = geplant, noch nicht an Hardware getestet):

| GARDENA-Gerät | Erscheint in Matter als | Du bekommst | Status |
|---|---|---|---|
| smart Sensor / Sensor II | Bodensensor (Soil Sensor) | Bodenfeuchte, Temperatur, (Licht), Batterie | ✅ (Bodenfeuchte als SoilMeasurement 0x0430 · Temp + Batterie chip-tool-verifiziert) |
| Water Control | Wasserventil (Water Valve) | Ventil auf/zu + Timer, Batterie | ⚪ |
| smart Irrigation Control | 6 × Wasserventil (ein Gerät) | sechs unabhängige Ventile | ⚪ |
| smart Power | An/Aus-Steckdose | schaltbare Steckdose | ⚪ |
| Pumpe / Pressure Pump | Pumpe (Pump) | Druck- & Durchfluss-Sensor (+ An/Aus) | ⚪ |
| Mähroboter (SILENO) | Saugroboter-Profil | **Status (mäht/parkt/lädt) + Batterie — read-only**; Start/Stopp später | ✅ (Matter-Status + Batterie chip-tool-verifiziert; HA-vacuum-Entität live; Schreibsteuerung geplant) |

Diagnose-Werte ohne Matter-Standard (Funk-Empfangsqualität, Mäher-Laufzeit) werden über das
MQTT-Frontend als `diagnostic`-Entitäten in Home Assistant veröffentlicht. → [MQTT-Dokumentation](mqtt.de.md)

## Fortschritt verfolgen

Die Entwicklung passiert offen. Issues und Beiträge sind willkommen — siehe
[Mitwirken](contributing.md).
