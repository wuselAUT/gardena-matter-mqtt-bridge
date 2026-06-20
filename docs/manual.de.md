# Handbuch

> Nutzungs- und Build-Anleitung. **Technische Referenz** hinter der Inbetriebnahme.

!!! warning "Garantie"
    Custom-Firmware verliert die Garantie. Alle Schritte zielen auf den **inaktiven A/B-Slot**,
    damit das Original bootbar bleibt. **Auf eigene Gefahr.**

!!! tip "Du willst es einfach in Betrieb nehmen?"
    → **[Inbetriebnahme](getting-started.md)** führt dich in **zwei einfachen Wegen** (Home
    Assistant **oder** Standalone-Installer) vom Karton zum laufenden Matter-Gerät — ohne
    SSH-/Build-Wissen. **Dieses Handbuch ist die technische Referenz** dahinter (SSH, Build,
    Flashen, Adapter, Slot-B-Advanced).

## 1. Voraussetzungen

- GARDENA smart Gateway **Art. 19005**, am LAN, Stromversorgung.
- Die **Geräte-ID** von der Unterseite (Format `GARDENA-xxxxxx`). Das SSH-Passwort sind die
  **ersten 8 Zeichen der ID**.
- Ein SSH-Schlüsselpaar (`ssh-keygen -t ed25519`).
- Für den Firmware-Build: ein **Linux-Host** (nativ, VM oder WSL2) — Yocto baut nicht unter Windows.

## 2. SSH-Zugang aktivieren

Offizieller Weg über die lokale HTTPS-API des Gateways — kein UART, kein Exploit:

```bash
gateway=GARDENA-123456
password=1234abcd          # erste 8 Zeichen der ID

# 1) Session holen
session=$(curl -H 'Content-Type: application/json' \
  -d '{"password": "'"$password"'"}' --insecure https://$gateway/login | jq -r .session)

# 2) eigenen Public Key registrieren
curl -X POST -H "X-session: $session" -H 'Content-Type: application/json' \
  -d '{"key": "'"$(cat ~/.ssh/id_ed25519.pub)"'"}' --insecure https://$gateway/ssh_access_credentials

# 3) SSH aktivieren
curl -X PUT -H "X-session: $session" -H 'Content-Type: application/json' \
  -d '{"enable": true}' --insecure https://$gateway/ssh_access_enable

# 4) einloggen
ssh root@$gateway
```

**UART-Fallback:** Port **J7**, **115200 8N1, 3,3 V**; in der U-Boot-Shell direkt nach dem
Einschalten Taste **„X"** drücken.

## 3. Recon — Gerät kennenlernen

Nach dem ersten Login die Ressourcen- und Schnittstellen-Lage aufnehmen:

```bash
cat /proc/cpuinfo          # SoC
free -m                    # freier RAM im Betrieb (binding constraint)
df -h ; cat /proc/mtd      # Flash / UBI-Partitionen
ps ; ss -tlnp              # laufende Daemons, offene lokale Ports/Sockets
```

Besonders interessant: ob `lwm2mserver` / `accessory-server` eine **lokale** Schnittstelle
(Port/Socket/D-Bus) anbieten — das ist der geplante Andock-Punkt der Bridge.

## 4. Custom-Firmware bauen & flashen

```bash
# Bauen (auf dem Linux-Host)
git clone --recurse-submodules https://github.com/husqvarnagroup/smart-garden-gateway-public
cd smart-garden-gateway-public
scripts/bbwrapper.sh mt7688 gardena-image-foss-bnw linux-yocto-tiny
```

Flashen per U-Boot + TFTP in den **inaktiven** A/B-Slot:

```
run do_toggle_bootslot
env save
ubi part nand
dhcp fitImage-gardena-sg-mt7688.bin && ubi write ${fileaddr} kernel${bootslot} ${filesize}
dhcp gardena-image-foss-bnw-gardena-sg-mt7688.squashfs-xz && ubi write ${fileaddr} rootfs${bootslot} ${filesize}
reset
```

## 5. Rollback / Recovery

Bootslot zurückschalten — das Original in Slot A bleibt unangetastet:

```bash
fw_setenv bootslot $(( 1 - $(fw_printenv -n bootslot) )); reboot
```

Offizielle Images zum Wiederherstellen liegen auf Husqvarnas Server
(`gateway.iot.sg.dss.husqvarnagroup.net`).

## 6. gardena-adapter: Deployen & Nutzen

Der **gardena-adapter** ist eine Python-Brücke zwischen dem internen `lwm2mserver`-EventBus
und einem stabilen **lokalen JSON-API** (Unix-Socket). Er ist der Baustein, auf dem die
spätere Matter-Bridge aufbaut: Er liefert Geräte-Inventar, Verbindungsstatus und
Sensor-Ressourcen, ohne den laufenden Stack zu berühren. Read-only.

### 6.1 Voraussetzungen

- GARDENA smart Gateway 19005 mit Firmware ≥ 10.4.4 (`bnw-zephyr`-Image)
- SSH-Zugang eingerichtet (→ §2)
- Python 3.12 auf dem Gerät (bereits vorinstalliert)
- `lwm2mserver` läuft (Standard-Betrieb)

### 6.2 Adapter auf das Gateway kopieren

Der Adapter liegt im privaten Werkstatt-Repo unter `adapter/`.
Auf das Gateway kopieren (kein Flash, kein OPKG nötig — Overlay oder /tmp reichen für Entwicklung):

```bash
# Auf dem Entwicklungs-Rechner (Linux/WSL):
# Dateien einzeln per SSH-Pipe übertragen (scp/sftp steht auf diesem Gerät nicht zur Verfügung)
GATEWAY=root@<gateway-ip>   # Beispiel-IP — durch die Adresse deines Gateways ersetzen
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

!!! tip "Alternativ"
    Auf Systemen mit `rsync` über SSH-Protokoll oder wenn `/usr/libexec/sftp-server` vorhanden
    ist, genügt `scp -r adapter/ $GATEWAY:$DEST/`.

### 6.3 Adapter starten

```bash
ssh root@<gateway-ip>

# Konfiguration
PYTHONPATH=/tmp/gardena-adapter

# Dauerhaft im Vordergrund (Entwicklung)
cd /tmp/gardena-adapter
PYTHONPATH=/tmp/gardena-adapter python3 -m adapter.gardena_adapter \
    --socket /tmp/gardena-adapter.sock \
    --log-level INFO

# Im Hintergrund (Dev-Betrieb)
PYTHONPATH=/tmp/gardena-adapter python3 -m adapter.gardena_adapter \
    --socket /tmp/gardena-adapter.sock &
```

Der Adapter:

1. Liest Inventar via `list-lemonbeat-devices` (beim Start + alle 5 min)
2. Verbindet sich mit dem EventBus-PUB-Socket und empfängt Geräte-Events passiv
3. Öffnet den lokalen JSON-API-Socket unter `--socket` (Standard: `/tmp/gardena-adapter.sock`)

Lognachrichten erscheinen auf stderr. Bereit wenn folgende Zeile erscheint:

```
GardenaAdapter: alle Komponenten gestartet, API auf /tmp/gardena-adapter.sock
```

**Verifikations-Schnelltest** (`--once`, einmalig + JSON-Report):

```bash
PYTHONPATH=/tmp/gardena-adapter python3 -m adapter.gardena_adapter --once
# Exit-Code 0 = alle Basis-Checks OK
```

### 6.4 Lokales API abfragen

Das API spricht **newline-JSON** (eine JSON-Zeile senden, eine JSON-Zeile empfangen),
konsistent mit dem EventBus-Stil.

**Allgemeines Abfragemuster:**

```bash
# Mit Python (empfohlen)
python3 -c "
import sys, json, socket
sys.path.insert(0, '/tmp/gardena-adapter')
from adapter.api import query_api
result = query_api({'cmd': 'KOMMANDO', ...})
print(json.dumps(result, indent=2))
"

# Direkt mit echo + socat (wenn socat verfügbar)
echo '{"cmd":"health"}' | socat - UNIX-CONNECT:/tmp/gardena-adapter.sock
```

#### `list_devices` — alle Geräte auflisten

```bash
python3 -c "
import sys, json
sys.path.insert(0, '/tmp/gardena-adapter')
from adapter.api import query_api
print(json.dumps(query_api({'cmd':'list_devices'}), indent=2))
"
```

Beispiel-Antwort:

```json
[
  {"address":"fc00::6:0000:0000:0001","name":"SG Mower LONA","sgtin":"300000...","online":null,"last_seen_ts":null},
  {"address":"fc00::6:0000:0000:0002","name":"SG Sensor 2","sgtin":"300001...","online":false,"last_seen_ts":1781471595},
  {"address":"fc00::6:0000:0000:0003","name":"SG Sensor 2","sgtin":"300001...","online":false,"last_seen_ts":1781471595}
]
```

#### `read` — Ressource lesen (EventBus-Proxy)

```bash
# connection_status (lokal gecacht, sofortige Antwort)
python3 -c "
import sys, json
sys.path.insert(0, '/tmp/gardena-adapter')
from adapter.api import query_api
result = query_api({
    'cmd': 'read',
    'address': 'fc00::6:0000:0000:0002',   # Sensor-Adresse
    'path': 'connection_status'
})
print(json.dumps(result, indent=2))
"
```

Beispiel-Antwort:

```json
{
  "success": true,
  "payload": {
    "0": {"online": {"vb": false, "ts": 1781471595}},
    "_urn": "urn:oma:lwm2m:x:28171"
  }
}
```

- `online.vb`: `true` = Gerät wach, `false` = schläft (Wake-on-Radio)
- `online.ts`: Unix-Epoch des letzten Verbindungschecks

```bash
# IPSO-Ressource (erfordert Geräte-Wakeup, bis 30s Wartezeit)
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
# Wenn Gerät schläft: {"success": false, "error": "Device '...' not connected"}
```

#### `get_device` — vollständiger Geräte-Cache-Snapshot

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

Antwort enthält: `address`, `name`, `sgtin`, `online`, `last_seen_ts`,
`resources` (zuletzt gesehene Ressourcen), `last_sequence`.

#### `health` — Adapter-Status

```bash
python3 -c "
import sys, json
sys.path.insert(0, '/tmp/gardena-adapter')
from adapter.api import query_api
print(json.dumps(query_api({'cmd':'health'}), indent=2))
"
```

Beispiel-Antwort:

```json
{
  "eventbus_connected": true,
  "device_count": 3,
  "uptime_s": 46.9,
  "last_sequence": 18
}
```

### 6.5 Bekannte Grenzen

| Einschränkung | Erklärung |
|---|---|
| Nur read-only | Keine Write/Execute-Kommandos; Mäher nicht aktiv angesprochen |
| IPSO-Mapping unvollständig | Sensor-Ressourcen (Temperatur, Feuchte) erst nach echtem Wakeup-Zyklus kartierbar |
| `online: null` direkt nach Start | Erst nach erstem EventBus-Event oder `read connection_status` gefüllt |
| Kein persistenter State | Bei Adapter-Neustart leerer Cache (Inventar nach ~5s wieder da) |
| Dev-Deployment | Kein autostart, kein Flash — für permanente Installation Beispiel-Unit `adapter/gardena-adapter.service` |

## 7. Matter-Bridge nutzen

### 7.1 Unterstützte Geräte und Datenpunkte

Die Matter-Bridge erkennt automatisch **alle GARDENA-Geräte** am Gateway und bridget sie
anhand der Modellnummer. Unterstützte Gerätetypen:

| Gerätetyp | Matter-Darstellung | Status |
|---|---|---|
| smart Sensor II (Art. 19040) | Soil Sensor (SoilMeasurement + Temperatur + Batterie) | verifiziert |
| smart Sensor (Art. 18845) | Soil Sensor + Beleuchtungsstärke | gemappt, noch nicht hw-verifiziert |
| Mähroboter (SILENO / LONA) | Robotic Vacuum Cleaner (Status + Batterie, read-only) | verifiziert |
| Water Control / Irrigation Control | Water Valve (nur Status, read-only) | gemappt, noch nicht hw-verifiziert |
| smart Power (Steckdose) | On/Off Plug-in Unit (nur Status, read-only) | gemappt, noch nicht hw-verifiziert |
| Pumpe | Pump (nur Status, read-only) | gemappt, noch nicht hw-verifiziert |
| Unbekanntes Modell | BridgedBasicInfo-only Stub (Erreichbarkeitsanzeige, keine Daten) | — |

Geräte, die während des Bridge-Betriebs am Gateway erscheinen, werden automatisch hinzugefügt
(kein Neustart nötig). Geräte, die verschwinden, werden entsprechend aus dem Matter-Fabric entfernt.

### 7.2 Gerätebenennung

Jeder Sensor erhält einen eindeutigen, lesbaren Namen aus der offiziellen Produktbezeichnung und
einem kurzen Diskriminator aus der internen Hardware-ID:

- `GARDENA smart Sensor (...0001)`
- `GARDENA smart Sensor (...0002)`

Diese Namen können in Home Assistant, Apple Home oder Google Home nach dem Commissioning frei
umbenannt werden. Der Bridge-Name ist nur das initiale Label.

### 7.3 Bridge bauen

#### Voraussetzungen

- Build-Host: Linux (nativ, VM oder WSL2), Ubuntu 22.04+
- Husqvarna-Yocto-SDK (OldSoft-Toolchain) aus dem BSP-Build — vollständige Build-Anleitung im
  privaten Werkstatt-Repo
- SSH-Zugang zum Gateway (→ §2)

#### Matter-SDK

Die Bridge wird gegen **connectedhomeip `v1.5.1.0`** gebaut (Tag `v1.5.1.0`,
SHA `abcc720b48c5e59c0edcfe65c516f76ca9448aa3`). Das ist das stabile Matter-1.5-SDK —
die erste Version, die den `SoilMeasurement`-Cluster (0x0430) für korrektes Boden­feuchte-Mapping
enthält.

Klonen:

```bash
git clone --branch v1.5.1.0 --depth 1 --recurse-submodules --shallow-submodules \
    https://github.com/project-chip/connectedhomeip.git ~/gardena-matter-build/connectedhomeip
```

#### Bauen

```bash
# Auf dem Build-Host (z.B. ubuntu-server):
bash matter/build_bridge_app.sh ~/gardena-matter-build 3
```

Führt den GN + ninja Cross-Build mit der OldSoft-MIPS-Toolchain durch. Ergebnis ist ein
gestripptes MIPS-Soft-Float-Binary (~2 MiB, fp_abi=0).

### 7.4 Persistente Installation (empfohlen)

```bash
bash matter/install_bridge.sh [GATEWAY_IP]
```

Installiert die Bridge dauerhaft in das beschreibbare Overlay des Gateways.

Was das Skript tut:

1. Kopiert das Binary nach `/usr/local/lib/gardena-matter/` (Overlay-Dateisystem, persistent)
2. Entpackt die C++-Laufzeit-Bibliotheken in dasselbe Verzeichnis
3. Legt einen Launcher mit korrektem `LD_LIBRARY_PATH` an
4. Legt das KVS-Verzeichnis `/var/lib/gardena-matter/` an (falls noch nicht vorhanden —
   ein vorhandenes KVS wird **nie** gelöscht)
5. Installiert und aktiviert die systemd-Unit `gardena-matter-bridge.service`
6. Öffnet UDP 5540 via `ExecStartPre` (persistent, auch nach Reboot)
7. Startet den Service; Bridge ist sofort erreichbar

Nach einem Reboot startet die Bridge automatisch — Commissioning-State (KVS) und HA-Pairing
bleiben vollständig erhalten.

#### Deinstallieren / Rollback

```bash
bash matter/uninstall_bridge.sh [GATEWAY_IP]
```

Entfernt Binary, Libs, Launcher, Unit-Datei und Firewall-Regeln.
Das KVS unter `/var/lib/gardena-matter/chip_kvs` wird **nicht** entfernt —
nach einer Neuinstallation ist kein erneutes Pairing in HA nötig.

#### Verifiziertes Verhalten nach Reboot

- Bridge startet automatisch (systemd `multi-user.target`)
- Firewall-Regel für UDP 5540 wird von `ExecStartPre` gesetzt
- KVS bleibt erhalten; HA-CASE-Session wird ohne erneutes Pairing wiederhergestellt
- Gardena-Cloud-Verbindung bleibt durchgehend aktiv

### 7.5 Temporärer Deploy (Entwicklung/schneller Test)

```bash
bash matter/deploy_bridge.sh ~/gardena-matter-build/out/mips-bridge/chip-bridge-app.stripped <gateway-ip>
```

Für Entwicklung und schnelle Tests: Kopiert das Binary nach `/tmp/` (RAM, verschwindet nach
Reboot). KVS und Commissioning-State bleiben erhalten. Nach einem Reboot muss `deploy_bridge.sh`
erneut ausgeführt werden.

### 7.6 In Home Assistant einbinden

1. QR-Payload oder manuellen Code aus der Deploy-Ausgabe notieren.
2. Browser-UI öffnen (`https://<gateway-ip>/assets/matter.html`) und einloggen.
3. **„Pairing aktivieren"** klicken — die Bridge öffnet ein 180-Sekunden-Pairing-Fenster.
4. In HA: **Einstellungen → Geräte & Dienste → Matter → Gerät hinzufügen** (während der Countdown läuft).
5. QR-Code scannen **oder** manuellen Code eingeben.
6. Erwartetes Ergebnis: **zwei Geräte** erscheinen — `GARDENA smart Sensor (...0001)` und
   `GARDENA smart Sensor (...0002)` — je mit drei Entitäten (Temperatur, Feuchte, Batterie).

> **Ohne Browser-UI:** Das Pairing-Fenster ist auch direkt nach dem Bridge-Start offen
> (Erststart / nach Neustart). In diesem Fall kann „Pairing aktivieren" übersprungen werden —
> Commissioning direkt aus der Deploy-/Install-Ausgabe starten.

> **Hinweis:** Falls eine Entität nach dem Pairing fehlt, hat die Bridge möglicherweise noch keine
> erste Messung erhalten. Die Sensoren schlafen die meiste Zeit und berichten etwa alle 30 Minuten.
> Erneutes Pairing nach kurzer Wartezeit (oder nach kurzem Antippen des Sensors) behebt das.

### 7.7 In Apple Home / Google Home einbinden

Apple Home und Google Home unterstützen Matter-Commissioning über denselben QR-Code oder
manuellen Code. Die Bridge ist ein Standard-Matter-Bridge-Gerät — keine Hersteller-App nötig.

### 7.8 Bekannte Grenzen

| Einschränkung | Details |
|---|---|
| Sensoren schlafen | Bodensensoren berichten ca. alle 30 min (batteriebetrieben). Werte in HA können nachhängen. |
| Batterie-Aktualisierung selten | Batteriestand wird ca. 1×/h aktualisiert. Die Bridge nutzt 50 % als Platzhalter bis zur ersten echten Messung. |
| Bodenfeuchte-Label | HA zeigt „Luftfeuchtigkeit" (Matter-Standard-Label) — der Wert ist Bodenfeuchte. Die Bridge nutzt den SoilMeasurement-Cluster (0x0430, Matter 1.5+) für korrektes Mapping. |
| RF-Signalqualität | Wird via Matter nicht ausgegeben (kein Standard-Cluster dafür). |
| Aktuierung (Ventil öffnen/schließen, Pumpe, Mäher starten) | Nur Status/read-only in dieser Version. Aktuierung ist als Follow-up geplant. |
| Geräte außerhalb des Testsets (Water Control, Pumpe, Steckdose, Sensor I) | Auf den richtigen Matter-Device-Type gemappt, aber noch nicht an echter Hardware verifiziert. |
| Commissioning in HA: User-Aktion | Das QR-/Code-Pairing muss vom User durchgeführt werden — die Bridge stellt die Daten bereit, der User führt das Pairing durch. |
| mDNS-Koexistenz | Bridge und Gateway-eigener `mdnsd` laufen gleichzeitig auf eth0; beides ist in `ff02::fb` eingetragen (ppp0 bewusst ausgeschlossen). Kein bekannter Konflikt. |
