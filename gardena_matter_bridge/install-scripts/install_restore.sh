#!/usr/bin/env bash
# install_restore.sh — OTA-Haertung: restore-src/ befuellen + Restore-Service deployen
#
# Setzt die persistente Restore-Quelle /etc/gardena-matter/restore-src/ auf dem Gateway auf
# und installiert den vollstaendigen gardena-matter-restore.service.
#
# Voraussetzung: Bridge (install_bridge.sh) + Web-UI (install_web_ui.sh) bereits installiert.
#
# Platz-Strategie (25 MiB Overlay, 8 MiB Libs):
#   - Bridge-Binary + Libs: SYMLINKS in restore-src/usr-local-lib/ -> Originalort
#     (kein doppelter Verbrauch; Restore aus BRIDGE_DIR direkt)
#   - systemd-Units (klein, ~2 KB je): echte Kopien in restore-src/systemd/
#   - Web-Dateien (matter.html, qrcode.min.js): echte Kopien in restore-src/assets/
#   - Executables (gardena-toggle, update-matter-status.sh): Symlinks -> ETC_DIR
#
# Usage:
#   bash matter/install_restore.sh [GATEWAY_IP]
#   # oder env-gesteuert (HA-Add-on-Container):
#   GATEWAY_IP=... GARDENA_SSH_KEY=... bash matter/install_restore.sh
#
# Parameter ($1 ODER Env GATEWAY_IP; Positional gewinnt) = Ziel-Gateway (scp-Ziel).
#
# Defaults:
#   GATEWAY_IP = 192.0.2.1  (RFC5737 TEST-NET — Platzhalter, durch echte Gateway-IP ersetzen)
#
# Hard Constraints:
#   - KVS /var/lib/gardena-matter/chip_kvs NIEMALS wipen
#   - Closed Daemons (cloudadapter, lemonbeatd) unangetastet
#   - Kein echtes OTA ausloesen
#   - Reversibel (Overlay-only, kein Flash/Slot/OPKG)

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

RESTORE_SRC="/etc/gardena-matter/restore-src"
BRIDGE_DIR="/usr/local/lib/gardena-matter"
UNIT_DIR="/etc/systemd/system"
ETC_DIR="/etc/gardena-matter"
ASSETS_SRC="${ETC_DIR}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "======================================================="
log "install_restore.sh START"
log "  GATEWAY_IP   = ${GATEWAY_IP}"
log "  RESTORE_SRC  = ${RESTORE_SRC}"
log "======================================================="

# ── SSH-Test ───────────────────────────────────────────────────────────
ssh ${SSH_OPTS} "${GW}" 'echo "SSH OK; hostname=$(hostname)"' \
    && log "SSH OK" || { log "ERROR: SSH fehlgeschlagen"; exit 1; }

# ── Sicherstellen dass Bridge + Web-UI bereits installiert sind ────────
log "=== Voraussetzungen pruefen ==="
ssh ${SSH_OPTS} "${GW}" << 'CHECK_EOF'
OK=1
[ -f "/usr/local/lib/gardena-matter/chip-bridge-app" ] || { echo "ERROR: Bridge-Binary fehlt -- zuerst install_bridge.sh ausfuehren"; OK=0; }
[ -f "/usr/local/lib/gardena-matter/runbridge.sh" ]    || { echo "ERROR: runbridge.sh fehlt -- zuerst install_bridge.sh ausfuehren"; OK=0; }
[ -f "/etc/gardena-matter/gardena-toggle" ]            || { echo "ERROR: gardena-toggle fehlt -- zuerst install_web_ui.sh ausfuehren"; OK=0; }
[ -f "/etc/gardena-matter/matter.html" ]               || { echo "ERROR: matter.html fehlt -- zuerst install_web_ui.sh ausfuehren"; OK=0; }
[ -f "/etc/gardena-matter/qrcode.min.js" ]             || { echo "ERROR: qrcode.min.js fehlt -- zuerst install_web_ui.sh ausfuehren"; OK=0; }
[ ${OK} -eq 1 ] && echo "Voraussetzungen: OK" || exit 1
CHECK_EOF

# ── restore-src/ Verzeichnisstruktur anlegen ───────────────────────────
log "=== restore-src/ Verzeichnisse anlegen ==="
ssh ${SSH_OPTS} "${GW}" << MKDIR_EOF
mkdir -p "${RESTORE_SRC}/usr-local-lib"
mkdir -p "${RESTORE_SRC}/systemd"
mkdir -p "${RESTORE_SRC}/assets"
echo "Verzeichnisse angelegt: ${RESTORE_SRC}/"
MKDIR_EOF

# ── Bridge-Binary + Libs ──────────────────────────────────────────────
# Binary (1.9 MiB) + runbridge.sh (500 B): echte Kopien (Symlink wuerde bei
# partiell geloeschter Datei gebrochen sein -> nutzlos als Restore-Quelle).
# Libs: Symlinks (Libs sind im Paarverbund nicht partiell verlierbar; Symlinks
# sparen ~7.8 MiB im 25 MiB Overlay).
log "=== Bridge-Binary + runbridge.sh -> restore-src/usr-local-lib/ (echte Kopien) ==="
ssh ${SSH_OPTS} "${GW}" << BIN_EOF
cp -p "${BRIDGE_DIR}/chip-bridge-app" "${RESTORE_SRC}/usr-local-lib/chip-bridge-app"
chmod 755 "${RESTORE_SRC}/usr-local-lib/chip-bridge-app"
cp -p "${BRIDGE_DIR}/runbridge.sh"    "${RESTORE_SRC}/usr-local-lib/runbridge.sh"
chmod 755 "${RESTORE_SRC}/usr-local-lib/runbridge.sh"
echo "Binary + Launcher: echte Kopien OK"
echo "Platz-Verbrauch restore-src/usr-local-lib: \$(du -sh ${RESTORE_SRC}/usr-local-lib/ | cut -f1)"
BIN_EOF

log "=== Libs -> restore-src/usr-local-lib/ (Symlinks, ~0 extra Platz) ==="
ssh ${SSH_OPTS} "${GW}" << SYM_EOF
# Lib-Symlinks (nur die echten Dateien, keine duplizierten Varianten)
mkdir -p "${RESTORE_SRC}/usr-local-lib/lib"
mkdir -p "${RESTORE_SRC}/usr-local-lib/usr-lib"
for f in "${BRIDGE_DIR}/lib/"*; do
    [ -e "\${f}" ] || continue
    ln -sf "\${f}" "${RESTORE_SRC}/usr-local-lib/lib/\$(basename \${f})"
    echo "  lib/\$(basename \${f}) -> symlink"
done
for f in "${BRIDGE_DIR}/usr/lib/"*.so*; do
    [ -e "\${f}" ] || continue
    bn=\$(basename "\${f}")
    ln -sf "\${f}" "${RESTORE_SRC}/usr-local-lib/usr-lib/\${bn}"
    echo "  usr-lib/\${bn} -> symlink"
done
echo "Lib-Symlinks: OK"
SYM_EOF

# ── systemd-Units in restore-src/ kopieren (echte Kopien, klein) ──────
log "=== systemd-Units -> restore-src/systemd/ (echte Kopien) ==="
ssh ${SSH_OPTS} "${GW}" << UNIT_EOF
for unit in \
    gardena-matter-bridge.service \
    gardena-matter-toggle.service \
    gardena-matter-toggle.socket \
    gardena-matter-status.service \
    gardena-matter-status.timer \
    gardena-matter-restore.path
do
    src="${UNIT_DIR}/\${unit}"
    if [ -f "\${src}" ]; then
        cp -p "\${src}" "${RESTORE_SRC}/systemd/\${unit}"
        chmod 644 "${RESTORE_SRC}/systemd/\${unit}"
        echo "  \${unit}: OK"
    else
        echo "  WARN: \${unit} nicht gefunden -- uebersprungen"
    fi
done
echo "Platz-Verbrauch restore-src/systemd: \$(du -sh ${RESTORE_SRC}/systemd/ | cut -f1)"
UNIT_EOF

# ── Web-UI-Dateien in restore-src/ kopieren ───────────────────────────
log "=== Web-UI -> restore-src/assets/ (echte Kopien, ~70 KB) ==="
ssh ${SSH_OPTS} "${GW}" << ASSETS_EOF
cp -p "${ETC_DIR}/matter.html"   "${RESTORE_SRC}/assets/matter.html"
cp -p "${ETC_DIR}/qrcode.min.js" "${RESTORE_SRC}/assets/qrcode.min.js"
chmod 644 "${RESTORE_SRC}/assets/matter.html"
chmod 644 "${RESTORE_SRC}/assets/qrcode.min.js"
echo "matter.html + qrcode.min.js: OK"
echo "Platz-Verbrauch restore-src/assets: \$(du -sh ${RESTORE_SRC}/assets/ | cut -f1)"
ASSETS_EOF

# ── Executables: Symlinks (gardena-toggle, update-matter-status.sh) ───
log "=== /etc/gardena-matter/ Executables -> restore-src/etc/ (Symlinks) ==="
ssh ${SSH_OPTS} "${GW}" << ETC_EOF
mkdir -p "${RESTORE_SRC}/etc"
ln -sf "${ETC_DIR}/gardena-toggle"          "${RESTORE_SRC}/etc/gardena-toggle"
ln -sf "${ETC_DIR}/update-matter-status.sh" "${RESTORE_SRC}/etc/update-matter-status.sh"
echo "gardena-toggle + update-matter-status.sh: Symlinks OK"
ETC_EOF

# ── Restore-Skript hochladen ───────────────────────────────────────────
log "=== Restore-Skript hochladen ==="
scp -O ${SSH_OPTS} \
    "${WEB_UI_SRC}/gardena-matter-restore.sh" \
    "${GW}:${ETC_DIR}/gardena-matter-restore.sh"
ssh ${SSH_OPTS} "${GW}" "chmod 755 ${ETC_DIR}/gardena-matter-restore.sh"
log "Restore-Skript: ${ETC_DIR}/gardena-matter-restore.sh"

# ── Neue Restore-Service-Unit hochladen + aktivieren ──────────────────
log "=== Neuen gardena-matter-restore.service deployen ==="
scp -O ${SSH_OPTS} \
    "${WEB_UI_SRC}/gardena-matter-restore.service" \
    "${GW}:${UNIT_DIR}/gardena-matter-restore.service"
scp -O ${SSH_OPTS} \
    "${WEB_UI_SRC}/gardena-matter-restore.path" \
    "${GW}:${UNIT_DIR}/gardena-matter-restore.path"

ssh ${SSH_OPTS} "${GW}" << ACTIVATE_EOF
# Alten failed-State aufraumen
systemctl reset-failed gardena-matter-restore.service 2>/dev/null || true
systemctl reset-failed gardena-matter-restore.path    2>/dev/null || true

systemctl daemon-reload

systemctl enable gardena-matter-restore.service
systemctl enable gardena-matter-restore.path

echo "Restore-Service aktiviert"

# Einmal laufen lassen (erster Test: alle Komponenten vorhanden -> "nichts zu tun")
systemctl start gardena-matter-restore.service
echo "Erster Restore-Lauf abgeschlossen (erwartet: alle vorhanden)"

# Path-Watch starten
systemctl start gardena-matter-restore.path
echo "Path-Watch aktiv"

echo ""
echo "=== Restore-Service Status ==="
systemctl status gardena-matter-restore.service --no-pager || true
ACTIVATE_EOF

# ── Footprint pruefen ──────────────────────────────────────────────────
log "=== Footprint-Check ==="
ssh ${SSH_OPTS} "${GW}" << FOOT_EOF
echo "restore-src Gesamtgroesse (inkl. Symlinks):"
du -sh "${RESTORE_SRC}/"
echo ""
echo "restore-src Inhalt:"
ls -la "${RESTORE_SRC}/"
echo ""
echo "Overlay-Platz gesamt:"
df -h / | tail -1
echo ""
echo "KVS (unveraendert):"
ls -lh /var/lib/gardena-matter/chip_kvs 2>/dev/null && echo "chip_kvs: OK (unberuehrt)" || echo "(noch nicht angelegt)"
echo ""
echo "Vendor-Stack (muss active sein):"
for s in cloudadapter lemonbeatd; do
    echo "  \${s}: \$(systemctl is-active \${s} 2>/dev/null || echo unknown)"
done
FOOT_EOF

log ""
log "==================================================================="
log "install_restore.sh DONE"
log ""
log "  restore-src/: ${RESTORE_SRC} (Symlinks fuer Binary/Libs, Kopien fuer Units/Assets)"
log "  Restore-Skript: ${ETC_DIR}/gardena-matter-restore.sh"
log "  Service: gardena-matter-restore.service (enabled, ran once)"
log ""
log "  Akzeptanz-Test -- Anleitung:"
log "    1. Eine Datei testweise loeschen:"
log "       ssh root@${GATEWAY_IP} 'rm /usr/share/gateway-config-interface/www/assets/matter.html'"
log "    2. Restore starten:"
log "       ssh root@${GATEWAY_IP} 'systemctl start gardena-matter-restore.service'"
log "    3. Datei wiederhergestellt pruefen:"
log "       ssh root@${GATEWAY_IP} 'ls -l /usr/share/.../assets/matter.html'"
log "    4. KVS unveraendert pruefen:"
log "       ssh root@${GATEWAY_IP} 'ls -lh /var/lib/gardena-matter/chip_kvs'"
log "    5. Bridge aktiv pruefen:"
log "       ssh root@${GATEWAY_IP} 'systemctl is-active gardena-matter-bridge'"
log ""
log "  Uninstall:"
log "    ssh root@${GATEWAY_IP} 'rm -rf ${RESTORE_SRC}'"
log "    + systemctl disable/stop gardena-matter-restore.service path"
log "==================================================================="
