# Technische Lage & Machbarkeit

> Öffentlich kuratierte Fassung der technischen Erkenntnisse.

## Hardware (19005) — bestätigt

Quelle: offizieller Linux-/U-Boot-Board-Support (`gardena-smart-gateway-mt7688.dts`,
in mainline Linux **und** U-Boot vorhanden).

| Komponente | Wert |
|---|---|
| SoC | MediaTek **MT7688** (MIPS 24KEc @ **580 MHz**, 1T1R 802.11n WiFi) |
| RAM | **128 MiB** DDR |
| Flash | **8 MiB** SPI NOR **+ 128 MiB** SPI NAND |
| RF-Coprozessor | **SiM3U167** (868 MHz, Lemonbeat) |
| Ethernet | 10/100 |

Es existiert **kein potenteres GARDENA-Gateway** — das 19005 ist das aktuelle und einzige
Modell. Der bindende Engpass ist **RAM (128 MiB)** zur Laufzeit und der **beschreibbare
Flash-Platz** (UBI).

## Software-Architektur (aktuelle Firmware)

- **Yocto-Linux** (aktuell „scarthgap"/5.0 LTS), Root als **read-only squashfs** auf UBI/NAND,
  **A/B-Boot-Slots**, beschreibbares Overlay (`meta-readonly-rootfs-overlay`).
- **Proprietäre Daemons** (closed binaries, via OPKG nachinstallierbar):
    - `lemonbeatd` — spricht 868-MHz-Lemonbeat mit den Geräten (der RF-Layer)
    - `accessory-server`, `lwm2mserver` — Gerätemodell / Device-Management (LwM2M)
    - `cloudadapter` — Cloud-Anbindung (heute **AWS IoT**)
    - `fwrolloutd`, `gateway-config-backend/-frontend`
- Der Cloud-Teil läuft über **AWS IoT**, nicht mehr über Seluxit/Shadoway. Älteres
  Reverse-Engineering (2019) ist für die aktuelle Firmware größtenteils obsolet.
- **RF Gerät → Gateway:** Lemonbeat (868 MHz), proprietär/verschlüsselt — wird vom Gateway
  gehandhabt und muss für Variante A **nicht** neu implementiert werden.

## Offen vs. proprietär — die entscheidende Grenze

| Offen (baubar, im Public-BSP) | Geschlossen (nur Binär via OPKG) |
|---|---|
| Yocto-BSP, U-Boot, Kernel (`linux-yocto-tiny`) | `lemonbeatd` (RF) |
| Basis-Image `gardena-image-foss-bnw` | `accessory-server`, `lwm2mserver` |
| WiFi-Provisioning, Tests (`meta-gardena`) | `cloudadapter` (AWS IoT) |
| `meta-distribution`, `meta-swupdate`, `meta-aws` | `fwrolloutd`, `gateway-config-*` |
| `meta-readonly-rootfs-overlay` | |

Die echte Lemonbeat-Funk-Firmware ist im Public-Repo nur ein **CLOSED Dummy-Stub**. Selbst die
eigenen proprietären Pakete passen laut Husqvarna **nicht alle** ins beschreibbare Dateisystem
— für einen zusätzlichen Matter-Stack ist ein **UBI-Volume-Resize** nötig („must be done with
great care").

## Machbarkeits-Verdict (Variante A)

**Machbar** — dank offiziellem BSP, A/B-Slots und offiziellem SSH-Zugang besser gestützt als
zunächst angenommen. Drei echte Herausforderungen, nach absteigender Unsicherheit:

1. **Lokale Geräte-Schnittstelle — gelöst.** `lemonbeatd` pflegt ein selbstbeschreibendes
   Dateisystem unter `/var/lib/lemonbeatd/` (die LsDL-Schicht). Die Bridge liest Geräteschemata
   und Live-Sensorwerte direkt aus diesem Verzeichnisbaum — kein IPC-Socket, kein
   Reverse-Engineering. Linux-`inotify` liefert Wert-Updates sofort, sobald der Daemon Dateien
   schreibt.
2. **Matter-Port auf MIPS.** `connectedhomeip` zielt nicht auf MIPS 24KEc; über den Yocto-BSP
   als Recipe machbar, aber ein echtes Port-Projekt (OpenSSL/mbedTLS, softfloat). 580 MHz
   Single-Core → Commissioning/Krypto langsam, aber funktional.
3. **Platz & RAM.** UBI-Volumes vergrößern; 128 MiB RAM neben den laufenden Daemons sind eng.

## Verworfene / alternative Ansätze

- **Variante B (separater Server):** lokaler Matter-Server auf einer Extra-Box + Umleitung.
  Einfacher, aber separater Server — entspricht nicht dem Ziel. Bleibt Fallback.
- **`shadoway.conf` → deGardenServer (obsolet):** leere, verlassene Hülle; zielt auf das alte
  Seluxit-Protokoll, das auf der aktuellen AWS-IoT-Firmware nicht mehr greift.

## Datenschicht: Wie die Bridge Sensorwerte liest

`lemonbeatd` pflegt ein selbstbeschreibendes Dateisystem unter `/var/lib/lemonbeatd/` — ein
Unterverzeichnis pro gekoppeltem Gerät (benannt nach dessen SGTIN). Jedes Geräteverzeichnis
enthält:

- **`Device_descriptionID_<n>.json`** — Gerätemetadaten: Seriennummer (SGTIN), Name, Typ
- **`Value_description/<id>.json`** — Werteschema: Name, Datenformat, Einheit, Wertebereich,
  Berechtigungen
- **`Value/Value_<id>r.json`** — Aktueller Wert: `{"id": N, "timestamp": <epoch_ms>, "value": "<str>"}`

Die Bridge erkennt beim Start alle gekoppelten Geräte, liest deren Schemata und lädt die
aktuellen Werte aus diesem Verzeichnisbaum. Anschließend registriert sie Linux-`inotify`-Watches
auf dem `Value/`-Verzeichnis jedes Geräts. Wenn `lemonbeatd` eine neue Messung auf die Platte
schreibt, liefert inotify das Ereignis sofort und die Bridge aktualisiert das zugehörige
Matter-Attribut — ohne jedes Polling.

```
/var/lib/lemonbeatd/
  Device_descriptionID_1/
    Device_descriptionID_1.json        ← SGTIN, Gerätename/-typ
    Value_description/
      12345.json                       ← Schema: "soil_temperature", number, °C, –40..85
      12346.json                       ← Schema: "soil_moisture", number, %, 0..100
      ...
    Value/
      Value_12345r.json                ← {"id":12345,"timestamp":1750123456789,"value":"31"}
      Value_12346r.json                ← {"id":12346,"timestamp":1750123456789,"value":"70"}
```

Verwendete Wertenamen:

| LsDL-Wertename | Bedeutung | Einheit |
|---|---|---|
| `soil_moisture` | Bodenfeuchte | % |
| `soil_temperature` | Bodentemperatur | °C |
| `battery_level` | Batterieladestand | % |
| `mower_status` | Betriebsstatus des Mähers | numerisch (0–18) |

Die Bridge öffnet **keinen IPC-Socket** — sie verbindet sich nie mit `lemonbeatd-command.ipc`
oder einem anderen Unix-Domain-Socket der Vendor-Daemons. Lesezugriffe sind rein passive
Dateisystem-Reads. Die Gardena-Cloud-Verbindung (`cloudadapter`) bleibt jederzeit aktiv —
die Bridge ist rein additiv und stört weder App-Nutzung noch OTA-Firmware-Updates.

## Matter-Gerätemodell

Jeder physische GARDENA smart Sensor wird auf **einen Matter Bridged Endpoint** (Soil Sensor,
Device-Type 0x0045) mit drei Clustern abgebildet:

```
GARDENA smart Sensor (...0001)   ← ein Matter-Gerät (Soil Sensor 0x0045)
  ├─ SoilMeasurement           (0x0430)  soil_moisture    [% direkt, 0–100]
  ├─ TemperatureMeasurement    (0x0402)  soil_temperature [°C × 100]
  └─ PowerSource               (0x002F)  battery_level    [% × 2]
```

**Cluster 0x0430 (`SoilMeasurement`)** ist seit Matter 1.5 im Standard enthalten — verfügbar in
`connectedhomeip v1.5.1.0`. Home Assistant zeigt ihn als „Soil moisture" mit `device_class MOISTURE`.
Das Attribut `SoilMoistureMeasuredValue` (0x0001) enthält den Wert als direkten Prozentwert (0–100),
**nicht** mit 100 multipliziert (anders als bei `TemperatureMeasurement`).

**Verifiziert (chip-tool):**
```
soilmeasurement read soil-moisture-measured-value → SoilMoistureMeasuredValue: 70
temperaturemeasurement read measured-value        → MeasuredValue: 2900  (= 29 °C × 100)
powersource read bat-percent-remaining            → BatPercentRemaining: 106  (= 53 % × 2)
```

**Geräte-Identität:** Die Bridge meldet sich als **„Local Garden / Gardena Matter Bridge"**
mit VendorId 0xFFF1 / ProductId 0x8000 (CSA-Test-Credentials aus den SDK-Beispiel-DAC-Zertifikaten).
Jeder gebridgte Endpoint trägt den echten Produktnamen (z. B. „GARDENA smart Sensor (…0001)").

Das entspricht der Darstellung in der offiziellen Gardena-Cloud-App: ein Gerät mit mehreren
Messwerten. Das Matter-Modell bildet dies exakt nach.

**Mäher-Endpoint:** Der Mäher wird als *Robotic Vacuum Cleaner* (0x0074) mit fünf Clustern
dargestellt: `Identify` (0x0003, Pflicht des RVC-Device-Types), `RvcRunMode` (0x0054),
`RvcOperationalState` (0x0061), `PowerSource` (0x002F) und `Descriptor` (0x001D).
`SupportedModes` meldet zwei Modi: *Idle* (Tag 0x4000) und *Cleaning* (Tag 0x4001).
Der Endpoint ist strikt **schreibgeschützt**: kein Aktuierungspfad existiert im Binary.
`Identify` hat keinen physischen Effekt (IdentifyType = None; Schreibzugriffe werden abgelehnt).

## Ressourcen / Links

- Offizielles BSP: `github.com/husqvarnagroup/smart-garden-gateway-public`
- Quellpakete: `opensource.smart.gardena.dev`
- Offizielle Restore-Images: `gateway.iot.sg.dss.husqvarnagroup.net`
- Mainline DTS: `gardena-smart-gateway-mt7688.dts` (Linux & U-Boot)
- Altes RE-Wiki (2019): `github.com/gardena-smart-reverse-engineering` (Lemonbeat/HW nützlich,
  Cloud-Teil obsolet)
- Matter-SDK: `connectedhomeip`
- Lokaler Websocket-Daemon (Referenz für Gerätemodell): `github.com/husqvarnagroup/smart-garden-gateway-websocketd`
- Gerätemodell-Referenz: `github.com/cloudless-garden/gardena-smart-local-api`
