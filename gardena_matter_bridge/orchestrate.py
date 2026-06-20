#!/usr/bin/env python3
"""orchestrate.py — SSH-Flow + Deploy-Orchestrierung.

Kapselt die gesamte mockbare Orchestrierungs-Logik des HA-Add-ons als reine,
gut testbare Funktionen/Klassen. Alle externen Effekte (HTTP zum
Gateway, ssh/scp, Release-Download) gehen ueber schmale, injizierbare
Runner -> in Unit-Tests komplett gemockt, KEIN echtes Gateway/Netz/HA noetig.

Release-Integritaet:
  Das primaere, harte Integritaets-Gate ist SHA256-Hash-Pinning (python
  `hashlib`, pure-python): das Release-Artefakt wird VOR jedem
  Deploy gegen einen erwarteten Hash geprueft -> Mismatch = harter Abbruch.
  Eine echte kryptographische Signatur ist ein OPTIONALER Folge-Schritt, der
  das Hash-Gate NICHT ersetzt (nur zusaetzlich prueft, wenn ein Verifier
  injiziert ist).

Offizieller SSH-Flow:
  1. POST /login {"password": <Aufkleber-PW>}                 -> {"session": <hex>}
  2. POST /ssh_access_credentials {<Add-on-Public-Key>}        (X-Session)
  3. PUT  /ssh_access_enable      {"enable": true}            (X-Session)
  4. ssh root@<gateway> mit Add-on-PRIVATE-Key -> Deploy der 3 Install-Skripte
  5. optional: PUT /ssh_access_enable {"enable": false}        (Key bleibt OTA-fest)

Hinweis: Der Login-Endpunkt ist /login, NICHT /authentication/login
(live bewiesen: POST /authentication/login=401, POST /login=200+Session).

Hinweis: /ssh_access_credentials braucht POST, NICHT PUT (live bewiesen:
PUT=405, POST=204). /ssh_access_enable bleibt PUT (live 204).

Bridge-Artefakt: GitHub-Release -> SHA256-Hash-Check VOR dem Deploy.

Credential-Modell:
  Es gibt nur EIN Credential-Feld: `device_id`. Das Login-Passwort ist
  `device_id[:8]` (die ersten 8 Zeichen der Geraete-ID, vorher getrimmt). Es gibt
  KEIN separates `label_password` mehr. `device_id` ist ein Secret (Schema-Typ
  `password`) und wird NIE geloggt.

Hard Constraints:
  - device_id (= Quelle des Login-PW) wird NIE geloggt, NIE in Exceptions/Repr
    gespiegelt; das abgeleitete Passwort ebenso wenig.
  - SshCredentials-JSON-Feldname: wir senden defensiv ALLE plausiblen
    Feldnamen-Kandidaten ('key', 'public_key', 'ssh_public_key') gleichzeitig im
    Body, sodass das Backend den passenden nimmt.
"""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import subprocess
import tarfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence


# ── Konstanten ───────────────────────────────────────────────────────────────
# Der Login-Endpunkt ist /login (live bewiesen: /authentication/login = 401).
LOGIN_PATH = "/login"
SSH_CREDENTIALS_PATH = "/ssh_access_credentials"
SSH_ENABLE_PATH = "/ssh_access_enable"

# SshCredentials-Feldname: defensiv alle Kandidaten senden.
SSH_PUBKEY_FIELD_CANDIDATES = ("key", "public_key", "ssh_public_key")

# Die drei vorhandenen Install-Skripte (Reihenfolge bindend: Bridge -> Web-UI -> Restore).
INSTALL_SCRIPTS = (
    "install_bridge.sh",
    "install_web_ui.sh",
    "install_restore.sh",
)

# MQTT-Publisher-Install-Skript (additiv, optional).
# Wird NUR ausgefuehrt wenn enable_mqtt=true (opt-in; Matter laeuft weiter, additiv).
INSTALL_MQTT_SCRIPT = "install_mqtt_publisher.sh"

# Name des MQTT-Publisher-Unterverzeichnisses im Release-Bundle.
BUNDLE_MQTT_PUBLISHER_DIR = "mqtt-publisher"
# Pflicht-Member im mqtt-publisher/-Unterverzeichnis (harter Abbruch wenn enable_mqtt=true).
BUNDLE_MQTT_PUBLISHER_REQUIRED = (
    "gardena-mqtt-publisher",       # MIPS-Binary (gebaute gardena-mqtt-publisher-Binary)
    "gardena-mqtt-publisher.service",
    "install_mqtt_publisher.sh",
)

# Container-lokaler Pfad der gespiegelten Install-Skripte (laufen IM
# Add-on-Container, nicht auf dem Gateway). Vgl. Dockerfile/run.sh: ADDON_DIR=/opt/gardena.
INSTALL_SCRIPTS_DIR = "/opt/gardena/install-scripts"

# Release-Bundle-Member: EIN Tarball gardena-bridge-<tag>.tar.gz
# mit flacher Struktur Binary + Libs-Tarball + VERSION + web-ui/-Unterverzeichnis.
BUNDLE_BINARY_NAME = "chip-bridge-app.stripped"
BUNDLE_LIBS_NAME = "matter_libs.tar.gz"
BUNDLE_VERSION_NAME = "VERSION"
# web-ui/-Unterverzeichnis im Bundle -- Gateway-Laufzeit-Payload.
BUNDLE_WEB_UI_DIR = "web-ui"
# Laufzeit-Dateien, die im Bundle-Unterverzeichnis web-ui/ ERWARTET werden
# (kein build_toggle.sh / gardena-toggle.c / storm_test.sh = Dev-Artefakte).
BUNDLE_WEB_UI_REQUIRED = (
    "gardena-toggle",
    "matter.html",
    "qrcode.min.js",
)
# Alle Laufzeit-Member (fuer Build-Skript-Verifikation / Bundle-Listing).
BUNDLE_WEB_UI_ALL_RUNTIME = (
    "gardena-toggle",
    "matter.html",
    "qrcode.min.js",
    "gardena-matter-toggle.service",
    "gardena-matter-toggle.socket",
    "gardena-matter-status.service",
    "gardena-matter-status.timer",
    "gardena-matter-restore.service",
    "gardena-matter-restore.path",
    "gardena-matter-restore.sh",
    "update-matter-status.sh",
)
# Dev-Artefakte, die NICHT im Bundle sein duerfen.
BUNDLE_WEB_UI_DEV_ARTIFACTS = (
    "build_toggle.sh",
    "gardena-toggle.c",
    "storm_test.sh",
)

# Pin-Quelle = bridge-release.lock neben diesem Modul.
RELEASE_LOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bridge-release.lock")
# Marker, der einen NOCH NICHT gepinnten Platzhalter-Hash erkennt -> fail-closed.
PLACEHOLDER_SHA256_MARKER = "PLACEHOLDER"


class OrchestrationError(Exception):
    """Fehler im Orchestrierungs-Flow mit klarer Nutzer-Meldung (PW-frei)."""


# Laenge des Login-Passworts = die ersten N Zeichen der Geraete-ID.
LOGIN_PASSWORD_LEN = 8


def derive_login_password(device_id: str) -> str:
    """Leitet das Login-Passwort aus der Geraete-ID ab (= erste 8 Zeichen).

    Das Aufkleber-Passwort = die ersten 8 Zeichen der Geraete-ID (Gateway-Login
    nutzt nur dieses Passwort). `device_id` wird vorher getrimmt (robust gegen
    versehentliche Leerzeichen/Newlines aus dem Options-Feld).

    Leere/zu-kurze device_id -> harter Abbruch (OrchestrationError). Es wird
    NIE der Wert selbst in die Fehlermeldung gespiegelt (Secret-Hygiene).
    """
    trimmed = (device_id or "").strip()
    if not trimmed:
        raise OrchestrationError(
            "device_id fehlt — bitte die Geraete-ID (Aufkleber-Unterseite) in "
            "den Add-on-Optionen eintragen."
        )
    if len(trimmed) < LOGIN_PASSWORD_LEN:
        raise OrchestrationError(
            "device_id ist zu kurz — die Geraete-ID muss mindestens "
            f"{LOGIN_PASSWORD_LEN} Zeichen lang sein (Login-Passwort = erste "
            f"{LOGIN_PASSWORD_LEN} Zeichen)."
        )
    return trimmed[:LOGIN_PASSWORD_LEN]


@dataclass
class HttpResponse:
    status: int
    body: str

    def json(self) -> dict:
        return json.loads(self.body)


# ── Runner-Interfaces (in Tests gemockt) ─────────────────────────────────────
@dataclass
class GatewayClient:
    """Spricht die offizielle Gateway-HTTPS-API — alle Methoden injizierbar.

    `http` ist eine Funktion (method, url, headers, json_body) -> HttpResponse.
    """

    host: str
    http: Callable[..., HttpResponse]
    session: Optional[str] = None

    def _url(self, path: str) -> str:
        return f"https://{self.host}{path}"

    def login(self, password: str) -> str:
        """Schritt 1: Session holen. PW geht NUR hier rein, wird NIE geloggt."""
        if not password:
            raise OrchestrationError("Aufkleber-Passwort fehlt.")
        resp = self.http(
            method="POST",
            url=self._url(LOGIN_PATH),
            headers={"Content-Type": "application/json"},
            json_body={"password": password},
        )
        if resp.status == 401:
            raise OrchestrationError(
                "Login am Gateway abgelehnt (401) — Aufkleber-Passwort falsch?"
            )
        if resp.status != 200:
            raise OrchestrationError(
                f"Login am Gateway fehlgeschlagen (HTTP {resp.status})."
            )
        try:
            session = resp.json().get("session")
        except Exception as exc:  # noqa: BLE001
            raise OrchestrationError("Login-Antwort des Gateways unlesbar.") from exc
        if not session:
            raise OrchestrationError("Gateway lieferte keine Session.")
        self.session = session
        return session

    def _auth_headers(self) -> Dict[str, str]:
        if not self.session:
            raise OrchestrationError("Keine Session — login() zuerst aufrufen.")
        # Token geht als X-Session-Header (kein Cookie).
        return {"Content-Type": "application/json", "X-Session": self.session}

    def install_public_key(self, public_key: str) -> None:
        """Schritt 2: POST /ssh_access_credentials mit Add-on-PUBLIC-Key.

        Methode ist POST, NICHT PUT (live bewiesen: PUT=405, POST=204).
        `/ssh_access_enable` bleibt PUT (live 204).
        """
        # Prefix-Check statt Substring — ein gueltiger
        # OpenSSH-Public-Key beginnt mit "ssh-" (z. B. ssh-ed25519 / ssh-rsa).
        # `startswith` ist strenger/robuster als `"ssh-" in key` (fuehrender
        # Muell vor dem Key wird so abgewiesen).
        if not public_key or not public_key.strip().startswith("ssh-"):
            raise OrchestrationError("Add-on-Public-Key fehlt/ungueltig.")
        body = {field_name: public_key for field_name in SSH_PUBKEY_FIELD_CANDIDATES}
        resp = self.http(
            method="POST",
            url=self._url(SSH_CREDENTIALS_PATH),
            headers=self._auth_headers(),
            json_body=body,
        )
        if resp.status not in (200, 204):
            raise OrchestrationError(
                f"Public-Key-Installation fehlgeschlagen (HTTP {resp.status})."
            )

    def set_ssh_enabled(self, enable: bool) -> None:
        """Schritt 3 / Schritt 5: PUT /ssh_access_enable {"enable": bool}."""
        resp = self.http(
            method="PUT",
            url=self._url(SSH_ENABLE_PATH),
            headers=self._auth_headers(),
            json_body={"enable": bool(enable)},
        )
        if resp.status not in (200, 204):
            raise OrchestrationError(
                f"SSH-{'Freigabe' if enable else 'Sperre'} fehlgeschlagen "
                f"(HTTP {resp.status})."
            )


@dataclass
class ReleaseArtifact:
    path: str
    sha256: str
    signature_path: Optional[str] = None
    # True NUR wenn eine kryptographische Signatur tatsaechlich geprueft wurde
    # (optionaler Folge-Schritt). False = nicht geprueft (Hash-Gate trug).
    signature_verified: bool = False


def compute_sha256(read_bytes: Callable[[str], bytes], path: str) -> str:
    """SHA-256 ueber den Artefakt-Inhalt (read_bytes injizierbar)."""
    return hashlib.sha256(read_bytes(path)).hexdigest()


def verify_build_hash(actual_sha256: str, expected_sha256: str) -> None:
    """Build-Hash-Abgleich (Footer == Release-Hash)."""
    if not expected_sha256:
        raise OrchestrationError("Kein erwarteter Build-Hash angegeben.")
    if actual_sha256.lower() != expected_sha256.lower():
        raise OrchestrationError(
            "Build-Hash des Release-Artefakts stimmt NICHT — Deploy abgebrochen."
        )


# ── Hash-Pinning-Quelle (bridge-release.lock) ────────────────────────────────
@dataclass
class ReleaseLock:
    repo: str
    tag: str
    sha256: str


def load_release_lock(
    read_text: Callable[[str], str],
    path: str = RELEASE_LOCK_PATH,
) -> ReleaseLock:
    """Liest + validiert bridge-release.lock (JSON {repo, tag, sha256}).

    `read_text` ist injizierbar (in Tests gemockt; produktiv = Datei lesen).
    Fehlt die Datei / ist sie kein valides JSON / fehlt ein Pflichtfeld -> harter
    OrchestrationError (fail-closed: ohne valide Pin-Quelle kein Deploy).
    """
    try:
        raw = read_text(path)
    except Exception as exc:  # noqa: BLE001
        raise OrchestrationError(
            "bridge-release.lock nicht lesbar — kein Hash-Pin, Deploy abgebrochen."
        ) from exc
    try:
        data = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        raise OrchestrationError(
            "bridge-release.lock ist kein valides JSON — Deploy abgebrochen."
        ) from exc
    if not isinstance(data, dict):
        raise OrchestrationError("bridge-release.lock hat kein JSON-Objekt.")
    repo = str(data.get("repo", "")).strip()
    tag = str(data.get("tag", "")).strip()
    sha256 = str(data.get("sha256", "")).strip()
    if not repo or not tag or not sha256:
        raise OrchestrationError(
            "bridge-release.lock unvollstaendig (repo/tag/sha256) — Deploy abgebrochen."
        )
    return ReleaseLock(repo=repo, tag=tag, sha256=sha256)


def resolve_expected_sha256(lock: ReleaseLock, configured_tag: str) -> str:
    """Liefert den erwarteten SHA256 aus dem Lock — fail-closed.

    Regeln (KEIN stiller Skip):
      - lock.sha256 ist ein klar markierter Platzhalter -> fail-closed (das echte
        Release ist noch nicht gepinnt; Deploy bricht ab).
      - configured_tag != lock.tag -> klare Warnung + fail-closed (es liegt kein
        Pin fuer das angeforderte Release vor).
      - sonst: lock.sha256 als harten Pin zurueckgeben.
    """
    if PLACEHOLDER_SHA256_MARKER in lock.sha256:
        raise OrchestrationError(
            "bridge-release.lock enthaelt noch den PLATZHALTER-Hash — das echte "
            "Bridge-Release ist noch nicht gepinnt. Deploy abgebrochen (fail-closed). "
            "Maintainer: build-bridge-release.sh laufen lassen + den SHA256 im Lock setzen."
        )
    if (configured_tag or "").strip() != lock.tag:
        raise OrchestrationError(
            f"Konfigurierter release_tag '{configured_tag}' != gepinntem Lock-Tag "
            f"'{lock.tag}' — fuer dieses Release liegt KEIN Hash-Pin vor. Deploy "
            "abgebrochen (fail-closed, kein stiller Skip). Entweder release_tag auf "
            f"'{lock.tag}' setzen oder das Lock fuer den gewuenschten Tag aktualisieren."
        )
    return lock.sha256


# Signatur-Verifier-Typ: (artifact_path, signature_path, public_key_path) -> bool.
# KEIN openssl-CLI mehr. Der Verifier ist OPTIONAL und wird injiziert (z. B.
# eine pure-python py3-cryptography-Implementierung), wenn ueberhaupt vorhanden.
SignatureVerifier = Callable[[str, str, str], bool]


def verify_signature_optional(
    sig_verify: Optional[SignatureVerifier],
    artifact_path: str,
    signature_path: str,
    public_key_path: str,
) -> bool:
    """OPTIONALER Signatur-Folge-Schritt — ersetzt NIE das Hash-Gate.

    Vertrag:
      - Ist KEIN Verifier injiziert (sig_verify is None), wird die Signatur NICHT
        geprueft: das SHA256-Hash-Pinning + HTTPS vom eigenen Release bleibt das
        (bereits bestandene) harte Gate. Rueckgabe False = "nicht geprueft".
      - Ist ein Verifier da, aber keine .sig vorhanden -> ebenfalls uebersprungen
        (kein harter Abbruch: das Hash-Gate hat bereits bestanden).
      - Ist ein Verifier da UND eine .sig vorhanden, wird hart geprueft:
        ungueltige Signatur -> OrchestrationError (Abbruch).

    Rueckgabe: True wenn eine Signatur tatsaechlich erfolgreich geprueft wurde,
    sonst False (= uebersprungen, NICHT als Fehler zu werten).
    """
    if sig_verify is None:
        return False
    if not signature_path:
        return False
    ok = sig_verify(artifact_path, signature_path, public_key_path)
    if not ok:
        raise OrchestrationError(
            "Signatur des Release-Artefakts ungueltig — Deploy abgebrochen."
        )
    return True


def fetch_and_verify_release(
    downloader: Callable[[str, str, str], ReleaseArtifact],
    read_bytes: Callable[[str], bytes],
    *,
    repo: str,
    tag: str,
    expected_sha256: str,
    sig_verify: Optional[SignatureVerifier] = None,
    signing_public_key_path: str = "",
) -> ReleaseArtifact:
    """Zieht das Release (§2.2 b) und prueft die Integritaet VOR dem Deploy.

    Reihenfolge bindend (Rework):
      download -> sha256 -> HARTES Hash-Pinning-Gate -> OPTIONALE Signatur.
    Das Hash-Gate ist das primaere, harte Kriterium; der Signatur-Schritt ist
    optional und ersetzt es NICHT. Erst nach bestandenem Hash-Gate darf
    deploy_via_ssh() laufen.
    """
    if not repo or "/" not in repo:
        raise OrchestrationError("GitHub-Repo (owner/name) fehlt/ungueltig.")
    artifact = downloader(repo, tag, "/data/release")
    actual = compute_sha256(read_bytes, artifact.path)
    # PRIMAERES, hartes Gate: SHA256-Hash-Pinning (Abbruch bei Mismatch).
    verify_build_hash(actual, expected_sha256)
    # OPTIONALER Folge-Schritt: kryptographische Signatur (ersetzt das Gate nicht).
    artifact.signature_verified = verify_signature_optional(
        sig_verify,
        artifact.path,
        artifact.signature_path or "",
        signing_public_key_path,
    )
    # Verifizierten Hash zurueckschreiben (Audit).
    artifact.sha256 = actual
    return artifact


# ── Release-Bundle entpacken ──────────────────────────────────────────────────
@dataclass
class UnpackedBundle:
    """Pfade der entpackten Bundle-Member (container-lokal, z. B. /data/release/)."""

    binary_path: str
    libs_tgz_path: str
    version: str = ""
    # Pfad zum entpackten web-ui/-Unterverzeichnis.
    web_ui_dir: str = ""
    # Pfad zum entpackten mqtt-publisher/-Unterverzeichnis.
    # Leer wenn Bundle kein MQTT-Publisher-Verzeichnis enthaelt (opt-in via enable_mqtt).
    mqtt_publisher_dir: str = ""


def unpack_bundle(
    artifact_path: str,
    dest_dir: str,
    *,
    extractor: Optional[Callable[[str, str], None]] = None,
    read_text: Optional[Callable[[str], str]] = None,
) -> UnpackedBundle:
    """Entpackt das Release-Bundle container-lokal nach dest_dir.

    Das Bundle gardena-bridge-<tag>.tar.gz enthaelt:
      chip-bridge-app.stripped + matter_libs.tar.gz + VERSION
      + web-ui/<Laufzeit-Dateien> (gardena-toggle, matter.html, qrcode.min.js,
        systemd-Units, gardena-matter-restore.sh, update-matter-status.sh).

    `extractor` (mockbar) fuehrt das eigentliche Entpacken aus; default = tarfile
    (data_filter, kein Pfad-Ausbruch). `read_text` liest die VERSION (mockbar).
    Nach dem Entpacken MUESSEN Binary + Libs-Tarball + die drei Kern-web-ui-
    Dateien vorhanden sein, sonst OrchestrationError (harter Abbruch).
    """
    if extractor is None:
        extractor = _default_tar_extract
    extractor(artifact_path, dest_dir)

    binary_path = os.path.join(dest_dir, BUNDLE_BINARY_NAME)
    libs_tgz_path = os.path.join(dest_dir, BUNDLE_LIBS_NAME)
    version_path = os.path.join(dest_dir, BUNDLE_VERSION_NAME)
    web_ui_dir = os.path.join(dest_dir, BUNDLE_WEB_UI_DIR)
    mqtt_publisher_dir = os.path.join(dest_dir, BUNDLE_MQTT_PUBLISHER_DIR)

    missing = [
        name
        for name, p in ((BUNDLE_BINARY_NAME, binary_path), (BUNDLE_LIBS_NAME, libs_tgz_path))
        if not os.path.isfile(p)
    ]
    if missing:
        raise OrchestrationError(
            "Release-Bundle unvollstaendig -- fehlende Member: "
            + ", ".join(missing)
            + ". Deploy abgebrochen."
        )

    # web-ui/-Unterverzeichnis pruefen (harter Abbruch bei fehlenden Dateien).
    missing_web = [
        f
        for f in BUNDLE_WEB_UI_REQUIRED
        if not os.path.isfile(os.path.join(web_ui_dir, f))
    ]
    if missing_web:
        raise OrchestrationError(
            "Release-Bundle: web-ui/-Member fehlen: "
            + ", ".join(missing_web)
            + ". Deploy abgebrochen."
        )

    version = ""
    reader = read_text or _default_read_text
    try:
        version = reader(version_path).strip()
    except Exception:  # noqa: BLE001
        version = ""  # VERSION ist informativ, kein harter Abbruch.

    # mqtt-publisher/-Verzeichnis OPTIONAL (nur wenn Bundle es enthaelt, opt-in via enable_mqtt).
    # Existenz wird hier nicht erzwungen — Pruefen erst in deploy_mqtt_publisher_if_enabled().
    # Kein harter Abbruch hier: MQTT ist additiv; fehlendes Verzeichnis wird erst beim
    # tatsaechlichen MQTT-Deploy bemerkt (dort fail-closed wenn enable_mqtt=true).
    resolved_mqtt_dir = mqtt_publisher_dir if os.path.isdir(mqtt_publisher_dir) else ""

    return UnpackedBundle(
        binary_path=binary_path,
        libs_tgz_path=libs_tgz_path,
        version=version,
        web_ui_dir=web_ui_dir,
        mqtt_publisher_dir=resolved_mqtt_dir,
    )


def _default_tar_extract(archive_path: str, dest_dir: str) -> None:
    """Entpackt einen .tar.gz sicher nach dest_dir (kein Pfad-Ausbruch)."""
    os.makedirs(dest_dir, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tar:
        # Python 3.12+: data_filter wehrt Pfad-Traversal/absolute Pfade ab.
        try:
            tar.extractall(dest_dir, filter="data")  # type: ignore[call-arg]
        except TypeError:  # pragma: no cover - aeltere Python ohne filter-Kwarg
            tar.extractall(dest_dir)  # noqa: S202


def _default_read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ── Container-lokaler Deploy der drei Install-Skripte ────────────────────────
# Skripte 2+3 brauchen WEB_UI_SRC (web-ui-Payload aus dem Bundle); Skript 1
# (install_bridge.sh) bekommt WEB_UI_SRC NICHT -- es hat keine web-ui-Abhaengigkeit.
_SCRIPTS_NEEDING_WEB_UI_SRC = frozenset({
    "install_web_ui.sh",
    "install_restore.sh",
})


def build_install_script_command(
    script: str,
    *,
    scripts_dir: str,
    gateway_host: str,
    private_key_path: str,
    binary_path: str,
    libs_tgz_path: str,
    web_ui_dir: str = "",
) -> List[str]:
    """Baut die Kommandozeile, die EIN Install-Skript CONTAINER-LOKAL ausfuehrt.

    Architektur: die Install-Skripte laufen IM Add-on-Container (der hat
    ssh/scp zum Gateway), NICHT auf dem Gateway. Sie scp'en selbst zum Gateway
    (bestehende Logik in matter/install_*.sh). Wir reichen ihnen das Ziel + die
    Bundle-Pfade als ENV durch:
      GATEWAY_IP=gateway_host  GARDENA_SSH_KEY=<Add-on-Private-Key>
      BINARY_PATH=<entpackte Binary>  LIBS_TGZ=<entpackte Libs>

    install_web_ui.sh + install_restore.sh erhalten zusaetzlich
      WEB_UI_SRC=<web_ui_dir>  (entpacktes web-ui/-Unterverzeichnis im Bundle)
    install_bridge.sh erhaelt WEB_UI_SRC NICHT (hat keine web-ui-Abhaengigkeit).
    """
    env = [
        "env",
        "HOME=/root",  # nounset-sicher auch ohne HOME im Container-Env
        f"GATEWAY_IP={gateway_host}",
        f"GARDENA_SSH_KEY={private_key_path}",
        f"BINARY_PATH={binary_path}",
        f"LIBS_TGZ={libs_tgz_path}",
    ]
    # WEB_UI_SRC nur fuer Skripte 2+3, NICHT fuer install_bridge.sh.
    if script in _SCRIPTS_NEEDING_WEB_UI_SRC and web_ui_dir:
        env.append(f"WEB_UI_SRC={web_ui_dir}")
    env += ["bash", os.path.join(scripts_dir, script)]
    return env


def deploy_via_ssh(
    runner: Callable[[Sequence[str]], int],
    *,
    host: str,
    private_key_path: str,
    binary_path: str,
    libs_tgz_path: str,
    web_ui_dir: str = "",
    scripts: Sequence[str] = INSTALL_SCRIPTS,
    scripts_dir: str = INSTALL_SCRIPTS_DIR,
) -> List[str]:
    """Idempotenter Deploy — fuehrt die Install-Skripte CONTAINER-LOKAL aus.

    `runner` fuehrt eine Kommandozeile aus -> Exit-Code (in Tests gemockt). Anders
    als das alte Modell (push+run AUF dem Gateway) laufen die Skripte hier IM
    Container und scp'en SELBST zum Gateway (scp-Ziel = `host` = gateway_host).
    Gibt die Liste der ausgefuehrten Skripte (Reihenfolge bindend: Bridge -> Web-UI
    -> Restore) zurueck.

    Die Install-Skripte sind on-device-idempotent (siehe matter/install_*.sh):
    KVS bleibt, systemctl enable wiederholbar, Firewall -C vor -I.
    """
    executed: List[str] = []
    for script in scripts:
        cmd = build_install_script_command(
            script,
            scripts_dir=scripts_dir,
            gateway_host=host,
            private_key_path=private_key_path,
            binary_path=binary_path,
            libs_tgz_path=libs_tgz_path,
            web_ui_dir=web_ui_dir,
        )
        rc = runner(cmd)
        if rc != 0:
            raise OrchestrationError(
                f"Deploy-Skript {script} fehlgeschlagen (Exit {rc})."
            )
        executed.append(script)
    return executed


# ── MQTT-Publisher: additiver Deploy ─────────────────────────────────────────

@dataclass
class MqttConfig:
    """MQTT-Konfiguration aus Add-on-Optionen.

    enable: wenn False -> kein Deploy, kein Start des Publishers.
    broker_host: FQDN/IP des MQTT-Brokers. Leer = HA-Host (Gateway-IP als Proxy).
    broker_user / broker_password: Zugangsdaten. Passwort NIEMALS loggen (R12).
    topic_prefix: Topic-Praefix (Standard "gardena").
    ha_prefix: HA-Discovery-Prefix (Standard "homeassistant").
    """

    enable: bool = False
    broker_host: str = ""
    broker_user: str = ""
    broker_password: str = ""   # Secret — NIE loggen, NIE in Fehlermeldungen (R12)
    topic_prefix: str = "gardena"
    ha_prefix: str = "homeassistant"


def load_mqtt_config_from_env() -> MqttConfig:
    """Liest MQTT-Konfiguration aus Umgebungsvariablen (von run.sh gesetzt).

    Broker-Passwort wird NIE geloggt (R12). Fehlende Optionen -> sicherer Default.
    """
    enable_str = os.environ.get("GARDENA_ENABLE_MQTT", "false").strip().lower()
    return MqttConfig(
        enable=(enable_str in ("true", "1", "yes")),
        broker_host=os.environ.get("GARDENA_MQTT_BROKER_HOST", "").strip(),
        broker_user=os.environ.get("GARDENA_MQTT_BROKER_USER", "").strip(),
        broker_password=os.environ.get("GARDENA_MQTT_BROKER_PASSWORD", ""),
        topic_prefix=os.environ.get("GARDENA_MQTT_TOPIC_PREFIX", "gardena").strip() or "gardena",
        ha_prefix=os.environ.get("GARDENA_MQTT_HA_PREFIX", "homeassistant").strip() or "homeassistant",
    )


def deploy_mqtt_publisher_if_enabled(
    runner: Callable[[Sequence[str]], int],
    *,
    mqtt_config: MqttConfig,
    gateway_host: str,
    private_key_path: str,
    mqtt_publisher_dir: str,
    scripts_dir: str = INSTALL_SCRIPTS_DIR,
) -> bool:
    """Deployt den MQTT-Publisher ADDITIV — nur wenn enable_mqtt=true.

    Wenn enable=False: kein Deploy, kein Fehler. Gibt False zurueck (nicht deployt).
    Wenn enable=True und mqtt_publisher_dir leer/fehlt: harter Abbruch (fail-closed).
    Wenn enable=True: prueft Pflicht-Member, schreibt mqtt.env, ruft install_mqtt_publisher.sh.

    Additiv-Garantie:
      - Matter/Bridge/KVS/cloudadapter werden NICHT beruehrt.
      - Hash-Gate (orchestrate-Kern) bleibt unveraendert.
      - Publisher-Deploy schlaegt fail-closed falls Bundle-Member fehlen.

    Passwort-Hygiene: broker_password wird NUR in mqtt.env geschrieben (via SSH),
    NIEMALS in Logs oder Fehlermeldungen. Die SSH-Verbindung benutzt denselben
    Add-on-Private-Key wie der Matter-Deploy.

    EN: Deploys the MQTT publisher additively — only when enable_mqtt=true.
        Broker password is never logged; written only to /etc/gardena-matter/mqtt.env.
    DE: Deployt den MQTT-Publisher additiv — nur wenn enable_mqtt=true.
        Broker-Passwort wird nie geloggt; nur in /etc/gardena-matter/mqtt.env geschrieben.
    """
    if not mqtt_config.enable:
        return False  # nicht aktiviert — kein Deploy

    if not mqtt_publisher_dir or not os.path.isdir(mqtt_publisher_dir):
        raise OrchestrationError(
            "enable_mqtt=true, aber das mqtt-publisher/-Verzeichnis fehlt im Release-Bundle. "
            "Bitte ein Bundle verwenden das den MQTT-Publisher enthaelt. "
            "Deploy abgebrochen (fail-closed)."
        )

    # Pflicht-Member pruefen
    missing = [
        f for f in BUNDLE_MQTT_PUBLISHER_REQUIRED
        if not os.path.isfile(os.path.join(mqtt_publisher_dir, f))
    ]
    if missing:
        raise OrchestrationError(
            "Release-Bundle: mqtt-publisher/-Member fehlen: "
            + ", ".join(missing)
            + ". MQTT-Deploy abgebrochen (fail-closed)."
        )

    # install_mqtt_publisher.sh via SSH aufrufen.
    # MQTT_BROKER_PASSWORD wird als ENV-Variable durchgereicht — NIE als Shell-Argument
    # (Shell-History-Schutz). Das Skript schreibt mqtt.env auf dem Gateway.
    script_path = os.path.join(scripts_dir, INSTALL_MQTT_SCRIPT)
    if not os.path.isfile(script_path):
        # Fallback: Skript aus dem Bundle-Verzeichnis
        script_path = os.path.join(mqtt_publisher_dir, INSTALL_MQTT_SCRIPT)

    broker_host = mqtt_config.broker_host or gateway_host  # HA-Host als Default

    cmd = [
        "env",
        "HOME=/root",
        f"GATEWAY_IP={gateway_host}",
        f"GARDENA_SSH_KEY={private_key_path}",
        f"MQTT_BINARY={os.path.join(mqtt_publisher_dir, 'gardena-mqtt-publisher')}",
        f"MQTT_SERVICE={os.path.join(mqtt_publisher_dir, 'gardena-mqtt-publisher.service')}",
        f"MQTT_BROKER_HOST={broker_host}",
        f"MQTT_BROKER_USER={mqtt_config.broker_user}",
        f"MQTT_BROKER_PASS={mqtt_config.broker_password}",  # Secret via ENV, nie als Arg
        f"MQTT_TOPIC_PREFIX={mqtt_config.topic_prefix}",
        f"MQTT_HA_PREFIX={mqtt_config.ha_prefix}",
        "bash",
        script_path,
    ]
    rc = runner(cmd)
    if rc != 0:
        raise OrchestrationError(
            f"MQTT-Publisher-Install-Skript fehlgeschlagen (Exit {rc}). "
            "Broker-Konfiguration pruefen (Host/Port/Credentials)."
        )
    return True


# ── Voller Orchestrierungs-Flow (Reihenfolge bindend) ────────────────────────
@dataclass
class DeployPlan:
    gateway_host: str
    private_key_path: str
    public_key_path: str
    repo: str
    tag: str
    expected_sha256: str
    # Optional: nur gesetzt, wenn ein echter Signatur-Verifier hinterlegt ist.
    signing_public_key_path: str = ""
    disable_ssh_after: bool = False
    scripts: Sequence[str] = field(default_factory=lambda: list(INSTALL_SCRIPTS))
    # MQTT-Konfiguration (additiv, optional).
    # None = MQTT-Deploy deaktiviert (kein enable_mqtt in Optionen).
    mqtt_config: Optional[MqttConfig] = None


@dataclass
class DeployResult:
    steps: List[str] = field(default_factory=list)
    executed_scripts: List[str] = field(default_factory=list)
    artifact_sha256: str = ""
    # ob im Release-Verify-Schritt eine kryptographische Signatur geprueft
    # wurde (False = nur Hash-Gate, der vertretbare Hobby-Add-on-Default).
    signature_verified: bool = False
    # Version aus dem entpackten Release-Bundle (informativ).
    bundle_version: str = ""
    # ob der MQTT-Publisher additiv deployt wurde.
    mqtt_deployed: bool = False


def run_full_deploy(
    plan: DeployPlan,
    *,
    gateway: GatewayClient,
    device_id: str,
    read_public_key: Callable[[str], str],
    downloader: Callable[[str, str, str], ReleaseArtifact],
    read_bytes: Callable[[str], bytes],
    ssh_runner: Callable[[Sequence[str]], int],
    sig_verify: Optional[SignatureVerifier] = None,
    unpack_dir: str = "/data/release",
    extractor: Optional[Callable[[str, str], None]] = None,
    read_text: Optional[Callable[[str], str]] = None,
) -> DeployResult:
    """Fuehrt den kompletten Flow in der vorgegebenen Reihenfolge aus.

    login -> install_credentials -> enable -> (release verify) -> deploy
          -> optional disable.

    WICHTIG: Das Release wird VOR der eigentlichen Deploy-Ausfuehrung gezogen +
    verifiziert; aber NACH der SSH-Freigabe ist egal — die Reihenfolge
    login/credentials/enable/deploy ist bindend (wird per Unit-Test gesichert).

    Der gateway_host wird IMMER explizit aus der Add-on-Config
    durchgereicht — KEIN Hardcode-Fallback. Fehlt er, bricht der Flow hart ab,
    statt still auf irgendeine Default-IP zu zielen.

    Integritaet = SHA256-Hash-Pinning (hartes Gate). Eine echte
    Signatur ist optional (sig_verify), ersetzt das Hash-Gate NICHT.

    Es gibt nur EIN Credential — `device_id`. Das Login-Passwort
    wird daraus abgeleitet (`device_id[:8]`). Fehlt `device_id` (ODER `gateway_host`),
    bricht der Flow HART ab, bevor irgendein Gateway-Aufruf laeuft.
    """
    if not plan.gateway_host:
        raise OrchestrationError(
            "gateway_host fehlt — bitte in den Add-on-Optionen setzen "
            "(kein Default/Hardcode im Add-on-Pfad)."
        )

    # Login-Passwort = device_id[:8]. Leere device_id -> harter Abbruch
    # (derive_login_password wirft), bevor ein Gateway-Aufruf erfolgt.
    login_password = derive_login_password(device_id)

    result = DeployResult()

    gateway.login(login_password)
    result.steps.append("login")

    public_key = read_public_key(plan.public_key_path)
    gateway.install_public_key(public_key)
    result.steps.append("install_credentials")

    gateway.set_ssh_enabled(True)
    result.steps.append("enable_ssh")

    artifact = fetch_and_verify_release(
        downloader,
        read_bytes,
        repo=plan.repo,
        tag=plan.tag,
        expected_sha256=plan.expected_sha256,
        sig_verify=sig_verify,
        signing_public_key_path=plan.signing_public_key_path,
    )
    result.steps.append("release_verified")
    result.artifact_sha256 = artifact.sha256
    result.signature_verified = artifact.signature_verified

    # Bundle ERST NACH bestandenem Hash-Gate entpacken (kein Entpacken
    # un-verifizierter Bytes), dann die entpackten Binary/Libs an den Deploy geben.
    bundle = unpack_bundle(
        artifact.path,
        unpack_dir,
        extractor=extractor,
        read_text=read_text,
    )
    result.bundle_version = bundle.version
    result.steps.append("bundle_unpacked")

    result.executed_scripts = deploy_via_ssh(
        ssh_runner,
        host=plan.gateway_host,
        private_key_path=plan.private_key_path,
        binary_path=bundle.binary_path,
        libs_tgz_path=bundle.libs_tgz_path,
        web_ui_dir=bundle.web_ui_dir,
        scripts=plan.scripts,
    )
    result.steps.append("deploy")

    # MQTT-Publisher additiv deployen (nach dem Matter-Deploy, opt-in).
    # Additiv-Garantie: dieser Block beruehrt NICHT Matter/Bridge/KVS/cloudadapter.
    # Broker-Passwort wird via ENV an das Install-Skript weitergegeben (nie als Arg).
    if plan.mqtt_config is not None:
        result.mqtt_deployed = deploy_mqtt_publisher_if_enabled(
            ssh_runner,
            mqtt_config=plan.mqtt_config,
            gateway_host=plan.gateway_host,
            private_key_path=plan.private_key_path,
            mqtt_publisher_dir=bundle.mqtt_publisher_dir,
        )
        if result.mqtt_deployed:
            result.steps.append("mqtt_deploy")

    if plan.disable_ssh_after:
        gateway.set_ssh_enabled(False)
        result.steps.append("disable_ssh")

    return result


# ── REALE injizierbare Implementierungen ──────────────────────────────────────
# Diese Funktionen sind die produktiven Implementierungen der bislang nur als
# Callable-Typ modellierten Injektions-Punkte (runner/http/downloader). In den
# Unit-Tests werden sie weiterhin durch Fakes ERSETZT (kein echter Netz-/
# Gateway-/GitHub-Zugriff im Test). Erst der echte Lauf (mit User) ruft sie
# tatsaechlich auf.

# GitHub-API-Basis. Asset-Name-Schema = gardena-bridge-<tag>.tar.gz.
GITHUB_API_BASE = "https://api.github.com"
RELEASE_ASSET_NAME_TMPL = "gardena-bridge-{tag}.tar.gz"
# Default-Timeout fuer HTTP/Subprocess (Sekunden) — grosszuegig fuer scp eines
# Release-Bundles ueber LAN, aber nicht unendlich (kein haengender Deploy).
HTTP_TIMEOUT_S = 60
DEPLOY_RUN_TIMEOUT_S = 1800


def real_http_client(
    method: str,
    url: str,
    headers: Dict[str, str],
    json_body: Optional[dict] = None,
    *,
    timeout: int = HTTP_TIMEOUT_S,
) -> HttpResponse:
    """REALER HTTPS-Client zum Gateway (/login + /ssh_access_*).

    Pure-stdlib (urllib), keine Zusatz-Abhaengigkeit. Das Gateway nutzt ein
    self-signed Cert auf :443 -> wir verifizieren das Cert NICHT (LAN-Geraet, der
    Nutzer spricht ohnehin sein eigenes Gateway an; Integritaet der DEPLOY-Bytes
    laeuft separat ueber das harte SHA256-Hash-Gate). Secrets (Passwort) stecken
    NUR im json_body und werden hier NIE geloggt.
    """
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    # Gateway = self-signed auf dem LAN -> Cert-Verifikation aus (s. Docstring).
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return HttpResponse(status=resp.status, body=body)
    except urllib.error.HTTPError as exc:  # noqa: PERF203
        # 401/405 etc. sind erwartbare Status -> als HttpResponse durchreichen,
        # damit GatewayClient klare Meldungen bauen kann (KEIN Secret im Text).
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            body = ""
        return HttpResponse(status=exc.code, body=body)
    except Exception as exc:  # noqa: BLE001
        # Netz-/TLS-Fehler -> klare, PW-freie Meldung (url enthaelt KEIN Secret).
        raise OrchestrationError(
            f"HTTPS-Aufruf zum Gateway fehlgeschlagen ({method} {url})."
        ) from exc


def real_subprocess_runner(
    cmd: Sequence[str],
    *,
    timeout: int = DEPLOY_RUN_TIMEOUT_S,
) -> int:
    """REALER Runner fuer die container-lokalen Install-Skripte.

    Fuehrt EINE Kommandozeile (env ... bash <script>) aus und gibt den Exit-Code
    zurueck. Das Kommando enthaelt KEIN Secret (nur GATEWAY_IP/Key-PFAD/Bundle-
    Pfade) -> es darf geloggt werden; wir loggen es bewusst NICHT mit Wert hier,
    um Pfad-Rauschen zu vermeiden. ssh/scp innerhalb der Skripte nutzen den
    Add-on-PRIVATE-Key (Pfad), nicht das Passwort.
    """
    try:
        proc = subprocess.run(  # noqa: S603
            list(cmd),
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise OrchestrationError(
            "Deploy-Skript hat das Zeitlimit ueberschritten — abgebrochen."
        ) from exc
    except FileNotFoundError as exc:
        raise OrchestrationError(
            "Deploy-Kommando nicht ausfuehrbar (env/bash fehlt im Container?)."
        ) from exc
    return proc.returncode


def github_release_downloader(
    repo: str,
    tag: str,
    dest_dir: str,
    *,
    token: str = "",
    opener: Optional[Callable[..., object]] = None,
    timeout: int = HTTP_TIMEOUT_S,
) -> ReleaseArtifact:
    """REALER GitHub-Release-Downloader — holt das Bundle-Asset.

    Ablauf (GitHub-REST):
      1. GET /repos/<repo>/releases/tags/<tag>  -> Release-JSON mit assets[].
      2. Asset gardena-bridge-<tag>.tar.gz heraussuchen -> dessen `url`
         (api.github.com/.../assets/<id>).
      3. GET dieser Asset-URL mit `Accept: application/octet-stream` -> Bytes
         -> nach dest_dir/<asset-name> schreiben.

    Ist `token` gesetzt -> `Authorization: Bearer <token>` (fuer ein PRIVATES Repo);
    sonst unauth (public). Der Token wird NIE geloggt und NIE in eine
    Fehlermeldung gespiegelt. `opener` ist injizierbar (Tests mocken ihn; produktiv = urllib).
    """
    if not repo or "/" not in repo:
        raise OrchestrationError("GitHub-Repo (owner/name) fehlt/ungueltig.")
    _open = opener or _real_url_open
    asset_name = RELEASE_ASSET_NAME_TMPL.format(tag=tag)

    base_headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "gardena-matter-bridge-addon",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        base_headers["Authorization"] = f"Bearer {token}"

    # 1. Release-Metadaten zum Tag holen.
    rel_url = f"{GITHUB_API_BASE}/repos/{repo}/releases/tags/{tag}"
    try:
        status, body = _open("GET", rel_url, base_headers, timeout)
    except OrchestrationError:
        raise
    except Exception as exc:  # noqa: BLE001
        # Token NIE spiegeln -> generische Meldung ohne Header-Inhalt.
        raise OrchestrationError(
            f"GitHub-Release-Metadaten nicht abrufbar (repo {repo}, tag {tag})."
        ) from exc
    if status == 404:
        raise OrchestrationError(
            f"GitHub-Release nicht gefunden (repo {repo}, tag {tag}). "
            "Privates Repo? Dann github_token in den Optionen setzen."
        )
    if status == 401:
        raise OrchestrationError(
            "GitHub lehnte die Authentifizierung ab (401) — github_token pruefen."
        )
    if status != 200:
        raise OrchestrationError(
            f"GitHub-Release-Abruf fehlgeschlagen (HTTP {status}, tag {tag})."
        )
    try:
        release = json.loads(body)
    except Exception as exc:  # noqa: BLE001
        raise OrchestrationError("GitHub-Release-Antwort unlesbar.") from exc

    # 2. Asset heraussuchen.
    asset_url = ""
    for asset in release.get("assets", []) or []:
        if asset.get("name") == asset_name:
            asset_url = asset.get("url", "")
            break
    if not asset_url:
        raise OrchestrationError(
            f"Release-Asset '{asset_name}' fehlt im Release (tag {tag})."
        )

    # 3. Asset-Bytes als octet-stream laden.
    asset_headers = dict(base_headers)
    asset_headers["Accept"] = "application/octet-stream"
    try:
        a_status, a_bytes = _open("GET", asset_url, asset_headers, timeout, True)
    except OrchestrationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise OrchestrationError(
            f"Release-Asset '{asset_name}' nicht herunterladbar."
        ) from exc
    if a_status != 200:
        raise OrchestrationError(
            f"Release-Asset-Download fehlgeschlagen (HTTP {a_status})."
        )

    os.makedirs(dest_dir, exist_ok=True)
    out_path = os.path.join(dest_dir, asset_name)
    with open(out_path, "wb") as fh:
        fh.write(a_bytes)
    return ReleaseArtifact(path=out_path, sha256="")


def _real_url_open(method, url, headers, timeout, binary=False):
    """Pure-stdlib urllib-Open -> (status, body). Tokens stecken in `headers`.

    Rueckgabe: (status:int, body:str|bytes). Bei binary=True -> rohe Bytes.
    HTTPError wird als (status, body) durchgereicht (z. B. 404/401), damit der
    Downloader klare, token-freie Meldungen bauen kann.
    """
    req = urllib.request.Request(url=url, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            return resp.status, (data if binary else data.decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        data = b""
        try:
            data = exc.read()
        except Exception:  # noqa: BLE001
            data = b""
        return exc.code, (data if binary else data.decode("utf-8", "replace"))


# ── Sicherheits-Helfer: nie das PW loggen ────────────────────────────────────
def redact(text: str, secret: str) -> str:
    """Ersetzt ein Geheimnis (Aufkleber-PW) durch *** in beliebigem Text."""
    if not secret:
        return text
    return text.replace(secret, "***")


def addon_public_key_present(read_public_key: Callable[[str], str], path: str) -> bool:
    try:
        pk = read_public_key(path)
    except Exception:  # noqa: BLE001
        return False
    return bool(pk) and pk.strip().startswith("ssh-")
