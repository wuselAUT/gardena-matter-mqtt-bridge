# GARDENA Matter & MQTT Bridge — Documentation

## Architecture

```
Home Assistant
  └─ add-on container (supervisor-managed)
       ├─ config.yaml        options + schema, ingress :8099
       ├─ Dockerfile         ghcr.io/hassio-addons/base:18.2.0 + openssh-client + python3
       ├─ run.sh             reads options, generates SSH keypair, starts the status UI
       ├─ orchestrate.py     SSH flow + deploy orchestration — pure, unit-testable
       ├─ status.py          commissioning/status logic (matter-status.json) — pure, testable
       ├─ web_ui.py          ingress HTTP server (stdlib) — thin glue layer
       ├─ web/               index.html + app.js + style.css (status UI)
       └─ install-scripts/   install_bridge.sh, install_web_ui.sh, install_restore.sh
```

## How the deploy works

1. **SSH access** — the add-on uses the official `/ssh_access_*` flow (no raw SSH hack).
   It generates its own SSH keypair and sends only the **public key** to the gateway.
2. **Download + verify** — the bridge artifact (`gardena-bridge-<tag>.tar.gz`) is pulled
   from a GitHub release and verified against the pinned SHA-256 hash in
   `bridge-release.lock` before anything is deployed (hard integrity gate: mismatch =
   fail-closed, no deploy).
3. **Deploy** — the three install scripts run **inside the add-on container** (which has
   SSH/SCP to the gateway). They SCP the files to the gateway themselves.
   Order: `install_bridge.sh` → `install_web_ui.sh` → `install_restore.sh`.
4. **Commissioning** — QR code and setup code from `matter-status.json` are shown in the
   add-on UI; you enter them in Home Assistant under *Add device → Matter*.

## After installation

**The add-on is an installer/updater — not a runtime component.** Once deployed, the
bridge runs **standalone on the gateway**: reboot-proof, OTA-surviving (via the restore
service). Matter talks **directly gateway ↔ Home Assistant** — the add-on is **not in
the data path**.

- You may **stop or uninstall** this add-on after a successful deploy — the **pairing
  stays intact** and GARDENA devices keep working in Home Assistant.
- **Re-open only** to update the bridge to a new release, or to re-deploy after a
  gateway factory reset.
- The **pairing QR / setup code** and the **Matter on/off toggle** are also available
  **directly on the gateway page** (`/assets/matter.html`) without the add-on.

## Integrity and security

- **SHA-256 hash pinning** (`bridge-release.lock`) is the hard integrity gate. An
  optional cryptographic signature is a follow-up step, not a replacement.
- The `device_id` (source of the login password — its first 8 characters) is **never
  logged**, never mirrored into error messages, never committed anywhere.
- The `github_token` (if set, for a private bridge release repo) is **never logged**.
- The add-on runs in Home Assistant, not on the gateway — the GARDENA cloud is not
  touched.

## Release bundle

`build-bridge-release.sh <tag>` bundles the existing build outputs into one deterministic
tarball `gardena-bridge-<tag>.tar.gz` and prints its SHA-256. The maintainer creates the
GitHub release and pins the hash in `bridge-release.lock`.

| Member | Purpose |
|---|---|
| `chip-bridge-app.stripped` | cross-built bridge binary (MIPS, fp_abi=0) |
| `matter_libs.tar.gz` | matching shared libs (unpacked by `install_bridge.sh`) |
| `VERSION` | plain-text version / build stamp |

## SSH flow (official gateway API)

1. `POST /login {"password": <sticker PW>}` → `{"session": <hex>}`
2. `POST /ssh_access_credentials {<add-on public key>}` (header `X-Session`)
3. `PUT /ssh_access_enable {"enable": true}` (header `X-Session`)
4. `ssh root@<gateway>` with the add-on **private** key → run the 3 install scripts
5. optional `PUT /ssh_access_enable {"enable": false}` (key stays OTA-proof)

The login endpoint is `/login` (not `/authentication/login`).
`/ssh_access_credentials` requires **POST** (not PUT).
`/ssh_access_enable` uses **PUT**.

## Options

| Option | Type | Meaning |
|---|---|---|
| `gateway_host` | str | IP/hostname of the gateway (e.g. `GARDENA-123456` or `192.168.1.100`) |
| `device_id` | password | Device ID from the sticker. Login PW = first 8 characters. **Never logged.** |
| `enable_web_ui` | bool | Show the ingress status UI (default: on) |
| `disable_ssh_after_deploy` | bool | Turn SSH off after deploy (key stays installed) |
| `github_repo` | str | Source of the bridge release (`owner/name`) |
| `release_tag` | str | Release tag (default `v0.1.4`, matching `bridge-release.lock`) |
| `github_token` | password | Optional. Only needed for a **private** bridge release repo. **Never logged.** |
| `enable_mqtt` | bool | Enable the MQTT publisher service (additive; Matter is not affected) |
| `mqtt_broker_host` | str | IP/hostname of the MQTT broker |
| `mqtt_broker_user` | str | MQTT broker username |
| `mqtt_broker_password` | password | MQTT broker password. **Never logged.** |
| `mqtt_topic_prefix` | str | Topic prefix (default `gardena`) |

## Troubleshooting — what to include when reporting a problem

If something doesn't work, please open a GitHub issue with as much of the following as you can — it makes debugging much faster:

- **Versions:** the add-on version (Settings → Add-ons → GARDENA Matter & MQTT Bridge), your Home Assistant version, and the gateway model (GARDENA smart Gateway, art. 19005).
- **What happened:** the exact error message and the steps that led to it (what you entered / clicked).
- **The add-on log** (Settings → Add-ons → GARDENA Matter & MQTT Bridge → *Log*) — this is the single most useful item. Copy the relevant lines.
- **Matter side:** if pairing in Home Assistant failed, the message shown under *Settings → Devices & Services → Add device → Matter*.
- **Your devices:** which GARDENA devices (sensors, mower, …) and how many.
- **Gateway still healthy?** Does the GARDENA app / cloud still show your devices? (Confirms the gateway itself is fine.)
- **Advanced (optional):** if you have SSH access to the gateway, the bridge log: `journalctl -u gardena-matter-bridge -n 100 --no-pager`.

> **⚠️ Redact secrets before posting.** Do **not** share your **device ID**, the **sticker password**, the **pairing / setup code** (the QR code or the 11-digit manual code), or your real local IP addresses. The pairing code is a secret that lets anyone commission your gateway — replace such values with `…` / `<redacted>`.

---

## 🇩🇪 Deutsch

# GARDENA Matter & MQTT Bridge — Dokumentation

## Architektur

```
Home Assistant
  └─ Add-on-Container (Supervisor-managed)
       ├─ config.yaml        Optionen + Schema, Ingress :8099
       ├─ Dockerfile         ghcr.io/hassio-addons/base:18.2.0 + openssh-client + python3
       ├─ run.sh             Optionen lesen, SSH-Keypair erzeugen, Status-UI starten
       ├─ orchestrate.py     SSH-Flow + Deploy-Orchestrierung — rein, unit-testbar
       ├─ status.py          Commissioning-/Status-Logik (matter-status.json) — rein, testbar
       ├─ web_ui.py          Ingress-HTTP-Server (stdlib) — duenne Glue-Schicht
       ├─ web/               index.html + app.js + style.css (Status-UI)
       └─ install-scripts/   install_bridge.sh, install_web_ui.sh, install_restore.sh
```

## Wie der Deploy ablaeuft

1. **SSH-Zugang** — das Add-on nutzt den offiziellen `/ssh_access_*`-Flow (kein Roh-SSH-Hack).
   Es erzeugt ein eigenes SSH-Keypair und sendet nur den **Public-Key** ans Gateway.
2. **Download + Verifikation** — das Bridge-Artefakt (`gardena-bridge-<tag>.tar.gz`) wird
   aus einem GitHub-Release gezogen und vor dem Deploy gegen den gepinnten SHA-256-Hash
   in `bridge-release.lock` geprueft (hartes Integritaets-Gate: Mismatch = fail-closed,
   kein Deploy).
3. **Deploy** — die drei Install-Skripte laufen **im Add-on-Container** (der hat SSH/SCP
   zum Gateway). Sie uebertragen die Dateien per SCP selbst ans Gateway.
   Reihenfolge: `install_bridge.sh` → `install_web_ui.sh` → `install_restore.sh`.
4. **Commissioning** — QR-Code und Setup-Code aus `matter-status.json` werden in der
   Add-on-UI angezeigt; du traegst sie in Home Assistant unter *Geraet hinzufuegen → Matter* ein.

## Nach der Installation

**Das Add-on ist ein Installer/Updater — kein Laufzeit-Bestandteil.** Nach dem Deploy
laeuft die Bridge **eigenstaendig auf dem Gateway**: reboot-fest, OTA-ueberlebend
(ueber den Restore-Dienst). Matter spricht **direkt Gateway ↔ Home Assistant** — das
Add-on ist **nicht im Datenpfad**.

- Du darfst das Add-on nach einem erfolgreichen Deploy **stoppen oder deinstallieren** —
  das **Pairing bleibt erhalten** und die GARDENA-Geraete funktionieren weiter.
- **Nur wieder oeffnen**, um die Bridge auf ein neues Release zu aktualisieren oder
  nach einem Factory-Reset des Gateways neu zu deployen.
- **Pairing-QR / Setup-Code** und der **Matter-An/Aus-Schalter** sind auch **direkt auf
  der Gateway-Seite** (`/assets/matter.html`) ohne das Add-on erreichbar.

## Integritaet und Sicherheit

- **SHA-256-Hash-Pinning** (`bridge-release.lock`) ist das harte Integritaets-Gate.
  Eine optionale kryptographische Signatur ist ein Folge-Schritt, kein Ersatz.
- Die `device_id` (Quelle des Login-Passworts — die ersten 8 Zeichen) wird **nie
  geloggt**, nie in Fehlermeldungen gespiegelt, nie committet.
- Das `github_token` (falls gesetzt, fuer ein privates Bridge-Release-Repo) wird
  **nie geloggt**.
- Das Add-on laeuft in Home Assistant, nicht am Gateway — die GARDENA-Cloud wird
  nicht beruehrt.

## Release-Bundle

`build-bridge-release.sh <tag>` schnuert die vorhandenen Build-Outputs zu einem
deterministischen Tarball `gardena-bridge-<tag>.tar.gz` und gibt dessen SHA-256 aus.
Der Maintainer erstellt das GitHub-Release und pinnt den Hash in `bridge-release.lock`.

| Member | Zweck |
|---|---|
| `chip-bridge-app.stripped` | Cross-gebaute Bridge-Binary (MIPS, fp_abi=0) |
| `matter_libs.tar.gz` | Passende Shared-Libs (wird von `install_bridge.sh` entpackt) |
| `VERSION` | Klartext-Versions-/Build-Stempel |

## SSH-Flow (offizieller Gateway-API)

1. `POST /login {"password": <Aufkleber-PW>}` → `{"session": <hex>}`
2. `POST /ssh_access_credentials {<Add-on-Public-Key>}` (Header `X-Session`)
3. `PUT /ssh_access_enable {"enable": true}` (Header `X-Session`)
4. `ssh root@<gateway>` mit dem Add-on-**Private**-Key → Deploy der 3 Install-Skripte
5. optional `PUT /ssh_access_enable {"enable": false}` (Key bleibt OTA-fest)

Der Login-Endpunkt ist `/login` (nicht `/authentication/login`).
`/ssh_access_credentials` benoetigt **POST** (nicht PUT).
`/ssh_access_enable` nutzt **PUT**.

## Optionen

| Option | Typ | Bedeutung |
|---|---|---|
| `gateway_host` | str | IP/Hostname des Gateways (z. B. `GARDENA-123456` oder `192.168.1.100`) |
| `device_id` | password | Geraete-ID vom Aufkleber. Login-PW = erste 8 Zeichen. **Nie geloggt.** |
| `enable_web_ui` | bool | Ingress-Status-UI anzeigen (Standard: an) |
| `disable_ssh_after_deploy` | bool | SSH nach Deploy sperren (Key bleibt installiert) |
| `github_repo` | str | Quelle des Bridge-Release (`owner/name`) |
| `release_tag` | str | Release-Tag (Standard `v0.1.4`, passend zu `bridge-release.lock`) |
| `github_token` | password | Optional. Nur fuer ein **privates** Bridge-Release-Repo. **Nie geloggt.** |
| `enable_mqtt` | bool | MQTT-Publisher-Dienst aktivieren (additiv; Matter wird nicht beeinflusst) |
| `mqtt_broker_host` | str | IP/Hostname des MQTT-Brokers |
| `mqtt_broker_user` | str | MQTT-Broker-Benutzername |
| `mqtt_broker_password` | password | MQTT-Broker-Passwort. **Nie geloggt.** |
| `mqtt_topic_prefix` | str | Topic-Praefix (Standard `gardena`) |

## Fehlersuche — was du bei einer Problemmeldung angeben solltest

Wenn etwas nicht funktioniert, öffne bitte ein GitHub-Issue mit möglichst vielen der folgenden Angaben — das macht die Fehlersuche viel schneller:

- **Versionen:** Add-on-Version (Einstellungen → Add-ons → GARDENA Matter & MQTT Bridge), deine Home-Assistant-Version und das Gateway-Modell (GARDENA smart Gateway, Art. 19005).
- **Was passiert ist:** die genaue Fehlermeldung und die Schritte, die dazu geführt haben (was du eingegeben / geklickt hast).
- **Das Add-on-Log** (Einstellungen → Add-ons → GARDENA Matter & MQTT Bridge → *Log*) — die mit Abstand nützlichste Einzelangabe. Kopiere die relevanten Zeilen.
- **Matter-Seite:** falls das Pairing in Home Assistant fehlschlug, die Meldung unter *Einstellungen → Geräte & Dienste → Gerät hinzufügen → Matter*.
- **Deine Geräte:** welche GARDENA-Geräte (Sensoren, Mäher, …) und wie viele.
- **Gateway noch gesund?** Zeigt die GARDENA-App / Cloud deine Geräte weiterhin an? (Bestätigt, dass das Gateway selbst in Ordnung ist.)
- **Fortgeschritten (optional):** falls du SSH-Zugriff auf das Gateway hast, das Bridge-Log: `journalctl -u gardena-matter-bridge -n 100 --no-pager`.

> **⚠️ Secrets vor dem Posten schwärzen.** Teile **niemals** deine **Geräte-ID**, das **Aufkleber-Passwort**, den **Pairing-/Setup-Code** (den QR-Code oder den 11-stelligen Manual-Code) oder deine echten lokalen IP-Adressen. Der Pairing-Code ist ein Geheimnis, mit dem jeder dein Gateway koppeln könnte — ersetze solche Werte durch `…` / `<geschwärzt>`.
