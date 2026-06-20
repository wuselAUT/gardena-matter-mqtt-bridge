#!/usr/bin/env bash
# install_web_ui.sh — Web-UI-Komponenten ins Gateway-Overlay installieren
#
# Installiert die Web-UI-Komponenten ins Gateway-Overlay:
#   - gardena-toggle (kompiliertes Binary, MIPS fp_abi=0) → /etc/gardena-matter/
#   - matter.html + qrcode.min.js → /etc/gardena-matter/ (persistent) UND
#                                    /assets/ (www-Overlay, unauth)
#   - gardena-matter-toggle.socket/.service   → /etc/systemd/system/
#   - gardena-matter-status.service/.timer    → /etc/systemd/system/
#   - gardena-matter-restore.service/.path    → /etc/systemd/system/ (OTA-Restore)
#   - update-matter-status.sh                 → /etc/gardena-matter/
#
# Kurskorrektur:
#   Seite liegt unter /assets/matter.html (unauth — Gateway liefert /assets/* ohne Login aus).
#   Die Seite authentifiziert sich SELBST per JS: Login-Feld → POST /login → Session-Token
#   → fetch /matter-status.json mit X-session-Header.
#
# URL nach Install:
#   https://<gateway-ip>/assets/matter.html  → 200 UNAUTH, Browser-ladbar
#   http://<gateway-ip>:8099/toggle          → Toggle-API (X-Session Auth)
#   https://<gateway-ip>/matter-status.json  → Status-JSON (X-session noetig)
#
# Usage:
#   bash matter/install_web_ui.sh [GATEWAY_IP]
#   # oder env-gesteuert (HA-Add-on-Container):
#   GATEWAY_IP=... GARDENA_SSH_KEY=... bash matter/install_web_ui.sh
#
# Parameter ($1 ODER Env GATEWAY_IP; Positional gewinnt) = Ziel-Gateway (scp-Ziel).
#
# Hard Constraints:
#   - Passwort NIEMALS speichern/loggen/committen
#   - Closed Backend (gateway-config-backend) NICHT patchen
#   - Reversibel (Overlay-Only, kein Flash/Slot/OPKG)
#   - lemonbeatd/cloudadapter/accessory-server NICHT stoppen
#   - Slot A / Recovery NICHT gefaehrden
#
set -euo pipefail

# GATEWAY_IP: Positional $1 ODER Env GATEWAY_IP ODER RFC5737-TEST-NET-Platzhalter.
GATEWAY_IP="${1:-${GATEWAY_IP:-192.0.2.1}}"
SSH_KEY="${GARDENA_SSH_KEY:-${HOME:-/root}/.ssh/id_ed25519}"
SSH_OPTS="-i ${SSH_KEY} -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=${HOME:-/root}/.ssh/known_hosts_gardena -o ConnectTimeout=15"
GW="root@${GATEWAY_IP}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# WEB_UI_SRC: Env-Override -- im Add-on-Container setzt build_install_script_command
# WEB_UI_SRC=<unpack_dir>/web-ui; auf dem Build-Host greift der Default SCRIPT_DIR/web-ui.
WEB_UI_SRC="${WEB_UI_SRC:-${WEB_UI_SRC:-${SCRIPT_DIR}/web-ui}}"
WWW_DST="/usr/share/gateway-config-interface/www"
ASSETS_DST="${WWW_DST}/assets"
INSTALL_DIR="/etc/gardena-matter"
UNIT_DIR="/etc/systemd/system"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "======================================================="
log "install_web_ui.sh START"
log "  GATEWAY_IP  = ${GATEWAY_IP}"
log "  INSTALL_DIR = ${INSTALL_DIR}"
log "  ASSETS_DST  = ${ASSETS_DST}"
log "  WEB_UI_SRC  = ${WEB_UI_SRC}"
log "======================================================="

# ── Voraussetzungen pruefen ────────────────────────────────────────────
if [ ! -f "${WEB_UI_SRC}/gardena-toggle" ]; then
    log "ERROR: Compiled Binary nicht gefunden: ${WEB_UI_SRC}/gardena-toggle"
    log "  Bitte zuerst bauen: source SDK && bash ${WEB_UI_SRC}/build_toggle.sh"
    exit 1
fi
if [ ! -f "${WEB_UI_SRC}/qrcode.min.js" ]; then
    log "ERROR: qrcode.min.js fehlt."
    log "  Bitte einmalig ausfuehren: bash matter/web-ui/fetch_qrcode_js.sh"
    log "  (Dann nach ${WEB_UI_SRC}/ kopieren)"
    exit 1
fi
if [ ! -f "${WEB_UI_SRC}/matter.html" ]; then
    log "ERROR: matter.html fehlt in ${WEB_UI_SRC}/"
    exit 1
fi

# ── SSH-Test ───────────────────────────────────────────────────────────
ssh ${SSH_OPTS} "${GW}" 'echo "SSH OK; hostname=$(hostname)"' \
    && log "SSH zum Gateway OK" \
    || { log "ERROR: SSH fehlgeschlagen"; exit 1; }

# ── Alte Web-UI-Reste deaktivieren (falls aktiv) ──────────────────────
log "=== Alte Dienste deaktivieren (falls aktiv) ==="
ssh ${SSH_OPTS} "${GW}" << 'CLEANUP_EOF'
for u in gardena-matter-web.socket gardena-matter-web.service; do
    if systemctl is-active --quiet "$u" 2>/dev/null; then
        systemctl stop "$u" && echo "Stopped: $u"
    fi
    if systemctl is-enabled --quiet "$u" 2>/dev/null; then
        systemctl disable "$u" && echo "Disabled: $u"
    fi
done
# Alte matter.html aus www-Root entfernen (war die 401-Stelle)
if [ -f "/usr/share/gateway-config-interface/www/matter.html" ]; then
    rm -f "/usr/share/gateway-config-interface/www/matter.html"
    echo "Entfernt: www/matter.html"
fi
echo "Bereinigung abgeschlossen"
CLEANUP_EOF

# ── Verzeichnisse anlegen ──────────────────────────────────────────────
log "=== Overlay-Verzeichnisse anlegen ==="
ssh ${SSH_OPTS} "${GW}" "mkdir -p ${INSTALL_DIR} && mkdir -p ${ASSETS_DST}"

# ── __BUILD_VERSION__ im matter.html ersetzen ─────────────────────────
# Platzhalter __BUILD_VERSION__ -> echte Release-Version (kein "dev" bei Deploy aus Bundle).
#
#   1. WEB_UI_SRC/../VERSION  — Bundle-Root (z. B. /tmp/unpack/VERSION); greift beim
#      Add-on-Deploy aus dem Tarball (orchestrate.py entpackt nach <unpack_dir>/,
#      setzt WEB_UI_SRC=<unpack_dir>/web-ui → ../VERSION = <unpack_dir>/VERSION).
#   2. SCRIPT_DIR/../VERSION  — naechstes Verzeichnis relativ zum Skript (Overlay-Deploy).
#   3. git rev-parse --short HEAD  — wenn ein git-Repo vorhanden (Dev-Lauf, Build-Host).
#   4. "dev"  — echter Fallback, nur wenn weder Bundle-VERSION noch git vorhanden.
#
# Dadurch zeigt der Footer nach Tarball-Deploy immer "vX.Y.Z" statt "dev".
log "=== Build-Version einsetzen ==="
BUILD_VERSION=""

# Suchpfad 1: Bundle-Root (WEB_UI_SRC/../VERSION — greift beim Add-on-Deploy aus Tarball)
BUNDLE_ROOT="$(cd "${WEB_UI_SRC}/.." && pwd)"
if [ -f "${BUNDLE_ROOT}/VERSION" ]; then
    BUILD_VERSION="$(tr -d '[:space:]' < "${BUNDLE_ROOT}/VERSION")"
    log "  BUILD_VERSION (Bundle-Root ${BUNDLE_ROOT}/VERSION) = ${BUILD_VERSION}"
fi

# Suchpfad 2: Skript-Verzeichnis-Elternteil (Overlay-Deploy ohne Bundle-Root)
if [ -z "${BUILD_VERSION}" ]; then
    SCRIPT_PARENT="$(cd "${SCRIPT_DIR}/.." && pwd)"
    if [ -f "${SCRIPT_PARENT}/VERSION" ]; then
        BUILD_VERSION="$(tr -d '[:space:]' < "${SCRIPT_PARENT}/VERSION")"
        log "  BUILD_VERSION (Script-Parent ${SCRIPT_PARENT}/VERSION) = ${BUILD_VERSION}"
    fi
fi

# Suchpfad 3: git rev-parse (Dev-Lauf / Build-Host — kein Tarball-Deploy)
if [ -z "${BUILD_VERSION}" ]; then
    # Suche nach git-Repo im WEB_UI_SRC oder darueber
    for _git_dir in "${BUNDLE_ROOT}" "$(cd "${BUNDLE_ROOT}/.." 2>/dev/null && pwd || echo "")"; do
        if [ -n "${_git_dir}" ] && git -C "${_git_dir}" rev-parse --short HEAD >/dev/null 2>&1; then
            BUILD_VERSION="$(git -C "${_git_dir}" rev-parse --short HEAD 2>/dev/null || true)"
            log "  BUILD_VERSION (git rev-parse in ${_git_dir}) = ${BUILD_VERSION}"
            break
        fi
    done
fi

# Suchpfad 4: echter Fallback
if [ -z "${BUILD_VERSION}" ]; then
    BUILD_VERSION="dev"
    log "  BUILD_VERSION = dev (Fallback — kein Bundle/VERSION/git gefunden)"
fi

log "  BUILD_VERSION final = ${BUILD_VERSION}"

# Temporaere Kopie mit ersetztem Platzhalter erzeugen (Original bleibt unveraendert)
MATTER_HTML_TMP="/tmp/matter_$$.html"
sed "s/__BUILD_VERSION__/${BUILD_VERSION}/g" "${WEB_UI_SRC}/matter.html" > "${MATTER_HTML_TMP}"
trap 'rm -f "${MATTER_HTML_TMP}"' EXIT

# ── Dateien permanent in /etc/gardena-matter/ ablegen (OTA-Restore-Quelle) ──
log "=== Persistente Ablage in ${INSTALL_DIR}/ ==="
scp -O ${SSH_OPTS} \
    "${WEB_UI_SRC}/gardena-toggle" \
    "${WEB_UI_SRC}/update-matter-status.sh" \
    "${WEB_UI_SRC}/qrcode.min.js" \
    "${GW}:${INSTALL_DIR}/"
# matter.html mit gesetzter Version (Ziel-Dateiname explizit gesetzt)
scp -O ${SSH_OPTS} "${MATTER_HTML_TMP}" "${GW}:${INSTALL_DIR}/matter.html"

ssh ${SSH_OPTS} "${GW}" "
    chmod +x ${INSTALL_DIR}/gardena-toggle
    chmod +x ${INSTALL_DIR}/update-matter-status.sh
    chmod 644 ${INSTALL_DIR}/matter.html
    chmod 644 ${INSTALL_DIR}/qrcode.min.js
"
log "Binary + Skripte + Web-Dateien in ${INSTALL_DIR}/ abgelegt"

# ── /assets/ befuellen (Live-Pfad, unauth) ────────────────────────────
log "=== /assets/ befuellen (Browser-ladbar, unauth) ==="
ssh ${SSH_OPTS} "${GW}" "
    cp ${INSTALL_DIR}/matter.html    ${ASSETS_DST}/matter.html
    cp ${INSTALL_DIR}/qrcode.min.js  ${ASSETS_DST}/qrcode.min.js
    chmod 644 ${ASSETS_DST}/matter.html
    chmod 644 ${ASSETS_DST}/qrcode.min.js
    echo 'matter.html + qrcode.min.js in ${ASSETS_DST}/ installiert'
"
log "matter.html + qrcode.min.js in ${ASSETS_DST}/ installiert"

# ── systemd-Units uebertragen ──────────────────────────────────────────
log "=== systemd-Units installieren ==="
scp -O ${SSH_OPTS} \
    "${WEB_UI_SRC}/gardena-matter-toggle.socket" \
    "${WEB_UI_SRC}/gardena-matter-toggle.service" \
    "${WEB_UI_SRC}/gardena-matter-status.service" \
    "${WEB_UI_SRC}/gardena-matter-status.timer" \
    "${WEB_UI_SRC}/gardena-matter-restore.service" \
    "${WEB_UI_SRC}/gardena-matter-restore.path" \
    "${GW}:${UNIT_DIR}/"

# ── systemctl-Setup ───────────────────────────────────────────────────
log "=== systemctl-Setup ==="
ssh ${SSH_OPTS} "${GW}" << 'UNITEOF'
systemctl daemon-reload

# Toggle-Socket enablen + starten
systemctl enable gardena-matter-toggle.socket
systemctl start  gardena-matter-toggle.socket
echo "Toggle-Socket: gestartet"

# Status-Timer enablen + starten
systemctl enable gardena-matter-status.timer
systemctl start  gardena-matter-status.timer
echo "Status-Timer: gestartet"

# Status sofort einmal erzeugen
systemctl start gardena-matter-status.service
echo "Status-JSON: initial erzeugt"

# OTA-Restore enablen + einmal laufen lassen
systemctl enable gardena-matter-restore.service
systemctl enable gardena-matter-restore.path
systemctl start  gardena-matter-restore.service
systemctl start  gardena-matter-restore.path
echo "OTA-Restore: aktiviert"

echo ""
echo "=== Dienst-Status ==="
systemctl status gardena-matter-toggle.socket  --no-pager || true
systemctl status gardena-matter-status.timer   --no-pager || true
systemctl status gardena-matter-restore.service --no-pager || true

echo ""
echo "=== Vendor-Stack-Check (darf NICHT gestoert sein) ==="
for s in lemonbeatd cloudadapter lwm2mserver accessory-server; do
    st=$(systemctl is-active "$s" 2>/dev/null || echo "unknown")
    echo "  $s: $st"
done

echo ""
echo "=== Bridge-Check ==="
systemctl is-active gardena-matter-bridge && echo "Bridge: ACTIVE" || echo "Bridge: inactive"
UNITEOF

# ── Footprint-Check ───────────────────────────────────────────────────
log "=== Footprint-Check ==="
ssh ${SSH_OPTS} "${GW}" "
    echo '--- /etc/gardena-matter ---'
    du -sh ${INSTALL_DIR}/
    echo '--- /assets/ ---'
    du -sh ${ASSETS_DST}/matter.html ${ASSETS_DST}/qrcode.min.js 2>/dev/null || true
    echo '--- matter-status.json ---'
    du -sh ${WWW_DST}/matter-status.json 2>/dev/null || true
    echo '--- RAM ---'
    free -m
"

# ── Verifikation: deployt == Repo ─────────────────────────────────────
log "=== Verifikation: deployt == Repo (md5sum) ==="
LOCAL_HTML_MD5=$(md5sum "${WEB_UI_SRC}/matter.html"       | awk '{print $1}')
LOCAL_QR_MD5=$(md5sum   "${WEB_UI_SRC}/qrcode.min.js"    | awk '{print $1}')
LOCAL_BIN_MD5=$(md5sum  "${WEB_UI_SRC}/gardena-toggle"    | awk '{print $1}')

ssh ${SSH_OPTS} "${GW}" "
    GW_HTML_MD5=\$(md5sum ${ASSETS_DST}/matter.html        2>/dev/null | awk '{print \$1}' || echo 'MISSING')
    GW_QR_MD5=\$(  md5sum ${ASSETS_DST}/qrcode.min.js      2>/dev/null | awk '{print \$1}' || echo 'MISSING')
    GW_BIN_MD5=\$( md5sum ${INSTALL_DIR}/gardena-toggle    2>/dev/null | awk '{print \$1}' || echo 'MISSING')
    echo \"matter.html: local=${LOCAL_HTML_MD5}  gw=\${GW_HTML_MD5}\"
    echo \"qrcode.min.js: local=${LOCAL_QR_MD5}  gw=\${GW_QR_MD5}\"
    echo \"gardena-toggle: local=${LOCAL_BIN_MD5}  gw=\${GW_BIN_MD5}\"
    [ \"\${GW_HTML_MD5}\" = \"${LOCAL_HTML_MD5}\" ] && echo 'matter.html: deployt==Repo OK' || echo 'WARN: matter.html-md5 weicht ab'
    [ \"\${GW_QR_MD5}\"   = \"${LOCAL_QR_MD5}\"   ] && echo 'qrcode.min.js: deployt==Repo OK' || echo 'WARN: qrcode.min.js-md5 weicht ab'
    [ \"\${GW_BIN_MD5}\"  = \"${LOCAL_BIN_MD5}\"  ] && echo 'gardena-toggle: deployt==Repo OK' || echo 'WARN: gardena-toggle-md5 weicht ab'
"

# ── /assets/matter.html → 200 UNAUTH pruefen ─────────────────────────
log "=== /assets/matter.html unauth (curl auf 127.0.0.1) ==="
ssh ${SSH_OPTS} "${GW}" "
    HTTP_CODE=\$(curl -s -o /dev/null -w '%{http_code}' --insecure https://127.0.0.1/assets/matter.html 2>/dev/null)
    echo \"curl https://127.0.0.1/assets/matter.html → HTTP \${HTTP_CODE}\"
    [ \"\${HTTP_CODE}\" = '200' ] && echo 'PASS: /assets/matter.html 200 unauth' || echo 'WARN: Erwartet 200, got \${HTTP_CODE}'
"

# ── Zusammenfassung ───────────────────────────────────────────────────
log ""
log "==================================================================="
log "install_web_ui.sh DONE"
log ""
log "  Seite (unauth, Browser-ladbar):"
log "    https://${GATEWAY_IP}/assets/matter.html"
log ""
log "  Login-Flow: Gateway-Passwort eingeben → Session-Token → QR"
log "  Toggle-API: http://${GATEWAY_IP}:8099/toggle (X-Session Auth)"
log "  Status-JSON: https://${GATEWAY_IP}/matter-status.json (X-session noetig)"
log ""
log "  OTA-Restore: gardena-matter-restore.service (WantedBy=multi-user)"
log "==================================================================="
log ""
log "USER-VERIFY:"
log "  1. Browser: https://${GATEWAY_IP}/assets/matter.html"
log "     → muss OHNE Passwort laden (200, kein 401-Pop-up)"
log "  2. Gateway-Passwort eingeben (erste 8 Zeichen der Geraete-ID)"
log "  3. QR-Code + Manual-Code sehen + mit Smart-Home-App scannen"
log "  4. Toggle 'Matter ausschalten' → Bridge stoppt"
log "  5. Toggle 'Matter einschalten' → Bridge startet"
