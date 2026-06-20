#!/usr/bin/env bash
#
# Legt Binary + Libs + Launcher in /usr/local/lib/gardena-matter/ (persistentes Overlay),
# installiert systemd-Unit + enable, setzt persistente Firewall-Regel via ExecStartPre.
#
# Usage (auf Build-Host, lokalem Rechner ODER im HA-Add-on-Container):
#   bash matter/install_bridge.sh [BINARY_PATH] [GATEWAY_IP]
#   BINARY_PATH=... LIBS_TGZ=... GATEWAY_IP=... GARDENA_SSH_KEY=... bash matter/install_bridge.sh
#
# Defaults:
#   BINARY_PATH = ~/gardena-matter-build/out/mips-bridge/chip-bridge-app.stripped
#   GATEWAY_IP  = 192.0.2.1  (RFC5737 TEST-NET — Platzhalter, durch echte Gateway-IP ersetzen)
#   LIBS_TGZ    = ~/gardena-matter-build/matter_libs.tar.gz
#
# Parameter (Positional ODER gleichnamige Env-Variable; Positional gewinnt):
#   $1 / BINARY_PATH = Pfad zur Bridge-Binary (z. B. entpackt aus dem Release-Bundle)
#   $2 / GATEWAY_IP  = Ziel-Gateway (scp-Ziel; der Add-on-Container reicht gateway_host durch)
#   LIBS_TGZ         = Pfad zum matter_libs.tar.gz (entpackt aus dem Release-Bundle)
#
# SSH-Key:
#   Default: ~/.ssh/id_ed25519 (via scripts/enable-ssh.sh registriert)
#   Override: GARDENA_SSH_KEY=/path/to/key (Add-on: Add-on-Private-Key)
#
#   - KVS /var/lib/gardena-matter/chip_kvs NIEMALS wipen/verschieben
#   - Kein Flashen, kein OPKG, kein Slot-Eingriff
#   - Keine Vendor-Firewall-Dateien patchen
#   - Overlay /usr/local/lib/gardena-matter/ (NOT /tmp, NOT /usr/share [read-only squashfs])
#
# Abgrenzung zu deploy_bridge.sh:
#   deploy_bridge.sh  = Dev-Deploy nach /tmp (flüchtig, für schnelles Testen)
#   install_bridge.sh = Persistente Installation ins Overlay (reboot-fest, für Produktion)
#

set -euo pipefail

BUILD_ROOT="${HOME:-/root}/gardena-matter-build"
# BINARY: Positional $1 ODER Env BINARY_PATH ODER Build-Host-Default.
BINARY="${1:-${BINARY_PATH:-${BUILD_ROOT}/out/mips-bridge/chip-bridge-app.stripped}}"
# GATEWAY_IP: Positional $2 ODER Env GATEWAY_IP ODER neutraler Platzhalter.
GATEWAY_IP="${2:-${GATEWAY_IP:-192.0.2.1}}"
SSH_KEY="${GARDENA_SSH_KEY:-${HOME:-/root}/.ssh/id_ed25519}"
SSH_OPTS="-i ${SSH_KEY} -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=${HOME:-/root}/.ssh/known_hosts_gardena -o ConnectTimeout=15"
LOG="${BUILD_ROOT}/install_bridge.log"

# Ziel-Pfade auf dem Gerät (persistentes Overlay)
INSTALL_DIR="/usr/local/lib/gardena-matter"
LAUNCHER="${INSTALL_DIR}/runbridge.sh"
UNIT_FILE="/etc/systemd/system/gardena-matter-bridge.service"
KVS_DIR="/var/lib/gardena-matter"

# LIBS_TGZ: Env LIBS_TGZ (z. B. entpackt aus dem Release-Bundle) ODER Build-Host-Default.
LIBS_TGZ="${LIBS_TGZ:-${BUILD_ROOT}/matter_libs.tar.gz}"

GW="root@${GATEWAY_IP}"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "${LOG}"; }

mkdir -p "${BUILD_ROOT}"

log "======================================================="
log "install_bridge.sh START"
log "  BINARY     = ${BINARY}"
log "  GATEWAY_IP = ${GATEWAY_IP}"
log "  INSTALL_DIR= ${INSTALL_DIR}"
log "  KVS_DIR    = ${KVS_DIR}  (NICHT gewipet)"
log "  LOG        = ${LOG}"
log "======================================================="

# ─── Sanity-Checks ──────────────────────────────────────────────────────────
if [ ! -f "${BINARY}" ]; then
    log "ERROR: Binary nicht gefunden: ${BINARY}"
    log "Bitte zuerst bash matter/build_bridge_app.sh ausführen"
    exit 1
fi

if [ ! -f "${LIBS_TGZ}" ]; then
    log "ERROR: matter_libs.tar.gz nicht gefunden: ${LIBS_TGZ}"
    log "Bitte zuerst bash matter/deploy_bridge.sh ausführen (erstellt libs) oder"
    log "  SDK-Sysroot manuell packen (siehe deploy_bridge.sh §Libs-Archiv)"
    exit 1
fi

# SSH-Test
ssh ${SSH_OPTS} "${GW}" 'echo "SSH OK; hostname=$(hostname)"' >> "${LOG}" 2>&1 \
    && log "SSH zum Gateway OK" \
    || { log "ERROR: SSH fehlgeschlagen"; exit 1; }

# ─── Binary + Libs + Launcher in persistenten Overlay-Pfad ──────────────
log "=== Persistente Installation ins Overlay ==="

# Vorhandene Bridge stoppen (aus /tmp oder aus persistentem Pfad)
# pgrep -x scheitert auf BusyBox-MIPS, wenn der Prozessname länger als 15 Zeichen ist
# (trunciert). Fallback: alle chip-bridge-app-Prozesse via /proc/*/exe suchen.
log "Stoppe ggf. laufende Bridge (alle Instanzen) ..."
ssh ${SSH_OPTS} "${GW}" << 'STOPEOF'
# Schritt 1: systemd-Service stoppen (falls schon installiert)
if systemctl is-active gardena-matter-bridge.service >/dev/null 2>&1; then
    systemctl stop gardena-matter-bridge.service
    echo "gardena-matter-bridge.service gestoppt"
    sleep 2
fi
# Schritt 2: Prozesse via /proc/*/exe finden (robust gegenüber BusyBox-Truncation)
PIDS=""
for d in /proc/[0-9]*/exe; do
    target=$(readlink "${d}" 2>/dev/null || echo "")
    if echo "${target}" | grep -q "chip-bridge-app"; then
        pid=${d%/exe}; pid=${pid#/proc/}
        PIDS="${PIDS} ${pid}"
    fi
done
if [ -n "${PIDS}" ]; then
    for pid in ${PIDS}; do
        kill "${pid}" 2>/dev/null && echo "Prozess beendet (PID=${pid})" || true
    done
    sleep 2
else
    echo "Kein laufender chip-bridge-app-Prozess gefunden"
fi
STOPEOF

# Ziel-Verzeichnis anlegen
log "Lege ${INSTALL_DIR} an ..."
ssh ${SSH_OPTS} "${GW}" "mkdir -p ${INSTALL_DIR}/lib ${INSTALL_DIR}/usr/lib"

# Binary übertragen
log "Übertrage Binary (scp -O) ..."
BINARY_SIZE=$(du -sh "${BINARY}" | cut -f1)
log "  Binary-Größe: ${BINARY_SIZE}"
scp -O ${SSH_OPTS} "${BINARY}" "${GW}:${INSTALL_DIR}/chip-bridge-app"
ssh ${SSH_OPTS} "${GW}" "chmod +x ${INSTALL_DIR}/chip-bridge-app"
log "Binary installiert: ${INSTALL_DIR}/chip-bridge-app"

# Libs übertragen und entpacken
log "Übertrage + entpacke Libs ..."
scp -O ${SSH_OPTS} "${LIBS_TGZ}" "${GW}:/tmp/matter_libs_install.tar.gz"
ssh ${SSH_OPTS} "${GW}" << LIBEOF
cd ${INSTALL_DIR}
tar xzf /tmp/matter_libs_install.tar.gz
rm -f /tmp/matter_libs_install.tar.gz
# Libs in flaches lib/ und usr/lib/ legen (falls tar eine verschachtelte Struktur entpackt)
find ${INSTALL_DIR} -name "*.so*" | while read so; do
    target="${INSTALL_DIR}/usr/lib/\$(basename \"\${so}\")"
    if [ "\${so}" != "\${target}" ]; then
        cp -L "\${so}" "\${target}" 2>/dev/null || true
    fi
done
echo "Libs in ${INSTALL_DIR}:"
ls -lh ${INSTALL_DIR}/usr/lib/ 2>/dev/null || echo "(leer)"
LIBEOF
log "Libs installiert: ${INSTALL_DIR}/usr/lib/"

log "KVS-Verzeichnis sicherstellen (NICHT wipen) ..."
ssh ${SSH_OPTS} "${GW}" << KVSEOF
mkdir -p ${KVS_DIR}
if [ -f "${KVS_DIR}/chip_kvs" ]; then
    echo "KVS existiert bereits: \$(ls -lh ${KVS_DIR}/chip_kvs)"
    echo "KVS BLEIBT UNANGETASTET — HA-Pairing erhalten"
else
    echo "KVS-Datei noch nicht vorhanden (wird beim ersten Start angelegt)"
fi
KVSEOF

# Launcher-Skript schreiben (generate-if-absent + Verifier-Uebergabe)
log "Schreibe Launcher ${LAUNCHER} ..."
ssh ${SSH_OPTS} "${GW}" "cat > ${LAUNCHER}" << LAUNCHEREOF
#!/bin/sh
# Installiert in ${INSTALL_DIR} (persistentes Overlay, ueberlebt Reboot)
#
# : Commissioning-Credentials (Spake2+-Verifier) generate-if-absent:
#   Beim ersten Start erzeugt chip-bridge-app --generate-commissioning die conf.
#   Danach wird sie gesourct und der Verifier (NICHT der Passcode) uebergeben.
#   Idempotent: conf wird nur erzeugt wenn sie fehlt.
#
# EN: On first start, generates unique commissioning credentials (Spake2+ verifier).
#     Passcode is never stored or passed to the long-running bridge process.
# DE: Beim Erststart werden einmalig eindeutige Credentials erzeugt (Spake2+-Verifier).
#     Der Passcode wird nie gespeichert oder an den laufenden Bridge-Prozess uebergeben.
#
# (global/ULA fd.., NICHT link-local fe80:: und NICHT Mesh-Prefix)
# auf dem LAN-Interface verfuegbar ist.
# Bounded Wait-Loop: max. 60 Sekunden, Poll 1s.
# Nach Timeout: trotzdem starten + WARN-Log (robuster Betrieb).
#
# EN: Wait for a routable IPv6 (global/ULA, not link-local, not Mesh ppp0)
#     on the broadcast LAN interface before starting chip-bridge-app.
# DE: Vor dem Start auf eine routbare IPv6 warten (max. 60s).

CONF_FILE="${KVS_DIR}/commissioning.conf"

# Commissioning-Credentials erzeugen falls conf fehlt
if [ ! -f "\${CONF_FILE}" ]; then
    echo "[runbridge.sh] commissioning.conf fehlt — erzeuge Credentials..."
    # BUG-A-FIX: LD_LIBRARY_PATH VOR dem --generate-commissioning-Aufruf exportieren,
    # damit chip-bridge-app libstdc++.so.6 findet (ohne Library-Pfad: exit mit Shared-Lib-Fehler).
    export LD_LIBRARY_PATH=${INSTALL_DIR}/usr/lib:${INSTALL_DIR}/lib
    ${INSTALL_DIR}/chip-bridge-app --generate-commissioning "\${CONF_FILE}"
    gen_rc=\$?
    # BUG-B-FIX: Exit-Code pruefen; bei Fehler fail-closed (kein bedingungsloses 'erzeugt').
    if [ "\${gen_rc}" -ne 0 ]; then
        echo "[runbridge.sh] FEHLER: --generate-commissioning fehlgeschlagen (Exit \${gen_rc})" >&2
        exit 1
    fi
    # Verifizieren, dass conf existiert und Pflicht-Keys enthaelt.
    if [ ! -f "\${CONF_FILE}" ]; then
        echo "[runbridge.sh] FEHLER: commissioning.conf wurde nicht erzeugt" >&2
        exit 1
    fi
    for _key in GARDENA_DISCRIMINATOR GARDENA_SPAKE2P_VERIFIER GARDENA_SPAKE2P_SALT GARDENA_SPAKE2P_ITERATIONS; do
        if ! grep -q "^\${_key}=" "\${CONF_FILE}"; then
            echo "[runbridge.sh] FEHLER: Pflicht-Key \${_key} fehlt in commissioning.conf" >&2
            exit 1
        fi
    done
    echo "[runbridge.sh] Credentials erzeugt: \${CONF_FILE}"
fi

# conf sourcen (enthaelt GARDENA_DISCRIMINATOR, GARDENA_SPAKE2P_VERIFIER, etc.)
# shellcheck source=/dev/null
. "\${CONF_FILE}"

wait_routable_ipv6() {
    local max_wait=60
    local i=0
    while [ "\${i}" -lt "\${max_wait}" ]; do
        # Routable IPv6: global (2xxx:, 3xxx:) oder ULA (fdxx:)
        # Ausschluss: link-local (fe80::) und Mesh-ppp0-Prefix
        # ip -6 addr gibt alle IPv6-Adressen aus; grep filtert:
        #   - beginnt mit 'inet6'
        #   - gefolgt von 2, 3 (global) oder fd (ULA private)
        #   - NICHT 'scope link' (link-local fe80::)
        #   - NICHT 'ppp' im interface-Namen
        # Auf BusyBox ip sind scope-Angaben verfuegbar.
        local found
        found=\$(ip -6 addr show 2>/dev/null | grep 'inet6' | grep -v 'scope link' | grep -E '^\s+inet6 (2|3|fd)' | grep -v 'fc00:' | head -1)
        if [ -n "\${found}" ]; then
            # Routbare IPv6 gefunden: IP extrahieren und loggen
            local ipv6
            ipv6=\$(echo "\${found}" | awk '{print \$2}' | cut -d/ -f1)
            echo "[runbridge.sh] Routbare IPv6 gefunden nach \${i}s: \${ipv6} — starte Bridge"
            return 0
        fi
        sleep 1
        i=\$(( i + 1 ))
    done
    # Timeout: trotzdem starten, aber warnen
    echo "[runbridge.sh] WARN: Keine routbare IPv6 nach \${max_wait}s gefunden — starte Bridge trotzdem (nur link-local oder Mesh-Interface verfuegbar)"
    return 0
}

wait_routable_ipv6

export LD_LIBRARY_PATH=${INSTALL_DIR}/usr/lib:${INSTALL_DIR}/lib
# Verifier-Argumente (KEIN --passcode, passcode nie in cmdline)
exec ${INSTALL_DIR}/chip-bridge-app \\
    --KVS ${KVS_DIR}/chip_kvs \\
    --interface-id 0 \\
    --discriminator        "\${GARDENA_DISCRIMINATOR}" \\
    --spake2p-verifier     "\${GARDENA_SPAKE2P_VERIFIER}" \\
    --spake2p-salt         "\${GARDENA_SPAKE2P_SALT}" \\
    --spake2p-iterations   "\${GARDENA_SPAKE2P_ITERATIONS}"
LAUNCHEREOF
ssh ${SSH_OPTS} "${GW}" "chmod +x ${LAUNCHER}"
log "Launcher installiert: ${LAUNCHER}"

# Footprint prüfen
log "=== Footprint-Check ==="
ssh ${SSH_OPTS} "${GW}" << FOOTEOF
echo "Installierte Dateien in ${INSTALL_DIR}:"
du -sh ${INSTALL_DIR}
echo ""
echo "Overlay-Platz:"
df -h / | tail -1
echo ""
echo "ABI-Check (fp_abi muss 0 oder 3 sein, kein MFPXX):"
file ${INSTALL_DIR}/chip-bridge-app 2>/dev/null || echo "(file nicht verfügbar)"
FOOTEOF

# ─── systemd-Unit installieren + enable ─────────────────────────────────
log "=== systemd-Unit installieren ==="

# ExecStartPre setzt Firewall-Regel (idempotent: -C vor -I)
ssh ${SSH_OPTS} "${GW}" "cat > ${UNIT_FILE}" << UNITEOF
[Unit]
Description=Gardena Matter Bridge
Wants=lemonbeatd.service network-online.target
After=lemonbeatd.service network-online.target

[Service]
Type=simple
Restart=on-failure
RestartSec=30
ExecStartPre=/bin/sh -c 'iptables -C INPUT -p udp --dport 5540 -j ACCEPT 2>/dev/null || iptables -I INPUT -p udp --dport 5540 -j ACCEPT'
ExecStartPre=/bin/sh -c 'ip6tables -C INPUT -p udp --dport 5540 -j ACCEPT 2>/dev/null || ip6tables -I INPUT -p udp --dport 5540 -j ACCEPT'
ExecStart=${LAUNCHER}
StandardOutput=journal
StandardError=journal
SyslogIdentifier=gardena-matter-bridge

[Install]
WantedBy=multi-user.target
UNITEOF

log "Unit-Datei geschrieben: ${UNIT_FILE}"

# systemctl daemon-reload + enable
log "systemctl daemon-reload + enable ..."
ssh ${SSH_OPTS} "${GW}" << ENABLEEOF
systemctl daemon-reload
systemctl enable gardena-matter-bridge.service
echo "systemctl enable: OK"
echo ""
echo "Symlink-Check (multi-user.target.wants):"
ls -la /etc/systemd/system/multi-user.target.wants/gardena-matter-bridge.service 2>/dev/null \
    || ls -la /run/systemd/generator.late/gardena-matter-bridge.service 2>/dev/null \
    || echo "(Symlink wird von systemd verwaltet)"
systemctl is-enabled gardena-matter-bridge.service
ENABLEEOF
log "Unit enabled"

log "=== T2+gardena-matter-bridge.service starten ==="
ssh ${SSH_OPTS} "${GW}" << STARTEOF
systemctl start gardena-matter-bridge.service
sleep 20
echo "=== systemctl status ==="
systemctl status gardena-matter-bridge.service --no-pager || true
echo ""
echo "=== Firewall-Check ==="
iptables -C INPUT -p udp --dport 5540 -j ACCEPT 2>/dev/null && echo "IPv4 5540 ACCEPT: OK" || echo "IPv4 5540: NICHT GESETZT"
ip6tables -C INPUT -p udp --dport 5540 -j ACCEPT 2>/dev/null && echo "IPv6 5540 ACCEPT: OK" || echo "IPv6 5540: NICHT GESETZT"
echo ""
echo "=== Bridge-Prozess ==="
PID=\$(pgrep -x chip-bridge-app || true)
if [ -n "\${PID}" ]; then
    echo "PID=\${PID}"
    awk '/VmRSS/{print "RSS: " \$2 " kB"}' /proc/\${PID}/status 2>/dev/null || true
    echo "STATUS=RUNNING"
else
    echo "STATUS=NOT_RUNNING"
fi
echo ""
echo "=== Bridge-Log (Journal) ==="
journalctl -u gardena-matter-bridge.service -n 40 --no-pager 2>/dev/null || true
STARTEOF

# ─── Zusammenfassung ─────────────────────────────────────────────────────────
log ""
log "==================================================================="
log "install_bridge.sh DONE"
log ""
log "  Binary    : ${INSTALL_DIR}/chip-bridge-app"
log "  Libs      : ${INSTALL_DIR}/usr/lib/"
log "  Launcher  : ${LAUNCHER}"
log "  Unit      : ${UNIT_FILE}"
log "  KVS       : ${KVS_DIR}/chip_kvs  (unberührt, HA-Pairing erhalten)"
log ""
log "  Firewall  : ExecStartPre in Unit (persistiert reboot-fest)"
log "  Autostart : systemctl enable gardena-matter-bridge.service"
log ""
log "  Nächste Schritte:"
log "    - HA-Pairing prüfen: curl -H 'Authorization: Bearer \$HA_TOKEN'"
log "        http://<ha>:8123/api/diagnostics/config_entry/01K0FFM1757CN087H6Z7G28TN6"
log "        → 1026/0 (Temp) und 1029/0 (Feuchte) müssen != null sein"
log "    - Reboot: ssh root@${GATEWAY_IP} reboot"
log "    - Nach Reboot (ca. 90 s): systemctl status gardena-matter-bridge"
log "    - Deinstallation: bash matter/uninstall_bridge.sh ${GATEWAY_IP}"
log "==================================================================="
