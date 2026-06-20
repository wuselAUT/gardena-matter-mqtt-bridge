# GARDENA Matter & MQTT Bridge — Home Assistant add-on

[![Add the repository to your Home Assistant.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository=https%3A%2F%2Fgithub.com%2FwuselAUT%2Fgardena-matter-mqtt-bridge)
[![Open this add-on in your Home Assistant.](https://my.home-assistant.io/badges/supervisor_addon.svg)](https://my.home-assistant.io/redirect/supervisor_addon/?addon=gardena_matter_bridge&repository_url=https%3A%2F%2Fgithub.com%2FwuselAUT%2Fgardena-matter-mqtt-bridge)

> **One-click install:** the left button adds this add-on repository to Home Assistant, the right one jumps
> straight to the add-on page. **Active from go-live (public release):** the buttons point at the public repo
> `wuselAUT/gardena-matter-mqtt-bridge` — while it is still private, the click leads nowhere yet.

Installs the **GARDENA Matter & MQTT Bridge** on the GARDENA smart Gateway (19005)
— **no SSH, no building, no copy-pasting code**. You only enter the **device ID**
from the sticker (the login password is its first 8 characters, the add-on
derives it automatically); the add-on enables SSH through the official gateway
endpoint, downloads the pre-built bridge from a signed GitHub release and deploys
it. Afterwards you add the gateway to Home Assistant as a **Matter device**.

> **Status:** the add-on skeleton, the SSH/deploy orchestration, the commissioning
> display and the status UI are built and unit-tested. **The deploy is now active**
> — pressing *Re-deploy* runs the real download + SSH deploy (hash-pinned,
> fail-closed). The **first real deploy onto a gateway and the Matter commissioning
> in HA are still done together with the user as a live test**.

## What it does

1. **Enable SSH on the gateway** — via the official `/ssh_access_*` flow (no raw
   SSH hack). The add-on generates its own SSH keypair and sends only the
   **public key** to the gateway.
2. **Deploy the bridge** — the three install scripts
   (`install_bridge.sh`, `install_web_ui.sh`, `install_restore.sh`) are
   run idempotently. The bridge artifact comes from a **GitHub release** and is
   checked by **SHA-256 hash** before the deploy (hard integrity gate; a
   cryptographic signature is an optional extra step).
3. **Show commissioning** — the QR code and setup code are shown in the add-on
   UI; you enter them in Home Assistant under *Add device → Matter*.

## Options

| Option | Type | Meaning |
|---|---|---|
| `gateway_host` | str | IP/hostname of the gateway (e.g. `GARDENA-123456` or `192.168.1.100`) |
| `device_id` | password (secret) | Device ID from the sticker on the underside of the gateway (e.g. `a1b2c3d4-…`). The login password is derived automatically from its **first 8 characters**; the value is stored as a secret and **never logged**. |
| `enable_web_ui` | bool | Enable the ingress status UI (default: on) |
| `disable_ssh_after_deploy` | bool | Turn SSH back off after the deploy (the key stays installed and survives firmware updates) |
| `github_repo` | str | Source of the bridge release (`owner/name`) |
| `release_tag` | str | Release tag (default `v0.1.0`, matching the pinned `bridge-release.lock`) |
| `github_token` | password (secret) | Optional. Only needed while the bridge release repo is **private**: a GitHub token with read access to download the release asset. Leave empty for a public repo. Stored as a secret and **never logged**. |

## Onboarding (steps)

1. Add the add-on repository in Home Assistant (repo URL → *Add-on Store → ⋮ → Repositories*).
2. Install **GARDENA Matter & MQTT Bridge**.
3. In the add-on **options**, set `gateway_host` and `device_id` (device ID from
   the sticker), save. The login password is derived automatically from the
   first 8 characters of the device ID — no separate password field.
4. **Start** the add-on and open the **web UI** (ingress, sidebar).
5. Trigger the **deploy** (re-deploy button).
6. Enter the QR/setup code from the UI in Home Assistant under
   *Settings → Devices & services → Add device → Matter*.

## After installation

**The add-on is an installer/updater — not a runtime component.** Once the deploy
has finished, the bridge runs **standalone on the gateway**: it is reboot-proof
and survives firmware updates (OTA) via the restore service. Matter then talks
**directly gateway ↔ Home Assistant** — the add-on is **not in the data path**.

This means:

- You may **stop or even uninstall** this add-on after a successful deploy — the
  **pairing stays intact** and the GARDENA devices keep working in Home Assistant.
- **Re-open / start it again only** to update the bridge to a new release, or to
  re-deploy after a factory reset of the gateway.
- The **pairing QR / setup code** and the **Matter on/off** toggle are also
  available **directly on the gateway's own page** (`/assets/matter.html`),
  without the add-on.

## Security

- The sticker password is a **HA secret** and is **never logged**, never
  committed, never mirrored into error messages.
- The add-on runs in **Home Assistant**, not on the gateway — the GARDENA cloud
  is not touched.
- Reversible: the bridge is deployed into the writable overlay (no flash, no
  slot change). Uninstall scripts are provided.

## Distribution / publication

This add-on first lives in the **private** workshop repo. The public migration
(its own HA add-on repository) is a later documentation step and is done
**without any AI trace** (see `DOCS.md`).

---

## 🇩🇪 Deutsch

# GARDENA Matter & MQTT Bridge — Home-Assistant-Add-on

> **Ein-Klick-Installation:** Der linke Button (oben) fügt dieses Add-on-Repository zu Home Assistant hinzu, der
> rechte springt direkt zur Add-on-Seite. **Aktiv ab der Public-Schaltung** (Go-Live): Die Buttons zeigen auf das
> öffentliche Repo `wuselAUT/gardena-matter-mqtt-bridge` — solange es privat ist, läuft der Klick noch ins Leere.

Installiert die **GARDENA Matter & MQTT Bridge** auf dem GARDENA smart Gateway (19005)
— **ohne SSH, ohne Bauen, ohne Code-Abtippen**. Du trägst nur die **Geräte-ID**
vom Aufkleber ein (das Login-Passwort sind die ersten 8 Zeichen daraus, das
Add-on leitet es automatisch ab); das Add-on aktiviert SSH über den offiziellen
Gateway-Endpunkt, lädt die fertig gebaute Bridge aus einem signierten
GitHub-Release und deployt sie. Anschließend fügst du das Gateway in Home
Assistant als **Matter-Gerät** hinzu.

> **Status:** Add-on-Gerüst, SSH-/Deploy-Orchestrierung, Commissioning-Anzeige
> und Status-UI sind gebaut und unit-getestet. **Der Deploy ist jetzt aktiv** —
> ein Klick auf *Neu deployen* führt den echten Download + SSH-Deploy aus
> (hash-gepinnt, fail-closed). Der **erste echte Deploy auf ein Gateway sowie das
> Matter-Commissioning in HA laufen weiterhin gemeinsam mit dem Nutzer als
> Live-Test**.

## Was es tut

1. **SSH am Gateway aktivieren** — über den offiziellen `/ssh_access_*`-Flow
   (kein Roh-SSH-Hack). Das Add-on erzeugt ein eigenes SSH-Keypair und sendet
   nur den **Public-Key** an das Gateway.
2. **Bridge deployen** — die drei Install-Skripte
   (`install_bridge.sh`, `install_web_ui.sh`, `install_restore.sh`)
   werden idempotent ausgeführt. Das Bridge-Artefakt kommt aus einem
   **GitHub-Release** und wird vor dem Deploy per **SHA256-Hash** geprüft
   (hartes Integritäts-Gate; eine kryptographische Signatur ist ein optionaler
   Zusatz-Schritt).
3. **Commissioning anzeigen** — QR-Code und Setup-Code werden in der Add-on-UI
   gezeigt; du fügst sie in Home Assistant unter
   *Gerät hinzufügen → Matter* ein.

## Optionen

| Option | Typ | Bedeutung |
|---|---|---|
| `gateway_host` | str | IP/Hostname des Gateways (z. B. `GARDENA-123456` oder `192.168.1.100`) |
| `device_id` | password (Secret) | Geräte-ID vom Aufkleber auf der Geräteunterseite (z. B. `a1b2c3d4-…`). Das Login-Passwort wird automatisch aus den **ersten 8 Zeichen** abgeleitet; der Wert wird als Secret gespeichert und **nie geloggt**. |
| `enable_web_ui` | bool | Ingress-Status-UI aktivieren (Default: an) |
| `disable_ssh_after_deploy` | bool | SSH nach dem Deploy wieder sperren (Key bleibt OTA-fest hinterlegt) |
| `github_repo` | str | Quelle des Bridge-Release (`owner/name`) |
| `release_tag` | str | Release-Tag (Default `v0.1.0`, passend zum gepinnten `bridge-release.lock`) |
| `github_token` | password (Secret) | Optional. Nur nötig, solange das Bridge-Release-Repo **privat** ist: ein GitHub-Token mit Lesezugriff, um das Release-Asset herunterzuladen. Für ein öffentliches Repo leer lassen. Als Secret gespeichert und **nie geloggt**. |

## Onboarding (Schritte)

1. Add-on-Repository in Home Assistant hinzufügen (Repo-URL → *Add-on Store → ⋮ → Repositories*).
2. **GARDENA Matter & MQTT Bridge** installieren.
3. In den Add-on-**Optionen** `gateway_host` und `device_id` (Geräte-ID vom
   Aufkleber) eintragen, speichern. Das Login-Passwort wird automatisch aus den
   ersten 8 Zeichen der Geräte-ID abgeleitet — kein separates Passwort-Feld.
4. Add-on **starten** und die **Web-UI** (Ingress, Seitenleiste) öffnen.
5. Den **Deploy** anstoßen (Re-Deploy-Knopf).
6. QR-/Setup-Code aus der UI in Home Assistant unter
   *Einstellungen → Geräte & Dienste → Gerät hinzufügen → Matter* eingeben.

## Nach der Installation

**Das Add-on ist ein Installer/Updater — kein Laufzeit-Bestandteil.** Nach dem
abgeschlossenen Deploy läuft die Bridge **eigenständig auf dem Gateway**:
reboot-fest und OTA-überlebend (über den Restore-Dienst). Matter spricht danach
**direkt Gateway ↔ Home Assistant** — das Add-on ist **nicht im Datenpfad**.

Das heißt:

- Du darfst dieses Add-on nach einem erfolgreichen Deploy **stoppen oder sogar
  deinstallieren** — das **Pairing bleibt erhalten** und die GARDENA-Geräte
  funktionieren in Home Assistant weiter.
- **Wieder öffnen / anschalten nur**, um die Bridge auf ein neues Release zu
  aktualisieren, oder um nach einem Factory-Reset des Gateways neu zu deployen.
- **Pairing-QR / Setup-Code** und der **Matter-An/Aus**-Schalter gibt es auch
  **direkt auf der Gateway-eigenen Seite** (`/assets/matter.html`), ganz ohne
  das Add-on.

## Sicherheit

- Das Aufkleber-Passwort ist ein **HA-Secret** und wird **nie geloggt**, nie
  committet, nie in Fehlermeldungen gespiegelt.
- Das Add-on läuft in **Home Assistant**, nicht am Gateway — die GARDENA-Cloud
  wird nicht berührt.
- Reversibel: Die Bridge wird ins beschreibbare Overlay deployt (kein Flash,
  kein Slot-Eingriff). Uninstall-Skripte sind vorhanden.

## Distribution / Veröffentlichung

Dieses Add-on lebt zunächst im **privaten** Werkstatt-Repo. Die öffentliche
Migration (eigenes HA-Add-on-Repository) ist ein späterer Doku-Schritt und
erfolgt **ohne AI-Spur** (siehe `DOCS.md`).
