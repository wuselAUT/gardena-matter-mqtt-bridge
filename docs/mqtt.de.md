# MQTT-Frontend

> **Parallelpfad neben Matter** — deine GARDENA-Geräte veröffentlichen ihre Sensorwerte
> an jeden MQTT-Broker. Home Assistant erkennt sie per Auto-Discovery; auch Node-RED, Grafana,
> ioBroker und openHAB sind kompatibel.

!!! info "Status"
    Das MQTT-Frontend ist **in aktiver Entwicklung**. Die Matter-Bridge (der Hauptpfad)
    funktioniert heute vollständig. Der MQTT-Publisher wird mit dem HA-Add-on ausgeliefert,
    sobald das Add-on verfügbar ist. Die manuelle Installation ist weiter unten beschrieben,
    für diejenigen, die frühzeitig testen möchten.

## Warum MQTT?

Matter eignet sich gut für **Standardgeräte** (Sensoren, Ventile, Steckdosen). Diagnosewerte,
die in kein Matter-Cluster passen — **Funkverbindungsqualität, Mäher-Laufzeit, Fehlercodes** —
erscheinen als MQTT-`sensor`-Entitäten in Home Assistant.

Beide Pfade können **gleichzeitig** laufen: Die Bridge weiß nichts vom Publisher, und der
Publisher berührt die Bridge nicht.

## Wie es funktioniert

```
GARDENA-Geräte ──868 MHz──▶ lemonbeatd ──(schreibt LsDL-Dateien)──▶ /var/lib/lemonbeatd/
                                                                            │
                                                               gardena-mqtt-publisher
                                                               (liest alle 30 s via
                                                                inotify, kein IPC)
                                                                            │
                                                               MQTT-Broker (dein Netzwerk)
                                                                            │
                                                            Home Assistant MQTT-Integration
```

Der Publisher **liest dieselben Gerätebeschreibungsdateien**, die auch die Matter-Bridge
verwendet. Es gibt keinen gemeinsamen Socket und keinen gemeinsamen Prozess — die
Koexistenz ist strukturell garantiert.

**Home-Assistant-Auto-Discovery**: Der Publisher sendet Retained-Config-Messages auf
`homeassistant/<Komponente>/gardena_<Hash>/<ID>/config`. Home Assistant erkennt sie
automatisch. Keine manuelle Entitätskonfiguration nötig.

## Was du je Gerät erhältst

| GARDENA-Gerät | MQTT-Entitäten |
|---|---|
| smart Sensor / Sensor II | Bodentemperatur, Akku |
| SILENO Mähroboter | Status (mähen / geparkt / laden), Akku, Funkverbindungsqualität, Laufzeit, Fehlercode |
| Water Control / Irrigation Control | Akku, Funkverbindungsqualität |
| smart Power | Akku, Funkverbindungsqualität |
| Pumpe | Akku, Funkverbindungsqualität |

Entitäten, die als **Diagnose** markiert sind (Funkverbindungsqualität, Laufzeit, Fehlercode),
erscheinen im HA-Gerätekarte unter „Diagnose" — sie tauchen standardmäßig nicht auf
Dashboards auf.

## Home-Assistant-Add-on-Pfad (empfohlen)

Sobald das HA-Add-on verfügbar ist, wird der MQTT-Publisher über die Add-on-Optionen konfiguriert.

In der Add-on-Konfiguration:

| Option | Beispiel | Beschreibung |
|---|---|---|
| `enable_mqtt` | `true` | MQTT-Publisher aktivieren. Standard: `false`. |
| `mqtt_broker_host` | `homeassistant.local` | Hostname oder IP deines MQTT-Brokers. |
| `mqtt_broker_port` | `1883` | Broker-Port. Standard: `1883`. |
| `mqtt_broker_user` | `mqttbenutzer` | Broker-Benutzername (leer lassen, wenn dein Broker keine Authentifizierung braucht). |
| `mqtt_broker_password` | _(dein Passwort)_ | Broker-Passwort — wird verschlüsselt gespeichert, nie geloggt. |
| `mqtt_topic_prefix` | `gardena` | Präfix für State-Topics (`gardena/<Hash>/<Ressource>/state`). |
| `mqtt_ha_prefix` | `homeassistant` | Präfix für Discovery-Topics — muss zur HA-MQTT-Integration passen. |

`enable_mqtt: true` setzen, Broker-Daten eintragen und **Speichern → Neu starten** klicken.
Der Publisher wird automatisch auf dem Gateway installiert und gestartet.

!!! tip "Mosquitto in Home Assistant"
    Wenn du das **Mosquitto-Add-on** in HA verwendest, ist der Broker-Host normalerweise
    `homeassistant.local` (Port `1883`). Lege in den Mosquitto-Add-on-Einstellungen einen
    eigenen MQTT-Benutzer für den GARDENA-Publisher an.

## Gateway-Web-UI

Die Gateway-Web-UI (erreichbar unter `http://<Gateway-IP>:8099/matter.html`) zeigt den
MQTT-Publisher-Status und ermöglicht es, die Broker-Einstellungen **direkt auf dem Gateway**
zu ändern:

1. `http://<Gateway-IP>:8099/matter.html` im Browser öffnen.
2. Die **MQTT**-Karte zeigt den aktuellen Publisher-Status (aktiv / inaktiv).
3. Auf **Einstellungen** klicken, um das Broker-Konfigurationsformular aufzuklappen.
4. Host, Port, Benutzername und Passwort eintragen — dann auf **Speichern** klicken.
5. Das Gateway schreibt die Konfiguration nach `/etc/gardena-matter/mqtt.env`
   (nur für den Eigentümer lesbar) und startet den Publisher-Dienst neu.

Das Passwort wird in der UI **nie angezeigt** — nur ob eines gesetzt ist.

## Manuelle Installation (ohne HA-Add-on)

Für Tests vor dem Add-on-Release kannst du den Publisher direkt per SSH installieren.

**Voraussetzung:** Die GARDENA Matter Bridge muss bereits auf dem Gateway installiert sein.

```bash
# 1. Publisher-Binary auf das Gateway kopieren
scp gardena-mqtt-publisher root@<Gateway-IP>:/usr/local/lib/gardena-matter/

# 2. systemd-Service-Unit kopieren
scp mqtt-publisher/gardena-mqtt-publisher.service \
    root@<Gateway-IP>:/etc/systemd/system/

# 3. Konfigurationsdatei erstellen
ssh root@<Gateway-IP> "mkdir -p /etc/gardena-matter && cat > /etc/gardena-matter/mqtt.env" <<'EOF'
MQTT_BROKER_HOST=homeassistant.local
MQTT_BROKER_PORT=1883
MQTT_BROKER_USER=mqttbenutzer
MQTT_BROKER_PASS=<dein-passwort>
MQTT_TOPIC_PREFIX=gardena
MQTT_HA_PREFIX=homeassistant
EOF
ssh root@<Gateway-IP> "chmod 600 /etc/gardena-matter/mqtt.env"

# 4. Dienst aktivieren und starten
ssh root@<Gateway-IP> "systemctl daemon-reload && \
  systemctl enable gardena-mqtt-publisher.service && \
  systemctl start gardena-mqtt-publisher.service"

# 5. Status prüfen
ssh root@<Gateway-IP> "systemctl status gardena-mqtt-publisher.service"
```

`<Gateway-IP>` durch die IP-Adresse deines Gateways ersetzen, `<dein-passwort>` durch dein
MQTT-Broker-Passwort.

!!! warning "Passwort-Hygiene"
    `/etc/gardena-matter/mqtt.env` sollte nur für den Eigentümer lesbar sein (`chmod 600`).
    Die Datei enthält das Broker-Passwort im Klartext — sie darf nicht world-readable sein.

## In Home Assistant prüfen

Nach dem Start des Publishers dauert es bis zu 30 Sekunden, bis die ersten Werte ankommen.

1. In HA: **Einstellungen → Geräte & Dienste → MQTT**.
2. Ein Gerät **„GARDENA smart Gateway"** sollte mit den konfigurierten Entitäten erscheinen.
3. Unter **Entwicklerwerkzeuge → Zustände** nach `gardena` filtern, um Rohwerte zu sehen.

Falls keine Entitäten erscheinen, die Broker-Logs prüfen — der Publisher protokolliert
Verbindungsversuche in `journalctl -u gardena-mqtt-publisher`.

## Deinstallation

```bash
ssh root@<Gateway-IP> "systemctl stop gardena-mqtt-publisher.service && \
  systemctl disable gardena-mqtt-publisher.service && \
  rm /etc/systemd/system/gardena-mqtt-publisher.service && \
  rm -f /etc/gardena-matter/mqtt.env && \
  rm -f /usr/local/lib/gardena-matter/gardena-mqtt-publisher && \
  systemctl daemon-reload"
```

Die Matter-Bridge wird dabei **nicht berührt** — sie läuft wie zuvor weiter.

## Topic-Referenz

State-Topics folgen dem Muster `<Präfix>/<Hash>/<Ressource>/state`, wobei `<Hash>` ein
stabiler 4-Hex-Zeichen-Bezeichner für das Gerät ist (abgeleitet von der Lemonbeat-ID —
keine personenbezogenen Daten).

Discovery-Topics folgen dem Muster `<HA-Präfix>/sensor/gardena_<Hash>/<Objekt-ID>/config`.

Beispiel (Bodentemperatur-Sensor, Gerätehash `a1b2`):

```
State:     gardena/a1b2/temperature/state        → 18.5
Discovery: homeassistant/sensor/gardena_a1b2/soil_temperature/config  → { ... }
```
