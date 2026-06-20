# Inbetriebnahme

> **Vom Karton zum funktionierenden Matter-Gerät — für normale Smart-Home-Bastler.**
> Kein Löten, kein UART, kein Programmierwissen nötig.

!!! warning "Garantie"
    Custom-Software auf dem Gateway = **Garantieverlust**. Es gibt ein Sicherheitsnetz
    (A/B-Slots, Rückweg), aber Nutzung **auf eigene Gefahr**.

## Was am Ende dabei rauskommt

Dein **GARDENA smart Gateway** erscheint als **Matter-Gerät** in deinem Smart Home — die
GARDENA-Geräte (Sensoren, Mäher …) **lokal und cloudfrei**, gleichzeitig nutzbar in **Home
Assistant, Apple Home und Google Home**. Kein zweites Gerät, keine GARDENA-Cloud.

## Voraussetzungen

- **GARDENA smart Gateway Art. 19005**, am LAN (oder WLAN eingerichtet), mit Strom.
- Die **Geräte-ID** vom Aufkleber auf der Unterseite. Die **ersten 8 Zeichen der ID = das
  Login-Passwort** (gleich für SSH und die Gateway-Weboberfläche).
- Eine laufende **Home-Assistant**-Installation (für den Add-on-Weg unten).
- Ein **Matter-fähiges Smart Home**: Home Assistant 2024.10+, Apple Home oder Google Home.

## Home-Assistant-Add-on — 1-Klick-Einrichtung

Der einfachste Weg: Repository in Home Assistant hinzufügen und das Add-on deployt die Bridge
automatisch auf dein Gateway — kein SSH, kein Bauen, keine Kommandozeile.

### Schritt 1 — Repository hinzufügen

Klicke den Badge unten oder gehe zu **Home Assistant → Einstellungen → Add-ons →
Add-on-Shop** → Drei-Punkte-Menü → **Repositories** → URL einfügen:

```
https://github.com/wuselAUT/gardena-matter-mqtt-bridge
```

[![Add-on-Repository zu Home Assistant hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FwuselAUT%2Fgardena-matter-mqtt-bridge)

!!! note "Ehrlich: ~3 Schritte, nicht 1"
    Home Assistant kann ein Drittanbieter-Add-on nicht ohne deine Bestätigung installieren.
    Nach dem Badge-Klick bestätigst du **„Repository hinzufügen?"**, suchst dann das
    Add-on, installierst es und startest es — grob 3 bestätigte Schritte. Trotzdem deutlich
    einfacher als SSH.

### Schritt 2 — Installieren und konfigurieren

1. **„GARDENA Matter Bridge"** im Add-on-Shop finden und auf **Installieren** klicken.
2. Zum Tab **Konfiguration** des Add-ons wechseln und ausfüllen:
   - **Gateway-Adresse**: IP oder Hostname des Gateways (z. B. `192.168.1.100` oder
     `GARDENA-ab1234` — im Router nachsehen).
   - **Geräte-ID**: die vollständige ID vom Aufkleber auf der Gateway-Unterseite
     (z. B. `a1b2c3d4-e5f6-…`). Das Login-Passwort wird automatisch aus den ersten
     8 Zeichen abgeleitet — kein separates Passwort-Feld.
3. Alle anderen Optionen zunächst auf den Standardwerten lassen.
4. Auf **Speichern** klicken.

### Schritt 3 — Deployen und pairen

1. Zum Tab **Info** des Add-ons wechseln → **Starten** klicken.
2. Die **Web-UI** des Add-ons öffnen (Sidebar-Eintrag „GARDENA Matter" oder die Schaltfläche
   „Web-UI öffnen"). Die Status-Seite zeigt den Deploy-Fortschritt und danach den
   **Pairing-QR-Code** und den **11-stelligen manuellen Code**.
3. In Home Assistant: **Einstellungen → Geräte & Dienste → + Integration hinzufügen →
   Matter**. QR-Code scannen oder manuellen Code eingeben.
4. Home Assistant commissioned das Gerät. Nach einigen Sekunden erscheinen das Gateway und
   seine GARDENA-Geräte als Entitäten.

**Fertig** — kein SSH, keine Kommandozeile.

!!! tip "Gateway-Web-UI"
    Die eingebaute Gateway-Weboberfläche zeigt ebenfalls den Pairing-QR-Code und einen
    Matter-Ein/Aus-Toggle. Im Browser öffnen:
    ```
    https://<gateway-ip>/assets/matter.html
    ```
    Einmal die Warnung für das selbstsignierte Zertifikat bestätigen. Mit dem
    Gateway-Passwort anmelden (erste 8 Zeichen der Geräte-ID).

## Gateway in deiner Smart-Home-App pairen

### Home Assistant

- **Einstellungen → Geräte & Dienste → Matter → Gerät hinzufügen**
- QR-Code scannen **oder** 11-stelligen Code eingeben.
- Pro GARDENA-Gerät erscheinen zwei bis drei Entitäten.

### Apple Home

- **+** → **Zubehör hinzufügen** → **Weitere Optionen** → QR-Code scannen.
- Apple zeigt **„Dieses Zubehör ist nicht zertifiziert"** — auf **„Trotzdem hinzufügen"**
  tippen. Das ist für ein Hobby-Projekt normal (siehe
  [Zertifikate](#matter-zertifikate)).

### Google Home

- **+** → **Gerät einrichten** → **Works with Google** → **Matter** → QR-Code scannen.
- Google erfordert eine Entwickler-Registrierung für Test-Vendor-Geräte — siehe
  [Zertifikate](#matter-zertifikate).

## Eindeutiger Pairing-Code pro Gateway

Jedes Gateway erzeugt beim ersten Start der Bridge einen **zufälligen, einzigartigen
Pairing-Code**. Der Code wird aus einem kryptografischen Schlüssel (Spake2+-Verifier)
abgeleitet und im persistenten Speicher des Gateways gespeichert — er wird **nie geräteüber­greifend
wiederverwendet** und **nie als Klartext in der Prozessliste gespeichert**.

Der QR-Code und der 11-stellige manuelle Code, die im Web-UI angezeigt werden, sind
**einzigartig für genau dieses Gateway**. Zwei Gateways → zwei verschiedene Codes.

Der Code bleibt **stabil über Reboots, Add-on-Updates und OTA-Firmware-Updates**, solange
kein absichtlicher [Jungfräulicher Reset](manual.de.md#jungfraeuli-cher-reset) durchgeführt wird.

## Bleibt nach Stromausfall erhalten ✅

Alle Commissioning-Daten und Konfiguration liegen im **persistenten Speicher** des Gateways.
Nach einem Stromausfall oder Reboot startet das Gateway automatisch und ist **sofort wieder
einsatzbereit** — **kein erneutes Pairing** nötig.

## Deinstallation / Zurück auf Original

Bridge über das Add-on entfernen (Schaltfläche „Vom Gateway deinstallieren" oder
„Original wiederherstellen"). Das Original-Slot-A-System wird nie angetastet; du kannst
jederzeit zurückschalten — siehe [Handbuch](manual.de.md) §5.

## Matter-Zertifikate und der Hinweis „nicht zertifiziertes Gerät"

Diese Bridge ist ein **Hobby-Projekt** und **nicht CSA-zertifiziert**. Sie nutzt das
Matter-SDK mit **Test-Attestierung** (Test-Vendor-ID `0xFFF1`). Jeder Matter-Controller
behandelt sie daher als **Entwicklungs- / nicht zertifiziertes Gerät**. Was das je
Ökosystem bedeutet:

### Home Assistant — zwei Optionen

**Option A — Schnelle Einrichtung (Toggle an):** **„Enable test-net DCL usage"** in den
HA-Matter-Server-Einstellungen aktivieren (Einstellungen → Geräte & Dienste →
Matter-Server → Konfigurieren). HA holt dann die Test-PAA-Root-Zertifikate, auf die die
Attestierungskette der Bridge verweist. Beim Hinzufügen des Geräts kann zusätzlich eine
Bestätigung **„nicht zertifiziertes Gerät"** erscheinen.

**Option B — Eigenes PAA-Root (Toggle aus):** Das Release-Paket enthält ein
projektspezifisches PAA-Root-Zertifikat (`gardena-paa-cert.pem`). Fügst du es dem
HA-Matter-Server-Zertifikatsspeicher hinzu, validiert HA die Attestierungskette der
Bridge **lokal** — ohne DCL-Lookup. **„Enable test-net DCL usage" kann aus bleiben.**

Schritte für Option B:

1. `gardena-paa-cert.pem` vom
   [aktuellen Release](https://github.com/wuselAUT/gardena-matter-mqtt-bridge/releases)
   herunterladen.

2. In den HA-Matter-Server-Zertifikatsspeicher kopieren. Der Matter-Server liest aus
   `--paa-root-cert-dir` (Standard `/data/credentials`):

   ```bash
   # Beispiel über HA SSH-Add-on oder Terminal
   cp gardena-paa-cert.pem /data/credentials/gardena-paa-cert.pem
   ```

   Wenn du `python-matter-server` direkt betreibst, nutze das Verzeichnis aus
   `--paa-root-cert-dir`.

3. **HA Matter-Server neu starten** (Add-on-Neustart oder
   `systemctl restart matter-server`).

4. **„Enable test-net DCL usage" ausgeschaltet lassen** in den Matter-Server-Einstellungen.

5. **Bridge commissionen** — HA validiert die Attestierungskette gegen das lokal
   hinterlegte PAA-Root, kein DCL-Lookup nötig.

!!! note "Option-B-Hinweise"
    - Der Hinweis **„nicht zertifiziertes Gerät"** kann trotzdem erscheinen — er wird
      durch die Certification Declaration (CD) gesteuert, die test-signiert bleibt. Nur
      eine bezahlte CSA-Zertifizierung entfernt ihn. Option B beseitigt nur den Bedarf
      am *DCL-Toggle*.
    - Option B hilft **nicht** bei Apple Home oder Google Home — die nutzen eigene
      Trust-Modelle (siehe unten). Die Regeln je Ökosystem bleiben unverändert.
    - Beim Wechsel zwischen Option A und B ist erneutes Commissioning nötig.

### Apple Home — funktioniert, mit Warnung

Apple Home akzeptiert die Test-Vendor-ID `0xFFF1`. Beim Einrichten erscheint
**„Dieses Zubehör ist nicht zertifiziert"** — auf **„Trotzdem hinzufügen"** tippen.
Keine weitere Konfiguration nötig. Das eigene PAA-Root aus Option B oben hat hier keinen
Effekt.

### Google Home — extra Schritt nötig

Google Home ist am strengsten: Ein Test-VID-Gerät lässt sich nur commissionen, wenn du
eine passende **Matter-Integration (Test-VID/PID) in der
[Google Home Developer Console](https://developers.home.google.com/)** registrierst.
Ohne diese Registrierung lehnt Google Home es als **„Kein Matter-zertifiziertes Gerät"**
ab. Das eigene PAA-Root hat hier keinen Effekt.

### Vollständig warnungsfrei?

Nur **echte CSA-Zertifizierung** (bezahlte Mitgliedschaft, registrierte Vendor-ID und
Zertifizierungstests) entfernt die Warnung in allen Ökosystemen — für ein Hobby-Projekt
nicht realistisch. Der empfohlene, voll funktionierende Weg ist **Home Assistant**
(Option A oder B oben); das Gerät kann dann per Matter **Multi-Admin** an **Apple Home /
Google Home** weitergegeben werden, wo die oben genannten Regeln je Ökosystem gelten.

## Hilfe

- **Gateway nicht gefunden**: IP-Adresse im Router nachsehen und manuell eingeben.
- **Commissioning klappt nicht**: Gateway und Smart-Home-Hub im **gleichen Netzwerk**;
  mDNS/Bonjour muss im Netz funktionieren.
- **„Nicht zertifiziertes Gerät"**: siehe [Matter-Zertifikate](#matter-zertifikate) oben.
- Weitere Details + technischer Hintergrund: [Handbuch](manual.de.md).

## MQTT-Frontend (optional)

Der MQTT-Publisher läuft parallel zur Matter-Bridge — unabhängig, beide immer aktiv.
In der Add-on-Konfiguration aktivieren und auf den MQTT-Broker zeigen.
Vollständige Einrichtung: [MQTT](mqtt.de.md).
