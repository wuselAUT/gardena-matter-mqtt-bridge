"""native_deploy.py — Deploy via native ssh.exe/scp.exe (Windows built-in tools).

Ports the deploy sequence from the install scripts to Python. Calls ssh/scp
via subprocess — no bash, no paramiko, no third-party packages. Runs on
Windows, macOS, and Linux.

The REMOTE command strings (what runs on the gateway) are taken verbatim from
the install scripts. Only the LOCAL orchestration (which scp/ssh calls in which
order) is implemented in Python.

Hard constraints:
  - KVS /var/lib/gardena-matter/chip_kvs is NEVER wiped (preserves Matter pairing).
  - lemonbeatd / cloudadapter are NOT touched (vendor services must remain running).
  - EVERY ssh/scp call gets -i <key> + -o IdentitiesOnly=yes
    (without this, the gateway's SSH server may reject after too many key attempts
    from a loaded ssh-agent, causing spurious authentication failures).
  - Platform-neutral: Windows -> System32\\OpenSSH\\ssh.exe preferred; otherwise PATH.

EN: Deploy via native ssh/scp subprocess calls. Remote command strings taken
    verbatim from the install scripts.
DE: Deploy via native ssh/scp-Subprocess-Aufrufe. Remote-Befehls-Strings
    VERBATIM aus den Install-Skripten uebernommen.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Callable, List, Optional, Sequence

# Timeout for SSH/SCP subprocesses (seconds). Generous for scp of a
# release bundle over LAN.
SSH_TIMEOUT_S = 300

# Target paths on the gateway (from install_bridge.sh)
INSTALL_DIR = "/usr/local/lib/gardena-matter"
LAUNCHER = f"{INSTALL_DIR}/runbridge.sh"
UNIT_FILE = "/etc/systemd/system/gardena-matter-bridge.service"
KVS_DIR = "/var/lib/gardena-matter"

# Web UI paths (from install_web_ui.sh)
WWW_DST = "/usr/share/gateway-config-interface/www"
ASSETS_DST = f"{WWW_DST}/assets"
ETC_DIR = "/etc/gardena-matter"
UNIT_DIR = "/etc/systemd/system"

# Restore paths (from install_restore.sh)
RESTORE_SRC = "/etc/gardena-matter/restore-src"
BRIDGE_DIR = INSTALL_DIR


# ---------------------------------------------------------------------------
# Platform-neutral tool resolution
# ---------------------------------------------------------------------------

def find_tool(name: str) -> Optional[str]:
    """Finds ssh/scp/ssh-keygen/curl on the current system.

    Windows: prefers fully-qualified path from %WINDIR%\\System32\\OpenSSH\\.
    macOS/Linux: searches via shutil.which (PATH).
    Returns None if the tool is not found.

    EN: Resolves ssh/scp/ssh-keygen/curl — prefers Windows System32\\OpenSSH on Windows.
    DE: Loest ssh/scp/ssh-keygen/curl auf — bevorzugt Windows System32\\OpenSSH auf Windows.
    """
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        openssh_dir = os.path.join(windir, "System32", "OpenSSH")
        # Prefer fully-qualified path (don't rely on PATH ordering)
        candidate = os.path.join(openssh_dir, name + ".exe")
        if os.path.isfile(candidate):
            return candidate
        # Fallback: curl often lives in System32 directly (not the OpenSSH subfolder)
        if name == "curl":
            candidate2 = os.path.join(windir, "System32", "curl.exe")
            if os.path.isfile(candidate2):
                return candidate2
    # Platform fallback: PATH
    return shutil.which(name)


def _require_tool(name: str) -> str:
    """Like find_tool, but raises RuntimeError if not found."""
    path = find_tool(name)
    if not path:
        raise RuntimeError(
            f"Tool '{name}' nicht gefunden. / Tool '{name}' not found."
        )
    return path


# ---------------------------------------------------------------------------
# Preflight check
# ---------------------------------------------------------------------------

PREFLIGHT_TOOLS = ("ssh", "scp", "ssh-keygen", "curl")

# Bilingual error message for missing OpenSSH client (Windows)
_OPENSSH_MISSING_MSG_EN = (
    "OpenSSH client tools (ssh/scp/ssh-keygen) are not available.\n"
    "To install on Windows: Settings → Apps → Optional features → "
    "Add a feature → 'OpenSSH Client' (a built-in Windows component, no third-party software).\n"
    "curl is usually pre-installed on Windows 10/11."
)
_OPENSSH_MISSING_MSG_DE = (
    "OpenSSH-Client-Tools (ssh/scp/ssh-keygen) sind nicht verfuegbar.\n"
    "Installation unter Windows: Einstellungen → Apps → Optionale Features → "
    "Feature hinzufuegen → 'OpenSSH-Client' (ein Windows-Bordmittel, kein Fremdpaket).\n"
    "curl ist auf Windows 10/11 normalerweise vorinstalliert."
)


class PreflightError(Exception):
    """Raised when a required tool is missing."""


def preflight_check() -> None:
    """Checks that ssh/scp/ssh-keygen/curl are resolvable.

    If a tool is missing -> PreflightError with bilingual message (no crash).
    Should be called at startup in cli.py.

    EN: Checks that ssh/scp/ssh-keygen/curl are resolvable. Raises PreflightError on missing.
    DE: Prueft ob ssh/scp/ssh-keygen/curl gefunden werden. Wirft PreflightError bei Fehlen.
    """
    missing = [t for t in PREFLIGHT_TOOLS if find_tool(t) is None]
    if missing:
        missing_str = ", ".join(missing)
        raise PreflightError(
            f"Missing tools / Fehlende Tools: {missing_str}\n\n"
            f"{_OPENSSH_MISSING_MSG_EN}\n\n"
            f"{_OPENSSH_MISSING_MSG_DE}"
        )


# ---------------------------------------------------------------------------
# SSH/SCP options (mandatory options to avoid gateway SSH server rejections)
# ---------------------------------------------------------------------------

def _ssh_opts(private_key_path: str) -> List[str]:
    """Returns the mandatory SSH options as a list.

    Every ssh/scp call gets:
      -i <key>
      -o IdentitiesOnly=yes  <- use only our key so only one key is offered
                                (avoids the SSH server rejecting after too many
                                key attempts from a loaded ssh-agent)
      -o StrictHostKeyChecking=accept-new
      -o BatchMode=yes
      -o ConnectTimeout=15

    EN: Returns mandatory SSH options list. IdentitiesOnly=yes ensures only our
        key is offered — prevents the gateway from rejecting after too many
        attempts when Windows ssh.exe has a loaded ssh-agent.
    DE: Liefert Pflicht-SSH-Optionsliste. IdentitiesOnly=yes verhindert, dass
        der Gateway zu viele Keys angeboten bekommt.
    """
    return [
        "-i", private_key_path,
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=15",
    ]


# ---------------------------------------------------------------------------
# Runner type (injectable for tests)
# ---------------------------------------------------------------------------

# SubprocessRunner: (cmd: List[str]) -> int (returncode)
SubprocessRunner = Callable[[List[str]], int]


def real_ssh_runner(cmd: List[str]) -> int:
    """Real runner: executes an ssh/scp command and returns the exit code."""
    try:
        proc = subprocess.run(  # noqa: S603
            cmd,
            timeout=SSH_TIMEOUT_S,
            check=False,
        )
        return proc.returncode
    except subprocess.TimeoutExpired:
        return 124  # conventional for timeout
    except FileNotFoundError:
        return 127  # tool not found


# ---------------------------------------------------------------------------
# Helper: build SSH command / SCP command
# ---------------------------------------------------------------------------

def _ssh_cmd(
    ssh_bin: str,
    private_key_path: str,
    host: str,
    remote_cmd: str,
) -> List[str]:
    """Builds an ssh command with the mandatory options."""
    return [ssh_bin] + _ssh_opts(private_key_path) + [f"root@{host}", remote_cmd]


def _scp_cmd(
    scp_bin: str,
    private_key_path: str,
    local_paths: Sequence[str],
    remote_dest: str,
    host: str,
) -> List[str]:
    """Builds an scp command with the mandatory options.

    scp -O: forces legacy SCP protocol (compatible with older dropbear).
    """
    return (
        [scp_bin, "-O"]
        + _ssh_opts(private_key_path)
        + list(local_paths)
        + [f"root@{host}:{remote_dest}"]
    )


def _run(runner: SubprocessRunner, cmd: List[str], desc: str) -> None:
    """Executes a command; raises RuntimeError on non-zero exit."""
    rc = runner(cmd)
    if rc != 0:
        raise RuntimeError(
            f"Schritt fehlgeschlagen (Exit {rc}): {desc}\n"
            f"Step failed (exit {rc}): {desc}"
        )


# ---------------------------------------------------------------------------
# install_bridge (ported from install_bridge.sh)
# ---------------------------------------------------------------------------

# Remote strings taken verbatim from install_bridge.sh
# (sections that run via ssh on the gateway).

_REMOTE_STOP_SERVICE = r"""
if systemctl is-active gardena-matter-bridge.service >/dev/null 2>&1; then
    systemctl stop gardena-matter-bridge.service
    echo "gardena-matter-bridge.service gestoppt"
    sleep 2
fi
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
"""

_REMOTE_LIB_CLEANUP = r"""
echo "df-before: $(df -h /usr/local 2>/dev/null | tail -1)"
rm -rf "/usr/local/lib/gardena-matter/usr/lib" "/usr/local/lib/gardena-matter/lib"
echo "cleanup: lib dirs removed"
echo "df-after: $(df -h /usr/local 2>/dev/null | tail -1)"
"""

# Unpack libs template (INSTALL_DIR substituted at call time)
_REMOTE_UNPACK_LIBS_TEMPLATE = (
    "cd {install_dir}\n"
    "tar xzf /tmp/matter_libs_install.tar.gz\n"
    "rm -f /tmp/matter_libs_install.tar.gz\n"
    "find {install_dir} -name '*.so*' | while read so; do\n"
    "    target=\"{install_dir}/usr/lib/$(basename \"${{so}}\")\"\n"
    "    if [ \"${{so}}\" != \"${{target}}\" ]; then\n"
    "        cp -L \"${{so}}\" \"${{target}}\" 2>/dev/null || true\n"
    "    fi\n"
    "done\n"
    "echo 'Libs in {install_dir}:'\n"
    "ls -lh {install_dir}/usr/lib/ 2>/dev/null || echo '(leer)'\n"
)

# Launcher script (runbridge.sh) — taken verbatim from install_bridge.sh.
# Written via ssh "cat > {launcher}" to the gateway.
#
# Note on shell variables: Python format placeholders ({install_dir}, {kvs_dir})
# are substituted locally via .format(). All shell variables in the script
# (e.g. $CONF_FILE, $i) are double-braced (${{…}}) so Python's format()
# passes them through unchanged and they expand as real shell variables on the gateway.
#
# On first start, generates unique commissioning credentials (Spake2+ verifier).
# The passcode is never stored or passed to the long-running bridge process.
# Before starting, waits for a routable IPv6 (global/ULA, not link-local,
# not Mesh ppp0) on the broadcast LAN interface (max 60 seconds).
#
# EN: Launcher script — commissioning credential generation + IPv6 wait + exec.
# DE: Launcher-Skript — Commissioning-Credential-Erzeugung + IPv6-Wait + exec.
_REMOTE_WRITE_LAUNCHER_TEMPLATE = r"""cat > {launcher} << 'LAUNCHEREOF'
#!/bin/sh
# runbridge.sh — Gardena Matter Bridge Launcher (persistent)
# Installed in {install_dir} (persistent overlay, survives reboot)
#
# On first start, generates unique commissioning credentials (Spake2+ verifier):
#   chip-bridge-app --generate-commissioning writes the conf file.
#   The conf is then sourced and the verifier (NOT the passcode) is passed as argument.
#   Idempotent: conf is only generated if it is missing.
#
# EN: On first start, generates unique commissioning credentials (Spake2+ verifier).
#     Passcode is never stored or passed to the long-running bridge process.
# DE: Beim Erststart werden einmalig eindeutige Credentials erzeugt (Spake2+-Verifier).
#     Der Passcode wird nie gespeichert oder an den laufenden Bridge-Prozess uebergeben.
#
# Before starting, waits for a routable IPv6 (global/ULA, not link-local,
# not Mesh ppp0) on the broadcast LAN interface.
# Bounded wait loop: max 60 seconds, poll 1s.
# On timeout: start anyway + WARN log (robust operation).
#
# EN: Wait for a routable IPv6 (global/ULA, not link-local, not Mesh ppp0)
#     on the broadcast LAN interface before starting chip-bridge-app.
# DE: Vor dem Start auf eine routbare IPv6 warten (max. 60s).

CONF_FILE="{kvs_dir}/commissioning.conf"

# Generate commissioning credentials if conf is missing
if [ ! -f "${{CONF_FILE}}" ]; then
    echo "[runbridge.sh] commissioning.conf fehlt — erzeuge Credentials..."
    # Export LD_LIBRARY_PATH before --generate-commissioning so chip-bridge-app
    # can find libstdc++.so.6 (without this, it exits with a shared-library error).
    export LD_LIBRARY_PATH={install_dir}/usr/lib:{install_dir}/lib
    {install_dir}/chip-bridge-app --generate-commissioning "${{CONF_FILE}}"
    gen_rc=$?
    # Check exit code; fail-closed on error (no unconditional 'generated' message).
    if [ "${{gen_rc}}" -ne 0 ]; then
        echo "[runbridge.sh] FEHLER: --generate-commissioning fehlgeschlagen (Exit ${{gen_rc}})" >&2
        exit 1
    fi
    # Verify that conf exists and contains required keys.
    if [ ! -f "${{CONF_FILE}}" ]; then
        echo "[runbridge.sh] FEHLER: commissioning.conf wurde nicht erzeugt" >&2
        exit 1
    fi
    for _key in GARDENA_DISCRIMINATOR GARDENA_SPAKE2P_VERIFIER GARDENA_SPAKE2P_SALT GARDENA_SPAKE2P_ITERATIONS; do
        if ! grep -q "^${{_key}}=" "${{CONF_FILE}}"; then
            echo "[runbridge.sh] FEHLER: Pflicht-Key ${{_key}} fehlt in commissioning.conf" >&2
            exit 1
        fi
    done
    echo "[runbridge.sh] Credentials erzeugt: ${{CONF_FILE}}"
fi

# Source conf (contains GARDENA_DISCRIMINATOR, GARDENA_SPAKE2P_VERIFIER, etc.)
# shellcheck source=/dev/null
. "${{CONF_FILE}}"

wait_routable_ipv6() {{
    local max_wait=60
    local i=0
    while [ "${{i}}" -lt "${{max_wait}}" ]; do
        # Routable IPv6: global (2xxx:, 3xxx:) or ULA (fdxx:)
        # Exclude: link-local (fe80::) and Mesh-ppp0 prefix
        # ip -6 addr shows all IPv6 addresses; grep filters:
        #   - starts with 'inet6'
        #   - followed by 2, 3 (global) or fd (ULA private)
        #   - NOT 'scope link' (link-local fe80::)
        #   - NOT 'ppp' in the interface name
        # BusyBox ip provides scope annotations.
        local found
        found=$(ip -6 addr show 2>/dev/null | grep 'inet6' | grep -v 'scope link' | grep -E '^\s+inet6 (2|3|fd)' | grep -v 'fc00:' | head -1)
        if [ -n "${{found}}" ]; then
            # Routable IPv6 found: extract and log IP
            local ipv6
            ipv6=$(echo "${{found}}" | awk '{{print $2}}' | cut -d/ -f1)
            echo "[runbridge.sh] Routbare IPv6 gefunden nach ${{i}}s: ${{ipv6}} — starte Bridge"
            return 0
        fi
        sleep 1
        i=$(( i + 1 ))
    done
    # Timeout: start anyway but warn
    echo "[runbridge.sh] WARN: Keine routbare IPv6 nach ${{max_wait}}s gefunden — starte Bridge trotzdem (nur link-local oder Mesh-Interface verfuegbar)"
    return 0
}}

wait_routable_ipv6

export LD_LIBRARY_PATH={install_dir}/usr/lib:{install_dir}/lib
# Pass verifier arguments (NOT --passcode; passcode never in command line)
exec {install_dir}/chip-bridge-app \
    --KVS {kvs_dir}/chip_kvs \
    --interface-id 0 \
    --discriminator        "${{GARDENA_DISCRIMINATOR}}" \
    --spake2p-verifier     "${{GARDENA_SPAKE2P_VERIFIER}}" \
    --spake2p-salt         "${{GARDENA_SPAKE2P_SALT}}" \
    --spake2p-iterations   "${{GARDENA_SPAKE2P_ITERATIONS}}"
LAUNCHEREOF
chmod +x {launcher}
echo "Launcher installiert: {launcher}"
"""

# KVS ensure template — KVS is NEVER wiped (preserves Matter pairing)
_REMOTE_KVS_ENSURE_TEMPLATE = (
    "mkdir -p {kvs_dir}\n"
    "if [ -f \"{kvs_dir}/chip_kvs\" ]; then\n"
    "    echo \"KVS existiert bereits: $(ls -lh {kvs_dir}/chip_kvs)\"\n"
    "    echo \"KVS BLEIBT UNANGETASTET — HA-Pairing erhalten\"\n"
    "else\n"
    "    echo \"KVS-Datei noch nicht vorhanden (wird beim ersten Start angelegt)\"\n"
    "fi\n"
)

# systemd unit template — taken verbatim from install_bridge.sh
_REMOTE_WRITE_UNIT_TEMPLATE = (
    "cat > {unit_file} << 'UNITEOF_INNER'\n"
    "[Unit]\n"
    "Description=Gardena Matter Bridge\n"
    "Wants=lemonbeatd.service network-online.target\n"
    "After=lemonbeatd.service network-online.target\n"
    "\n"
    "[Service]\n"
    "Type=simple\n"
    "Restart=on-failure\n"
    "RestartSec=30\n"
    "ExecStartPre=/bin/sh -c 'iptables -C INPUT -p udp --dport 5540 -j ACCEPT 2>/dev/null || iptables -I INPUT -p udp --dport 5540 -j ACCEPT'\n"
    "ExecStartPre=/bin/sh -c 'ip6tables -C INPUT -p udp --dport 5540 -j ACCEPT 2>/dev/null || ip6tables -I INPUT -p udp --dport 5540 -j ACCEPT'\n"
    "ExecStart={launcher}\n"
    "StandardOutput=journal\n"
    "StandardError=journal\n"
    "SyslogIdentifier=gardena-matter-bridge\n"
    "\n"
    "[Install]\n"
    "WantedBy=multi-user.target\n"
    "UNITEOF_INNER\n"
    "echo 'Unit-Datei geschrieben: {unit_file}'\n"
)

# Enable service — taken verbatim from install_bridge.sh
_REMOTE_ENABLE_SERVICE = (
    "systemctl daemon-reload\n"
    "systemctl enable gardena-matter-bridge.service\n"
    "echo 'systemctl enable: OK'\n"
    "systemctl is-enabled gardena-matter-bridge.service\n"
)

# Start service + firewall check — taken verbatim from install_bridge.sh
_REMOTE_START_SERVICE = (
    "systemctl start gardena-matter-bridge.service\n"
    "sleep 20\n"
    "echo '=== systemctl status ==='\n"
    "systemctl status gardena-matter-bridge.service --no-pager || true\n"
    "echo ''\n"
    "echo '=== Firewall-Check ==='\n"
    "iptables -C INPUT -p udp --dport 5540 -j ACCEPT 2>/dev/null && echo 'IPv4 5540 ACCEPT: OK' || echo 'IPv4 5540: NICHT GESETZT'\n"
    "ip6tables -C INPUT -p udp --dport 5540 -j ACCEPT 2>/dev/null && echo 'IPv6 5540 ACCEPT: OK' || echo 'IPv6 5540: NICHT GESETZT'\n"
    "echo ''\n"
    "echo '=== Bridge-Prozess ==='\n"
    "PID=$(pgrep -x chip-bridge-app || true)\n"
    "if [ -n \"${PID}\" ]; then\n"
    "    echo \"PID=${PID}\"\n"
    "    awk '/VmRSS/{print \"RSS: \" $2 \" kB\"}' /proc/${PID}/status 2>/dev/null || true\n"
    "    echo 'STATUS=RUNNING'\n"
    "else\n"
    "    echo 'STATUS=NOT_RUNNING'\n"
    "fi\n"
    "echo ''\n"
    "echo '=== Bridge-Log (Journal) ==='\n"
    "journalctl -u gardena-matter-bridge.service -n 40 --no-pager 2>/dev/null || true\n"
)


def install_bridge(
    host: str,
    private_key_path: str,
    binary_path: str,
    libs_tgz_path: str,
    *,
    runner: SubprocessRunner = real_ssh_runner,
) -> None:
    """Ports install_bridge.sh to Python.

    Steps (order is binding):
      1. scp: Binary -> :/usr/local/lib/gardena-matter/chip-bridge-app
      2. scp: Libs-tgz -> :/tmp/matter_libs_install.tar.gz
      3. ssh: Stop service (if active), lib cleanup, create dirs,
              unpack libs, ensure KVS (NEVER wipe),
              write unit, daemon-reload/enable/start, firewall check.

    KVS /var/lib/gardena-matter/chip_kvs is NEVER wiped (preserves Matter pairing).
    lemonbeatd/cloudadapter are NOT touched (vendor services must remain running).

    EN: Ports install_bridge.sh to Python. Remote command strings taken verbatim.
    DE: Portiert install_bridge.sh nach Python. Remote-Strings VERBATIM uebernommen.
    """
    ssh_bin = _require_tool("ssh")
    scp_bin = _require_tool("scp")

    # Create target directories BEFORE scp so scp finds the destination directory.
    # On a factory-fresh gateway, /usr/local/lib/gardena-matter/ does not exist;
    # scp does not create parent directories.
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            f"mkdir -p {INSTALL_DIR}/lib {INSTALL_DIR}/usr/lib",
        ),
        "ssh: Verzeichnisse anlegen (VOR scp)",
    )

    # 1. Binary scp (atomic: upload to .tmp, then mv)
    _run(
        runner,
        _scp_cmd(scp_bin, private_key_path, [binary_path], f"{INSTALL_DIR}/chip-bridge-app.tmp", host),
        f"scp Binary -> {INSTALL_DIR}/chip-bridge-app.tmp",
    )
    # chmod + atomic mv (atomic with respect to a running process)
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            f"mv -f {INSTALL_DIR}/chip-bridge-app.tmp {INSTALL_DIR}/chip-bridge-app && "
            f"chmod +x {INSTALL_DIR}/chip-bridge-app",
        ),
        f"chmod+mv Binary -> {INSTALL_DIR}/chip-bridge-app",
    )

    # 2. Libs-tgz scp
    _run(
        runner,
        _scp_cmd(scp_bin, private_key_path, [libs_tgz_path], "/tmp/matter_libs_install.tar.gz", host),
        "scp Libs-tgz -> /tmp/matter_libs_install.tar.gz",
    )

    # 3. SSH: stop service
    _run(
        runner,
        _ssh_cmd(ssh_bin, private_key_path, host, _REMOTE_STOP_SERVICE),
        "ssh: Service stoppen",
    )

    # 4. SSH: lib cleanup
    _run(
        runner,
        _ssh_cmd(ssh_bin, private_key_path, host, _REMOTE_LIB_CLEANUP),
        "ssh: Lib-Cleanup",
    )

    # 5. SSH: unpack libs
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            _REMOTE_UNPACK_LIBS_TEMPLATE.format(install_dir=INSTALL_DIR),
        ),
        "ssh: Libs entpacken",
    )

    # 6. SSH: ensure KVS directory (NEVER wipe existing KVS)
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            _REMOTE_KVS_ENSURE_TEMPLATE.format(kvs_dir=KVS_DIR),
        ),
        "ssh: KVS sicherstellen (NICHT wipen)",
    )

    # 7. Write launcher runbridge.sh BEFORE systemctl start.
    # Content taken verbatim from install_bridge.sh LAUNCHEREOF heredoc.
    # Includes commissioning credential generation (--generate-commissioning,
    # Spake2+), IPv6 wait loop, and exec chip-bridge-app with verifier arguments.
    # Without this step, ExecStart points to a non-existent file ->
    # service start fails + no Matter pairing on a fresh gateway.
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            _REMOTE_WRITE_LAUNCHER_TEMPLATE.format(
                launcher=LAUNCHER,
                install_dir=INSTALL_DIR,
                kvs_dir=KVS_DIR,
            ),
        ),
        f"ssh: Launcher runbridge.sh schreiben -> {LAUNCHER}",
    )

    # 8. SSH: write systemd unit (taken verbatim from install_bridge.sh UNITEOF)
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            _REMOTE_WRITE_UNIT_TEMPLATE.format(unit_file=UNIT_FILE, launcher=LAUNCHER),
        ),
        f"ssh: Unit schreiben {UNIT_FILE}",
    )

    # 9. SSH: daemon-reload + enable
    _run(
        runner,
        _ssh_cmd(ssh_bin, private_key_path, host, _REMOTE_ENABLE_SERVICE),
        "ssh: daemon-reload + enable",
    )

    # 10. SSH: start + firewall check
    _run(
        runner,
        _ssh_cmd(ssh_bin, private_key_path, host, _REMOTE_START_SERVICE),
        "ssh: start + Firewall-Check",
    )


# ---------------------------------------------------------------------------
# install_web_ui (ported from install_web_ui.sh)
# ---------------------------------------------------------------------------

# Remote strings taken verbatim from install_web_ui.sh

_REMOTE_WEB_CLEANUP = r"""
for u in gardena-matter-toggle.socket gardena-matter-toggle.service; do
    if systemctl is-active --quiet "$u" 2>/dev/null; then
        systemctl stop "$u" && echo "Stopped: $u"
    fi
done
for u in gardena-matter-web.socket gardena-matter-web.service; do
    if systemctl is-active --quiet "$u" 2>/dev/null; then
        systemctl stop "$u" && echo "Stopped: $u"
    fi
    if systemctl is-enabled --quiet "$u" 2>/dev/null; then
        systemctl disable "$u" && echo "Disabled: $u"
    fi
done
if [ -f "/usr/share/gateway-config-interface/www/matter.html" ]; then
    rm -f "/usr/share/gateway-config-interface/www/matter.html"
    echo "Entfernt: www/matter.html"
fi
echo "Bereinigung abgeschlossen"
"""

_REMOTE_WEB_DIRS_TEMPLATE = (
    "mkdir -p {etc_dir} && mkdir -p {assets_dst}"
)

# systemctl setup (taken verbatim from install_web_ui.sh)
_REMOTE_WEB_SYSTEMCTL = r"""
systemctl daemon-reload

systemctl enable gardena-matter-toggle.socket
systemctl start  gardena-matter-toggle.socket
echo "Toggle-Socket: gestartet"

systemctl enable gardena-matter-status.timer
systemctl start  gardena-matter-status.timer
echo "Status-Timer: gestartet"

systemctl start gardena-matter-status.service
echo "Status-JSON: initial erzeugt"

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
"""

# File installation command for /assets/ (taken verbatim from install_web_ui.sh)
_REMOTE_WEB_ASSETS_COPY_TEMPLATE = (
    "cp {etc_dir}/matter.html    {assets_dst}/matter.html\n"
    "cp {etc_dir}/qrcode.min.js  {assets_dst}/qrcode.min.js\n"
    "chmod 644 {assets_dst}/matter.html\n"
    "chmod 644 {assets_dst}/qrcode.min.js\n"
    "echo 'matter.html + qrcode.min.js in {assets_dst}/ installiert'\n"
)

_REMOTE_WEB_PERMS_TEMPLATE = (
    "chmod +x {etc_dir}/update-matter-status.sh\n"
    "chmod 644 {etc_dir}/matter.html\n"
    "chmod 644 {etc_dir}/qrcode.min.js\n"
)


def install_web_ui(
    host: str,
    private_key_path: str,
    web_ui_dir: str,
    *,
    addon_version: str = "unknown",
    build_version: str = "dev",
    runner: SubprocessRunner = real_ssh_runner,
) -> None:
    """Ports install_web_ui.sh to Python.

    Steps:
      1. ssh: Deactivate old services (cleanup)
      2. ssh: Create directories
      3. scp: gardena-toggle -> /etc/gardena-matter/gardena-toggle.new (atomic)
      4. ssh: mv + chmod
      5. scp: update-matter-status.sh, qrcode.min.js -> /etc/gardena-matter/
      6. scp: matter.html (with __ADDON_VERSION__/__BUILD_VERSION__ substituted) -> /etc/gardena-matter/
      7. ssh: set permissions
      8. ssh: populate /assets/ (cp from /etc/gardena-matter/)
      9. scp: systemd units -> /etc/systemd/system/
     10. ssh: systemctl setup

    Placeholder substitution for matter.html (__ADDON_VERSION__, __BUILD_VERSION__)
    is done locally in Python (string.replace) before scp, using the provided
    addon_version and build_version arguments.

    EN: Ports install_web_ui.sh. Placeholder substitution done in Python.
    DE: Portiert install_web_ui.sh. Platzhalter-Ersetzung in Python.
    """
    import tempfile

    ssh_bin = _require_tool("ssh")
    scp_bin = _require_tool("scp")

    # 1. Deactivate old services (taken verbatim from install_web_ui.sh CLEANUP_EOF)
    _run(
        runner,
        _ssh_cmd(ssh_bin, private_key_path, host, _REMOTE_WEB_CLEANUP),
        "ssh: Web-UI Cleanup (Dienste stoppen)",
    )

    # 2. Create directories
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            _REMOTE_WEB_DIRS_TEMPLATE.format(etc_dir=ETC_DIR, assets_dst=ASSETS_DST),
        ),
        "ssh: Web-UI Verzeichnisse anlegen",
    )

    # 3. gardena-toggle: atomic via .new + mv
    toggle_src = os.path.join(web_ui_dir, "gardena-toggle")
    _run(
        runner,
        _scp_cmd(scp_bin, private_key_path, [toggle_src], f"{ETC_DIR}/gardena-toggle.new", host),
        f"scp gardena-toggle -> {ETC_DIR}/gardena-toggle.new",
    )
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            f"mv -f {ETC_DIR}/gardena-toggle.new {ETC_DIR}/gardena-toggle && chmod +x {ETC_DIR}/gardena-toggle",
        ),
        "ssh: mv + chmod gardena-toggle",
    )

    # 4. update-matter-status.sh + qrcode.min.js scp
    _run(
        runner,
        _scp_cmd(
            scp_bin, private_key_path,
            [
                os.path.join(web_ui_dir, "update-matter-status.sh"),
                os.path.join(web_ui_dir, "qrcode.min.js"),
            ],
            f"{ETC_DIR}/",
            host,
        ),
        "scp update-matter-status.sh + qrcode.min.js",
    )

    # 5. matter.html: substitute placeholders locally -> temporary file -> scp
    matter_html_src = os.path.join(web_ui_dir, "matter.html")
    with open(matter_html_src, encoding="utf-8") as fh:
        html_content = fh.read()
    html_content = html_content.replace("__ADDON_VERSION__", addon_version)
    html_content = html_content.replace("__BUILD_VERSION__", build_version)

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".html", delete=False, prefix="matter_"
    ) as tmp_html:
        tmp_html.write(html_content)
        tmp_html_path = tmp_html.name

    try:
        _run(
            runner,
            _scp_cmd(scp_bin, private_key_path, [tmp_html_path], f"{ETC_DIR}/matter.html", host),
            f"scp matter.html (mit Versionen) -> {ETC_DIR}/matter.html",
        )
    finally:
        try:
            os.unlink(tmp_html_path)
        except Exception:  # noqa: BLE001
            pass

    # 6. Set permissions
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            _REMOTE_WEB_PERMS_TEMPLATE.format(etc_dir=ETC_DIR),
        ),
        "ssh: Web-UI Permissions",
    )

    # 7. Populate /assets/
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            _REMOTE_WEB_ASSETS_COPY_TEMPLATE.format(etc_dir=ETC_DIR, assets_dst=ASSETS_DST),
        ),
        "ssh: /assets/ befuellen",
    )

    # 8. scp systemd units (all 6 units from install_web_ui.sh)
    unit_files = [
        "gardena-matter-toggle.socket",
        "gardena-matter-toggle.service",
        "gardena-matter-status.service",
        "gardena-matter-status.timer",
        "gardena-matter-restore.service",
        "gardena-matter-restore.path",
    ]
    unit_srcs = [os.path.join(web_ui_dir, u) for u in unit_files]
    _run(
        runner,
        _scp_cmd(scp_bin, private_key_path, unit_srcs, f"{UNIT_DIR}/", host),
        "scp systemd-Units -> /etc/systemd/system/",
    )

    # 9. systemctl setup
    _run(
        runner,
        _ssh_cmd(ssh_bin, private_key_path, host, _REMOTE_WEB_SYSTEMCTL),
        "ssh: systemctl-Setup Web-UI",
    )


# ---------------------------------------------------------------------------
# install_restore (ported from install_restore.sh)
# ---------------------------------------------------------------------------

# Remote strings taken verbatim from install_restore.sh

_REMOTE_RESTORE_CHECK = r"""
OK=1
[ -f "/usr/local/lib/gardena-matter/chip-bridge-app" ] || { echo "ERROR: Bridge-Binary fehlt -- zuerst install_bridge.sh ausfuehren"; OK=0; }
[ -f "/usr/local/lib/gardena-matter/runbridge.sh" ]    || { echo "ERROR: runbridge.sh fehlt -- zuerst install_bridge.sh ausfuehren"; OK=0; }
[ -f "/etc/gardena-matter/gardena-toggle" ]            || { echo "ERROR: gardena-toggle fehlt -- zuerst install_web_ui.sh ausfuehren"; OK=0; }
[ -f "/etc/gardena-matter/matter.html" ]               || { echo "ERROR: matter.html fehlt -- zuerst install_web_ui.sh ausfuehren"; OK=0; }
[ -f "/etc/gardena-matter/qrcode.min.js" ]             || { echo "ERROR: qrcode.min.js fehlt -- zuerst install_web_ui.sh ausfuehren"; OK=0; }
[ ${OK} -eq 1 ] && echo "Voraussetzungen: OK" || exit 1
"""

_REMOTE_RESTORE_MKDIR_TEMPLATE = (
    "mkdir -p \"{restore_src}/usr-local-lib\"\n"
    "mkdir -p \"{restore_src}/systemd\"\n"
    "mkdir -p \"{restore_src}/assets\"\n"
    "echo \"Verzeichnisse angelegt: {restore_src}/\"\n"
)

_REMOTE_RESTORE_COPY_BIN_TEMPLATE = (
    "cp -p \"{bridge_dir}/chip-bridge-app\" \"{restore_src}/usr-local-lib/chip-bridge-app\"\n"
    "chmod 755 \"{restore_src}/usr-local-lib/chip-bridge-app\"\n"
    "cp -p \"{bridge_dir}/runbridge.sh\"    \"{restore_src}/usr-local-lib/runbridge.sh\"\n"
    "chmod 755 \"{restore_src}/usr-local-lib/runbridge.sh\"\n"
    "echo \"Binary + Launcher: echte Kopien OK\"\n"
    "echo \"Platz-Verbrauch restore-src/usr-local-lib: $(du -sh {restore_src}/usr-local-lib/ | cut -f1)\"\n"
)

_REMOTE_RESTORE_SYMLINKS_TEMPLATE = (
    "mkdir -p \"{restore_src}/usr-local-lib/lib\"\n"
    "mkdir -p \"{restore_src}/usr-local-lib/usr-lib\"\n"
    "for f in \"{bridge_dir}/lib/\"*; do\n"
    "    [ -e \"${{f}}\" ] || continue\n"
    "    ln -sf \"${{f}}\" \"{restore_src}/usr-local-lib/lib/$(basename ${{f}})\"\n"
    "    echo \"  lib/$(basename ${{f}}) -> symlink\"\n"
    "done\n"
    "for f in \"{bridge_dir}/usr/lib/\"*.so*; do\n"
    "    [ -e \"${{f}}\" ] || continue\n"
    "    bn=$(basename \"${{f}}\")\n"
    "    ln -sf \"${{f}}\" \"{restore_src}/usr-local-lib/usr-lib/${{bn}}\"\n"
    "    echo \"  usr-lib/${{bn}} -> symlink\"\n"
    "done\n"
    "echo \"Lib-Symlinks: OK\"\n"
)

_REMOTE_RESTORE_COPY_UNITS_TEMPLATE = (
    "for unit in \\\n"
    "    gardena-matter-bridge.service \\\n"
    "    gardena-matter-toggle.service \\\n"
    "    gardena-matter-toggle.socket \\\n"
    "    gardena-matter-status.service \\\n"
    "    gardena-matter-status.timer \\\n"
    "    gardena-matter-restore.path\n"
    "do\n"
    "    src=\"{unit_dir}/${{unit}}\"\n"
    "    if [ -f \"${{src}}\" ]; then\n"
    "        cp -p \"${{src}}\" \"{restore_src}/systemd/${{unit}}\"\n"
    "        chmod 644 \"{restore_src}/systemd/${{unit}}\"\n"
    "        echo \"  ${{unit}}: OK\"\n"
    "    else\n"
    "        echo \"  WARN: ${{unit}} nicht gefunden -- uebersprungen\"\n"
    "    fi\n"
    "done\n"
    "echo \"Platz-Verbrauch restore-src/systemd: $(du -sh {restore_src}/systemd/ | cut -f1)\"\n"
)

_REMOTE_RESTORE_COPY_ASSETS_TEMPLATE = (
    "cp -p \"{etc_dir}/matter.html\"   \"{restore_src}/assets/matter.html\"\n"
    "cp -p \"{etc_dir}/qrcode.min.js\" \"{restore_src}/assets/qrcode.min.js\"\n"
    "chmod 644 \"{restore_src}/assets/matter.html\"\n"
    "chmod 644 \"{restore_src}/assets/qrcode.min.js\"\n"
    "echo \"matter.html + qrcode.min.js: OK\"\n"
    "echo \"Platz-Verbrauch restore-src/assets: $(du -sh {restore_src}/assets/ | cut -f1)\"\n"
)

_REMOTE_RESTORE_ETC_SYMLINKS_TEMPLATE = (
    "mkdir -p \"{restore_src}/etc\"\n"
    "ln -sf \"{etc_dir}/gardena-toggle\"          \"{restore_src}/etc/gardena-toggle\"\n"
    "ln -sf \"{etc_dir}/update-matter-status.sh\" \"{restore_src}/etc/update-matter-status.sh\"\n"
    "echo \"gardena-toggle + update-matter-status.sh: Symlinks OK\"\n"
)

_REMOTE_RESTORE_ACTIVATE_TEMPLATE = (
    "systemctl reset-failed gardena-matter-restore.service 2>/dev/null || true\n"
    "systemctl reset-failed gardena-matter-restore.path    2>/dev/null || true\n"
    "systemctl daemon-reload\n"
    "systemctl enable gardena-matter-restore.service\n"
    "systemctl enable gardena-matter-restore.path\n"
    "echo \"Restore-Service aktiviert\"\n"
    "systemctl start gardena-matter-restore.service\n"
    "echo \"Erster Restore-Lauf abgeschlossen (erwartet: alle vorhanden)\"\n"
    "systemctl start gardena-matter-restore.path\n"
    "echo \"Path-Watch aktiv\"\n"
    "echo \"\"\n"
    "echo \"=== Restore-Service Status ===\"\n"
    "systemctl status gardena-matter-restore.service --no-pager || true\n"
)


def install_restore(
    host: str,
    private_key_path: str,
    web_ui_dir: str,
    *,
    runner: SubprocessRunner = real_ssh_runner,
) -> None:
    """Ports install_restore.sh to Python.

    Steps:
      1. ssh: Check prerequisites (bridge + web UI must be installed)
      2. ssh: Create restore-src/ directories
      3. ssh: Binary + runbridge.sh (real copies)
      4. ssh: Lib symlinks
      5. ssh: systemd unit copies
      6. ssh: Web UI file copies
      7. ssh: Executable symlinks
      8. scp: gardena-matter-restore.sh -> /etc/gardena-matter/
      9. scp: gardena-matter-restore.service + .path -> /etc/systemd/system/
     10. ssh: Activate restore service

    EN: Ports install_restore.sh to Python. Remote command strings taken verbatim.
    DE: Portiert install_restore.sh nach Python. Remote-Strings VERBATIM uebernommen.
    """
    ssh_bin = _require_tool("ssh")
    scp_bin = _require_tool("scp")

    # 1. Check prerequisites
    _run(
        runner,
        _ssh_cmd(ssh_bin, private_key_path, host, _REMOTE_RESTORE_CHECK),
        "ssh: Voraussetzungen pruefen",
    )

    # 2. Create directories
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            _REMOTE_RESTORE_MKDIR_TEMPLATE.format(restore_src=RESTORE_SRC),
        ),
        "ssh: restore-src/ Verzeichnisse anlegen",
    )

    # 3. Binary + launcher real copies
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            _REMOTE_RESTORE_COPY_BIN_TEMPLATE.format(bridge_dir=BRIDGE_DIR, restore_src=RESTORE_SRC),
        ),
        "ssh: Binary + Launcher -> restore-src/",
    )

    # 4. Lib symlinks
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            _REMOTE_RESTORE_SYMLINKS_TEMPLATE.format(bridge_dir=BRIDGE_DIR, restore_src=RESTORE_SRC),
        ),
        "ssh: Lib-Symlinks -> restore-src/",
    )

    # 5. systemd unit copies
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            _REMOTE_RESTORE_COPY_UNITS_TEMPLATE.format(unit_dir=UNIT_DIR, restore_src=RESTORE_SRC),
        ),
        "ssh: Units -> restore-src/systemd/",
    )

    # 6. Web UI file copies
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            _REMOTE_RESTORE_COPY_ASSETS_TEMPLATE.format(etc_dir=ETC_DIR, restore_src=RESTORE_SRC),
        ),
        "ssh: Web-UI -> restore-src/assets/",
    )

    # 7. Executable symlinks
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            _REMOTE_RESTORE_ETC_SYMLINKS_TEMPLATE.format(etc_dir=ETC_DIR, restore_src=RESTORE_SRC),
        ),
        "ssh: Executables-Symlinks -> restore-src/etc/",
    )

    # 8. Restore script scp
    restore_sh_src = os.path.join(web_ui_dir, "gardena-matter-restore.sh")
    _run(
        runner,
        _scp_cmd(
            scp_bin, private_key_path,
            [restore_sh_src],
            f"{ETC_DIR}/gardena-matter-restore.sh",
            host,
        ),
        f"scp gardena-matter-restore.sh -> {ETC_DIR}/",
    )
    _run(
        runner,
        _ssh_cmd(
            ssh_bin, private_key_path, host,
            f"chmod 755 {ETC_DIR}/gardena-matter-restore.sh",
        ),
        "ssh: chmod restore-script",
    )

    # 9. Restore service + path scp
    _run(
        runner,
        _scp_cmd(
            scp_bin, private_key_path,
            [
                os.path.join(web_ui_dir, "gardena-matter-restore.service"),
                os.path.join(web_ui_dir, "gardena-matter-restore.path"),
            ],
            f"{UNIT_DIR}/",
            host,
        ),
        "scp gardena-matter-restore.service + .path -> /etc/systemd/system/",
    )

    # 10. Activate restore service
    _run(
        runner,
        _ssh_cmd(ssh_bin, private_key_path, host, _REMOTE_RESTORE_ACTIVATE_TEMPLATE.format()),
        "ssh: Restore-Service aktivieren",
    )


# ---------------------------------------------------------------------------
# Public deploy entry point
# ---------------------------------------------------------------------------

def deploy(
    host: str,
    private_key_path: str,
    binary_path: str,
    libs_tgz_path: str,
    web_ui_dir: str,
    *,
    addon_version: str = "unknown",
    build_version: str = "dev",
    runner: SubprocessRunner = real_ssh_runner,
) -> None:
    """Full native deploy via ssh/scp — no bash, no paramiko.

    Order is binding:
      1. install_bridge  (binary + libs + systemd unit)
      2. install_web_ui  (matter.html + toggle + units)
      3. install_restore (restore-src/ + restore service)

    All calls use ssh.exe/scp.exe with IdentitiesOnly=yes.
    Tool resolution via find_tool. Preflight separately via preflight_check().

    EN: Full native deploy via ssh/scp subprocess calls. No bash, no paramiko.
    DE: Vollstaendiger nativer Deploy via ssh/scp. Kein bash, kein paramiko.
    """
    install_bridge(
        host, private_key_path, binary_path, libs_tgz_path, runner=runner
    )
    install_web_ui(
        host, private_key_path, web_ui_dir,
        addon_version=addon_version,
        build_version=build_version,
        runner=runner,
    )
    install_restore(
        host, private_key_path, web_ui_dir, runner=runner
    )
