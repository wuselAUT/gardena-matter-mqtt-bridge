#!/usr/bin/env bash
#
# Schnuert EIN Release-Artefakt `gardena-bridge-<tag>.tar.gz` aus den vorhandenen
# Build-Outputs und gibt dessen SHA256 aus. Das Bundle ist das, was der HA-Add-on-
# Container spaeter aus dem GitHub-Release zieht, gegen den gepinnten Hash prueft
# und entpackt (orchestrate.py: fetch_and_verify_release -> deploy_via_ssh).
#
# Bundle-Inhalt:
#   chip-bridge-app.stripped                die cross-gebaute Bridge-Binary (MIPS, fp_abi=0)
#   matter_libs.tar.gz                      die zugehoerigen Shared-Libs
#   VERSION                                 Klartext-Versions-/Build-Hash-Stempel
#   web-ui/gardena-toggle              MIPS-Binary (Toggle-Backend)
#   web-ui/matter.html                 Gateway-Onboarding-Seite
#   web-ui/qrcode.min.js              QR-Code-Bibliothek
#   web-ui/gardena-matter-toggle.service
#   web-ui/gardena-matter-toggle.socket
#   web-ui/gardena-matter-status.service
#   web-ui/gardena-matter-status.timer
#   web-ui/gardena-matter-restore.service
#   web-ui/gardena-matter-restore.path
#   web-ui/gardena-matter-restore.sh
#   web-ui/update-matter-status.sh
#   mqtt-publisher/gardena-mqtt-publisher.service
#   mqtt-publisher/install_mqtt_publisher.sh
#
# NICHT im Bundle (Dev-Artefakte, bleiben auf dem Build-Host):
#   build_toggle.sh, gardena-toggle.c, storm_test.sh
#   mqtt-publisher/build_mqtt_publisher.sh, mqtt-publisher/*.c, mqtt-publisher/*.h
#   mqtt-publisher/MQTT_CLIENT_SPIKE.md, mqtt-publisher/mqtt.env.example
#
# Single-Source fuer web-ui/: matter/web-ui/ im Repo (Repo-intern; Bundle-Zielname: web-ui/).
#
# Dieses Skript BAUT NICHTS NEU (kein Cross-Build) -- es verpackt nur vorhandene
# Outputs. Das echte Erzeugen/Hochladen des GitHub-Releases macht der Maintainer/
#
# Usage:
#   bash ha-addon/build-bridge-release.sh <tag> [BINARY] [LIBS_TGZ] [OUT_DIR] [WEB_UI_SRC] [MQTT_PUBLISHER_BINARY]
#   # oder env-gesteuert:
#   TAG=v1.1.0 BINARY=... LIBS_TGZ=... OUT_DIR=... bash ha-addon/build-bridge-release.sh
#
# Defaults (Build-Host):
#   BINARY               = ~/gardena-matter-build/out/mips-bridge/chip-bridge-app.stripped
#   LIBS_TGZ             = ~/gardena-matter-build/matter_libs.tar.gz
#   OUT_DIR              = ~/gardena-matter-build/release
#   WEB_UI_SRC           = <repo-root>/matter/web-ui  (Single-Source)
#   MQTT_PUBLISHER_BIN   = ~/gardena-matter-build/out/mips-mqtt/gardena-mqtt-publisher
#   VERSION              = git rev-parse --short HEAD (Fallback: <tag>)
#
# Idempotent: ein erneuter Lauf mit gleichen Inputs erzeugt dasselbe Bundle neu
# (deterministisches tar: feste Member-Reihenfolge, Mtime/Owner/Group genullt).
#
# Verifikation (statisch, ohne Gateway/HA): sh -n sauber; das erzeugte
# bridge-release.lock wird vom Maintainer mit dem ausgegebenen SHA256 befuellt

set -euo pipefail

BUILD_ROOT="${HOME:-/root}/gardena-matter-build"

TAG="${1:-${TAG:-}}"
BINARY="${2:-${BINARY:-${BUILD_ROOT}/out/mips-bridge/chip-bridge-app.stripped}}"
LIBS_TGZ="${3:-${LIBS_TGZ:-${BUILD_ROOT}/matter_libs.tar.gz}}"
OUT_DIR="${4:-${OUT_DIR:-${BUILD_ROOT}/release}}"
MQTT_PUBLISHER_BIN="${6:-${MQTT_PUBLISHER_BIN:-${BUILD_ROOT}/out/mips-mqtt/gardena-mqtt-publisher}}"

log() { echo "[build-release] $*"; }
err() { echo "[build-release][ERROR] $*" >&2; }

if [ -z "${TAG}" ]; then
    err "Kein <tag> angegeben (Arg 1 oder Env TAG). Bsp.: bash $0 v1.0.0"
    exit 2
fi

# -- Repo-Wurzel bestimmen (relativ zu diesem Skript: ha-addon/ -> ..) --------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# WEB_UI_SRC: Arg 5, Env WEB_UI_SRC, oder Single-Source matter/web-ui/
WEB_UI_SRC="${5:-${WEB_UI_SRC:-${REPO_ROOT}/matter/web-ui}}"
MQTT_PUBLISHER_SRC="${MQTT_PUBLISHER_SRC:-${REPO_ROOT}/mqtt-publisher}"

# -- Inputs pruefen ------------------------------------------------------------
if [ ! -f "${BINARY}" ]; then
    err "Bridge-Binary nicht gefunden: ${BINARY}"
    err "  Zuerst die Bridge cross-bauen (matter/build_bridge_app.sh)."
    exit 1
fi
if [ ! -f "${LIBS_TGZ}" ]; then
    err "matter_libs.tar.gz nicht gefunden: ${LIBS_TGZ}"
    err "  Libs packen (matter/deploy_bridge.sh / install_bridge.sh Libs)."
    exit 1
fi
if [ ! -d "${WEB_UI_SRC}" ]; then
    err "web-ui-Quellverzeichnis nicht gefunden: ${WEB_UI_SRC}"
    err "  Single-Source: matter/web-ui/ im Repo."
    exit 1
fi

if [ ! -d "${MQTT_PUBLISHER_SRC}" ]; then
    warn() { echo "[build-release][WARN] $*" >&2; }
    warn "mqtt-publisher-Quellverzeichnis nicht gefunden: ${MQTT_PUBLISHER_SRC}"
    warn "  MQTT-Publisher wird NICHT ins Bundle aufgenommen (enable_mqtt=true schlaegt dann fail-closed)."
    MQTT_PUBLISHER_SRC=""
fi

# Laufzeit-Dateien der web-ui-Payload (OHNE Dev-Artefakte).
# Dev-Artefakte, die NICHT ins Bundle kommen: build_toggle.sh, gardena-toggle.c,
# storm_test.sh (Quellcode + Build-Skripte bleiben auf dem Build-Host).
WEB_UI_RUNTIME_FILES=(
    "gardena-toggle"
    "matter.html"
    "qrcode.min.js"
    "gardena-matter-toggle.service"
    "gardena-matter-toggle.socket"
    "gardena-matter-status.service"
    "gardena-matter-status.timer"
    "gardena-matter-restore.service"
    "gardena-matter-restore.path"
    "gardena-matter-restore.sh"
    "update-matter-status.sh"
)

# Alle Laufzeit-Dateien pruefen (vor dem Staging, damit frueh abgebrochen wird).
for f in "${WEB_UI_RUNTIME_FILES[@]}"; do
    if [ ! -f "${WEB_UI_SRC}/${f}" ]; then
        err "web-ui-Laufzeit-Datei fehlt: ${WEB_UI_SRC}/${f}"
        exit 1
    fi
done

#
# Zwei unabhaengige Pruefungen, BEIDE muessen bestehen:
#
#  Gate A — Endpunkt-Selbsttest (semantisch):
#    grep -a sucht im Binary nach den C-String-Literalen der MQTT-Endpunkte.
#    Wenn /mqtt-config ODER /mqtt-status fehlt, ist der eingecheckte Binary veraltet
#    (er wurde nach der Erweiterung NICHT neu kompiliert) → Release ABBRUCH.
#    "-a" behandelt das Binary als Text (portabel: busybox grep auf Build-Host).
#
#  Gate B — Timestamps (defensiv, Fruehwarnung):
#    Vergleicht die letzte git-Commit-Zeit der Quelldatei vs. des Binaries.
#    Quelle neuer als Binary -> Warnung; kombiniert mit Gate-A bildet dies einen
#    starken Schutz. (mtime-Fallback falls git nicht verfuegbar.)
#
# Fail-closed: jeder Fehler bricht den Release-Build mit exit 1 ab.
# Kein Cross-Build in diesem Skript — Toggle muss VORHER auf dem Build-Host
# kompiliert worden sein (build_toggle.sh). Das Gate ist ein GUARD, kein Builder.

TOGGLE_BIN="${WEB_UI_SRC}/gardena-toggle"
TOGGLE_SRC="${WEB_UI_SRC}/gardena-toggle.c"

log "=== T2 Regressions-Gate: stale Toggle pruefen ==="

# Gate A: Endpunkt-Selbsttest
log "  Gate A: Endpunkt-Selbsttest (/mqtt-config, /mqtt-status) ..."
GATE_A_PASS=1
for endpoint in "/mqtt-config" "/mqtt-status"; do
    if ! grep -qa "${endpoint}" "${TOGGLE_BIN}" 2>/dev/null; then
        err "Regressions-Gate A FEHLGESCHLAGEN: Endpunkt '${endpoint}' nicht im Toggle-Binary gefunden."
        err "  Binary: ${TOGGLE_BIN}"
        err "  Der eingecheckte 'gardena-toggle' ist VERALTET — er wurde nach der MQTT-Erweiterung"
        err "  (gardena-toggle.c) NICHT NEU KOMPILIERT. Fehler: MQTT-Karte gibt HTTP 404."
        err ""
        err "  Behebung: auf dem Build-Host ausfuehren:"
        err "    cd /home/nextcloud/gardena-matter-gateway"
        err "    source /home/nextcloud/gardena-matter-build/sdk-oldsoft-host/environment-setup-mips32r2el-24kc-nf-gardena-linux"
        err "    bash matter/web-ui/build_toggle.sh"
        err "    git add matter/web-ui/gardena-toggle && git commit -m 'build: Toggle neu kompiliert (Endpunkte)' && git push"
        err "  Dann dieses Skript erneut ausfuehren."
        GATE_A_PASS=0
    fi
done
if [ "${GATE_A_PASS}" -eq 0 ]; then
    exit 1
fi
log "  Gate A: OK — /mqtt-config + /mqtt-status beide im Binary gefunden."

# Gate B: Timestamp-Vergleich (Quellcode neuer als Binary = Warnung + Abbruch)
log "  Gate B: Timestamp-Vergleich (Quelle vs. Binary) ..."
SRC_TIME=""
BIN_TIME=""
if git -C "${REPO_ROOT}" rev-parse HEAD >/dev/null 2>&1; then
    SRC_TIME="$(git -C "${REPO_ROOT}" log -1 --format='%ct' -- "${TOGGLE_SRC}" 2>/dev/null || true)"
    BIN_TIME="$(git -C "${REPO_ROOT}" log -1 --format='%ct' -- "${TOGGLE_BIN}" 2>/dev/null || true)"
fi
# Fallback: mtime (wenn git-Zeiten nicht ermittelbar)
if [ -z "${SRC_TIME}" ]; then
    SRC_TIME="$(stat -c%Y "${TOGGLE_SRC}" 2>/dev/null || stat -f%m "${TOGGLE_SRC}" 2>/dev/null || echo 0)"
fi
if [ -z "${BIN_TIME}" ]; then
    BIN_TIME="$(stat -c%Y "${TOGGLE_BIN}" 2>/dev/null || stat -f%m "${TOGGLE_BIN}" 2>/dev/null || echo 0)"
fi
if [ -n "${SRC_TIME}" ] && [ -n "${BIN_TIME}" ] && \
   [ "${SRC_TIME}" != "0" ] && [ "${BIN_TIME}" != "0" ]; then
    if [ "${SRC_TIME}" -gt "${BIN_TIME}" ]; then
        err "Regressions-Gate B FEHLGESCHLAGEN: gardena-toggle.c ist NEUER als das eingecheckte Binary."
        err "  gardena-toggle.c zuletzt geaendert (git/mtime): ${SRC_TIME}"
        err "  gardena-toggle    zuletzt geaendert (git/mtime): ${BIN_TIME}"
        err "  Gate A ist bereits gruen (Endpunkte gefunden) — dennoch Abbruch: Quelle neuer als Binary"
        err "  bedeutet, dass moeglicherweise weitere Aenderungen nicht im Binary sind."
        err "  Behebung: Toggle neu kompilieren (build_toggle.sh auf Build-Host) und committen."
        exit 1
    fi
    log "  Gate B: OK — Binary ist nicht aelter als Quelle (src=${SRC_TIME} bin=${BIN_TIME})."
else
    log "  Gate B: SKIPPED — Timestamps nicht ermittelbar (kein git / stat fehlgeschlagen)."
fi

log "=== Regressions-Gate BESTANDEN — Toggle-Binary aktuell. ==="

# VERSION = TAG (z.B. v0.1.5) — damit zeigt install_web_ui.sh beim Bundle-Deploy
# die echte Release-Version im Footer (statt git-SHA oder "dev").
# GIT_SHA = nur fuer das Log (Traceability), nicht in der VERSION-Datei.
VERSION="${TAG}"
GIT_SHA=""
if git -C "${REPO_ROOT}" rev-parse --short HEAD >/dev/null 2>&1; then
    GIT_SHA="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || true)"
fi

# -- Staging-Verzeichnis aufbauen ---------------------------------------------
mkdir -p "${OUT_DIR}"
STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT

# Flache Basis-Dateien
cp -p "${BINARY}"   "${STAGE}/chip-bridge-app.stripped"
cp -p "${LIBS_TGZ}" "${STAGE}/matter_libs.tar.gz"
printf '%s\n' "${VERSION}" > "${STAGE}/VERSION"

# web-ui/ Unterverzeichnis -- nur Laufzeit-Dateien, keine Dev-Artefakte
# (Quelle: matter/web-ui/ im Repo; Bundle-Zielname: web-ui/ -- kein Meilenstein-Code im Bundle)
mkdir -p "${STAGE}/web-ui"
for f in "${WEB_UI_RUNTIME_FILES[@]}"; do
    cp -p "${WEB_UI_SRC}/${f}" "${STAGE}/web-ui/${f}"
done

BUNDLE="${OUT_DIR}/gardena-bridge-${TAG}.tar.gz"

# Laufzeit-Dateien des MQTT-Publishers: Binary + Service-Unit + Install-Skript.
# Dev-Artefakte NICHT im Bundle: *.c, *.h, build_mqtt_publisher.sh, MQTT_CLIENT_SPIKE.md,
# mqtt.env.example (letzteres wird bei der Installation aus den Add-on-Optionen erzeugt).
MQTT_RUNTIME_FILES=(
    "install_mqtt_publisher.sh"
    "gardena-mqtt-publisher.service"
)
MQTT_INCLUDE_IN_BUNDLE=0
if [ -n "${MQTT_PUBLISHER_SRC}" ]; then
    # Pruefen ob das gebaute Binary vorhanden ist
    if [ -f "${MQTT_PUBLISHER_BIN}" ]; then
        mkdir -p "${STAGE}/mqtt-publisher"
        cp -p "${MQTT_PUBLISHER_BIN}" "${STAGE}/mqtt-publisher/gardena-mqtt-publisher"
        for f in "${MQTT_RUNTIME_FILES[@]}"; do
            if [ -f "${MQTT_PUBLISHER_SRC}/${f}" ]; then
                cp -p "${MQTT_PUBLISHER_SRC}/${f}" "${STAGE}/mqtt-publisher/${f}"
            else
                echo "[build-release][WARN] mqtt-publisher Laufzeit-Datei fehlt: ${MQTT_PUBLISHER_SRC}/${f}"
            fi
        done
        log "  mqtt-publisher/: Binary + ${#MQTT_RUNTIME_FILES[@]} Laufzeit-Dateien (ohne Dev-Artefakte)"
        MQTT_INCLUDE_IN_BUNDLE=1
    else
        log "  mqtt-publisher/: gardena-mqtt-publisher Binary nicht gefunden: ${MQTT_PUBLISHER_BIN}"
        log "  -> MQTT-Publisher nicht im Bundle (zuerst cross-bauen: mqtt-publisher/build_mqtt_publisher.sh)"
    fi
fi

# Deterministisches tar: feste Member-Reihenfolge, Mtime/Owner/Group genullt, so
# dass derselbe Input denselben SHA256 ergibt (idempotent + auditierbar).
# GNU-tar-Flags; --sort=name fuer stabile Reihenfolge.
log "Schnuere Bundle: ${BUNDLE}"
log "  web-ui/: ${#WEB_UI_RUNTIME_FILES[@]} Laufzeit-Dateien (ohne Dev-Artefakte)"

# Bundle-Member: Basis immer; mqtt-publisher/ nur wenn vorhanden
BUNDLE_MEMBERS="chip-bridge-app.stripped matter_libs.tar.gz VERSION web-ui"
if [ "${MQTT_INCLUDE_IN_BUNDLE}" -eq 1 ]; then
    BUNDLE_MEMBERS="${BUNDLE_MEMBERS} mqtt-publisher"
fi

tar \
    --sort=name \
    --mtime='UTC 1970-01-01' \
    --owner=0 --group=0 --numeric-owner \
    -C "${STAGE}" \
    -czf "${BUNDLE}" \
    ${BUNDLE_MEMBERS}

# -- SHA256 ausgeben (-> bridge-release.lock pinnen) -------------------------
SHA256="$(sha256sum "${BUNDLE}" | awk '{print $1}')"

log "Bundle fertig:"
log "  Pfad    : ${BUNDLE}"
log "  Tag     : ${TAG}"
log "  Version : ${VERSION} (in Bundle-VERSION-Datei; Footer zeigt diese Version)"
log "  Git-SHA : ${GIT_SHA:-unbekannt} (nur Log, nicht in VERSION-Datei)"
log "  SHA256  : ${SHA256}"
log ""
log "Naechster Schritt (Maintainer, NICHT dieser Lauf):"
log "  1. GitHub-Release <tag>=${TAG} erzeugen + ${BUNDLE} als Asset hochladen."
log "  2. ha-addon/gardena-matter-bridge/bridge-release.lock setzen:"
log "       { \"repo\": \"<owner/name>\", \"tag\": \"${TAG}\", \"sha256\": \"${SHA256}\" }"
log "  -> erst dann laesst der Add-on-Deploy das Hash-Gate passieren (sonst fail-closed)."

# Maschinenlesbare Ausgabe (letzte Zeile: nur der Hash) fuer Skript-Pipelines.
echo "${SHA256}"
