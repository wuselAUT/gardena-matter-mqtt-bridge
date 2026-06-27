"""discovery.py — Gateway-Discovery (ARP+OUI, native .local, manuell).

Ports the on-device-verified discovery logic to Python (stdlib only, Python 3.9+).

Discovery methods (router-independent):
  1. PRIMARY:   ARP + MAC-OUI matching (Layer 2, no DNS, no mDNS service browsing).
                Ping-sweep of the local /24 fills the ARP cache; then `arp -a` is
                parsed; OUI match is anchored at the start of the MAC token
                (prevents false positives from OUIs appearing mid-address).
                Windows hyphen (94-bb-ae-...) AND Linux/macOS colon
                (94:bb:ae:...) formats are both supported.
  2. SECONDARY: Native GARDENA-<id>.local via socket.getaddrinfo or ping (no Bonjour).
  3. FALLBACK:  Manual IP entry.

EN: Ports the on-device-verified discovery logic to Python (stdlib only, 3.9+).
DE: Portiert die on-device-verifizierte Discovery-Logik nach Python (stdlib only, 3.9+).
"""

from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import List, Optional

# ---------------------------------------------------------------------------
# Known GARDENA/Husqvarna OUI prefix list (maintainable).
# Format: lowercase, colon-separated, exactly 3 octets.
# EN: Known Gardena/Husqvarna OUI prefixes (maintainable list).
# DE: Bekannte Gardena/Husqvarna OUI-Praefix-Liste (erweiterbar).
# ---------------------------------------------------------------------------
GARDENA_OUIS: List[str] = ["94:bb:ae"]

# Ping sweep parameters
_PING_THREADS = 64          # parallelism
_PING_TIMEOUT_S = 1         # timeout per ping in seconds
_ARP_TIMEOUT_S = 5          # timeout for arp command


@dataclass
class GatewayCandidate:
    """A discovered gateway candidate."""

    ip: str
    mac: Optional[str] = None   # None for manual entry or .local resolution
    label: str = ""             # display name


def _normalize_mac(mac_raw: str) -> Optional[str]:
    """Normalizes a MAC string to lowercase colon-separated form.

    Accepts Windows hyphen (aa-bb-cc-dd-ee-ff) AND
    Linux/macOS colon format (aa:bb:cc:dd:ee:ff).
    Returns None for invalid input.

    EN: Normalizes MAC to lowercase colon-separated form.
    DE: Normalisiert MAC auf Kleinbuchstaben, Doppelpunkt-getrennt.
    """
    # Accepts: exactly 6 groups of 2 hex digits, separated by ':' or '-'
    m = re.fullmatch(
        r"([0-9A-Fa-f]{2})[:\-]([0-9A-Fa-f]{2})[:\-]([0-9A-Fa-f]{2})"
        r"[:\-]([0-9A-Fa-f]{2})[:\-]([0-9A-Fa-f]{2})[:\-]([0-9A-Fa-f]{2})",
        mac_raw.strip(),
    )
    if not m:
        return None
    return ":".join(g.lower() for g in m.groups())


def _oui_of(mac_normalized: str) -> str:
    """Returns the first 3 octets of a normalized MAC."""
    parts = mac_normalized.split(":")
    return ":".join(parts[:3])


def _is_gardena_mac(mac_normalized: str, oui_list: List[str] = GARDENA_OUIS) -> bool:
    """Checks if the MAC belongs to a known GARDENA OUI.

    Comparison is anchored at the start of the MAC token (NOT substring):
    prevents false positives such as an OUI match in the middle of an IP
    address or as octets 2-4 of a foreign MAC (e.g. 00:94:bb:ae:xx:xx).

    EN: Checks if MAC belongs to a known Gardena OUI (anchored prefix match).
    DE: Prueft ob MAC einem bekannten GARDENA-OUI gehoert (verankerter Praefix-Match).
    """
    oui = _oui_of(mac_normalized)
    return any(oui == known.lower() for known in oui_list)


# ---------------------------------------------------------------------------
# ARP table parser
# ---------------------------------------------------------------------------

# Pattern for a dotted-quad IP:
#   - in parentheses: (192.168.1.50)  — Linux/macOS format
#   - bare at line start (after whitespace): 192.168.1.50  — Windows format
# Both variants are supported.
_IP_IN_PARENS = re.compile(r"\((\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\)")
_IP_BARE = re.compile(r"(?:^|\s)(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?:\s|$)")

# Pattern for a MAC token (6 hex octets, hyphen OR colon).
# We search for the FIRST such token in the line (IP comes before it).
_MAC_PATTERN = re.compile(
    r"(?<![0-9a-fA-F:])([0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}"
    r"[:\-][0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2}[:\-][0-9a-fA-F]{2})(?![0-9a-fA-F:])"
)


def parse_arp_output(arp_text: str, oui_list: List[str] = GARDENA_OUIS) -> List[GatewayCandidate]:
    """Parses `arp -a` output and returns GARDENA candidates.

    Supports:
      - Windows:    ? (192.168.1.50)    94-bb-ae-11-22-33   dynamic  ...
      - Linux:      ? (192.168.1.50) at 94:bb:ae:11:22:33 [ether] on eth0
      - macOS:      ? (192.168.1.50) at 94:bb:ae:11:22:33 on en0 ...
      - Incomplete/placeholder entries (without a valid MAC) are skipped.

    OUI comparison is anchored at the start of the MAC token — no substring false positives.

    EN: Parses `arp -a` output and returns Gardena candidates.
    DE: Parst `arp -a`-Ausgabe und liefert GARDENA-Kandidaten.
    """
    candidates: List[GatewayCandidate] = []
    seen_ips: set[str] = set()

    for line in arp_text.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue
        # Skip incomplete entries
        if "incomplete" in line_stripped.lower():
            continue

        # Extract IP — priority:
        #   1. In parentheses (Linux/macOS): (192.168.1.50)
        #   2. Bare IP at line start (Windows): "  192.168.1.50   94-bb-ae-..."
        ip_m = _IP_IN_PARENS.search(line_stripped)
        if ip_m:
            ip = ip_m.group(1)
        else:
            bare_m = _IP_BARE.search(line_stripped)
            if bare_m:
                ip = bare_m.group(1)
            else:
                continue

        # Find MAC token (first valid token)
        mac_m = _MAC_PATTERN.search(line_stripped)
        if not mac_m:
            continue
        mac_raw = mac_m.group(1)

        mac_norm = _normalize_mac(mac_raw)
        if mac_norm is None:
            continue

        if not _is_gardena_mac(mac_norm, oui_list):
            continue

        if ip in seen_ips:
            continue
        seen_ips.add(ip)

        # Display label: GARDENA-<last 3 hex octets without separators>
        suffix = mac_norm.replace(":", "")[-6:]
        label = f"GARDENA-{suffix}"
        candidates.append(GatewayCandidate(ip=ip, mac=mac_norm, label=label))

    return candidates


# ---------------------------------------------------------------------------
# Ping sweep (fills ARP cache)
# ---------------------------------------------------------------------------

def _ping_one(host: str, timeout_s: int = _PING_TIMEOUT_S) -> None:
    """Sends a single ICMP ping (fire-and-forget, no output)."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["ping", "-n", "1", "-w", str(timeout_s * 1000), host],
                capture_output=True, timeout=timeout_s + 2,
            )
        else:
            subprocess.run(
                ["ping", "-c", "1", "-W", str(timeout_s), host],
                capture_output=True, timeout=timeout_s + 2,
            )
    except Exception:  # noqa: BLE001
        pass


def ping_sweep(subnet_base: str, timeout_s: int = _PING_TIMEOUT_S) -> None:
    """Ping-sweeps the full /24 subnet (subnet_base = '192.168.0').

    Starts all 254 pings in parallel threads and waits for completion.
    Purpose: fill the OS ARP cache (no result parsing needed).

    EN: Ping-sweeps the /24 subnet to populate the OS ARP cache.
    DE: Ping-Sweep des /24-Subnetzes zum Befuellen des ARP-Caches.
    """
    threads: List[threading.Thread] = []
    for last in range(1, 255):
        host = f"{subnet_base}.{last}"
        t = threading.Thread(target=_ping_one, args=(host, timeout_s), daemon=True)
        threads.append(t)
        t.start()
        # Batch limit: don't start more than _PING_THREADS at once
        if len([th for th in threads if th.is_alive()]) >= _PING_THREADS:
            # Wait until at least one finishes
            for th in threads:
                th.join(timeout=0.05)

    # Wait for all remaining threads
    for th in threads:
        th.join()


def _get_local_ip() -> Optional[str]:
    """Determines the local primary IP address (via UDP socket trick).

    No packets are actually sent. Platform-neutral (Windows/macOS/Linux).

    EN: Determines the local primary IP without sending any packets.
    DE: Bestimmt die eigene primaere IP ohne Pakete zu senden.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:  # noqa: BLE001
        return None


def _run_arp() -> str:
    """Runs `arp -a` and returns stdout as a string."""
    try:
        result = subprocess.run(
            ["arp", "-a"],
            capture_output=True, text=True, timeout=_ARP_TIMEOUT_S,
        )
        return result.stdout
    except Exception:  # noqa: BLE001
        return ""


def discover_via_arp(
    oui_list: List[str] = GARDENA_OUIS,
    do_sweep: bool = True,
    progress_cb=None,
) -> List[GatewayCandidate]:
    """Full ARP+OUI discovery.

    1. Determine local IP -> derive /24 subnet.
    2. Optional: ping sweep (fills ARP cache).
    3. Run `arp -a` and parse.
    4. Return candidates with matching OUI.

    progress_cb(msg: str): optional progress callback.

    EN: Full ARP+OUI discovery — sweep, read ARP table, filter by OUI.
    DE: Vollstaendige ARP+OUI-Discovery — Sweep, ARP-Tabelle lesen, OUI-Filter.
    """
    if progress_cb:
        progress_cb("Discovering Gardena gateways via ARP... / Gateway-Suche via ARP...")

    local_ip = _get_local_ip()
    if not local_ip:
        if progress_cb:
            progress_cb("[WARN] Could not determine local IP; ARP scan skipped. / Lokale IP unbekannt, ARP-Scan uebersprungen.")
        return []

    # /24 subnet base (e.g. '192.168.0')
    try:
        net = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
        subnet_base = str(net.network_address).rsplit(".", 1)[0]
    except Exception:  # noqa: BLE001
        parts = local_ip.rsplit(".", 1)
        subnet_base = parts[0]

    if progress_cb:
        progress_cb(f"Local IP: {local_ip} — sweeping {subnet_base}.1-254 (fills ARP table)...")
        progress_cb("This takes a few seconds, please wait... / Bitte warten...")

    if do_sweep:
        ping_sweep(subnet_base)

    if progress_cb:
        progress_cb("Parsing ARP table... / ARP-Tabelle auslesen...")

    arp_text = _run_arp()
    candidates = parse_arp_output(arp_text, oui_list)

    if progress_cb:
        progress_cb(f"Found {len(candidates)} Gardena device(s) via ARP OUI. / {len(candidates)} Gardena-Geraet(e) via ARP OUI gefunden.")

    return candidates


# ---------------------------------------------------------------------------
# Secondary: native .local hostname resolution
# ---------------------------------------------------------------------------

def resolve_local_hostname(hostname: str) -> Optional[str]:
    """Resolves a .local hostname natively (without Bonjour/avahi service browsing).

    Tries socket.getaddrinfo (DnsClient on Win10/11, Avahi on Linux, mDNS on macOS)
    and falls back to ping. Returns the first IPv4 address or None.

    EN: Resolves a .local hostname natively without Bonjour/dns-sd service browsing.
    DE: Loest .local-Hostnamen nativ auf, ohne Bonjour/avahi-Service-Browsing.
    """
    # Method 1: socket.getaddrinfo (platform-native mDNS on Win10+/macOS/Linux+avahi)
    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_INET)
        for _, _, _, _, sockaddr in results:
            ip = sockaddr[0]
            if ip:
                return ip
    except (socket.gaierror, OSError):
        pass

    # Method 2: Ping (extract IP from output)
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "2000", hostname],
                capture_output=True, text=True, timeout=5,
            )
            # Windows: "Reply from 192.168.1.50:" or "Antwort von 192.168.1.50:"
            m = re.search(r"(?:Reply from|Antwort von)\s+(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", result.stdout)
            if m:
                return m.group(1)
            # Alternative: IP in brackets from "PING GARDENA-xxx.local (192.168.1.50)"
            m = re.search(r"\[(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\]", result.stdout)
            if m:
                return m.group(1)
        else:
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "2", hostname],
                capture_output=True, text=True, timeout=5,
            )
            m = re.search(
                r"PING\s+\S+\s+\((\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\)",
                result.stdout,
            )
            if m:
                return m.group(1)
    except Exception:  # noqa: BLE001
        pass

    return None


def discover_via_local(serial_suffix: str, progress_cb=None) -> Optional[GatewayCandidate]:
    """Resolves GARDENA-<serial_suffix>.local natively.

    EN: Resolves GARDENA-<serial_suffix>.local natively.
    DE: Loest GARDENA-<serial_suffix>.local nativ auf.
    """
    hostname = f"GARDENA-{serial_suffix}.local"
    if progress_cb:
        progress_cb(f"Resolving {hostname}...")
    ip = resolve_local_hostname(hostname)
    if ip:
        if progress_cb:
            progress_cb(f"Resolved: {hostname} -> {ip}")
        return GatewayCandidate(ip=ip, mac=None, label=hostname.removesuffix(".local"))
    if progress_cb:
        progress_cb(f"[WARN] Could not resolve {hostname}. / {hostname} nicht aufloesbar.")
    return None


# ---------------------------------------------------------------------------
# Device ID validation (credential field)
# ---------------------------------------------------------------------------

# Valid format for the Device ID (sticker label):
#   - UUID-style sticker number (e.g. a1b2c3d4-..., ~36 characters)
#   - Minimum length: 8 characters
#   - Allowed characters: alphanumeric + hyphen (UUID style)
#   - NO 'GARDENA-' prefix (that is only the mDNS hostname, not a credential)
# EN: Valid Device ID: alphanumeric + hyphens, min 8 chars. No 'GARDENA-' prefix.
# DE: Gueltige Device ID: alphanumerisch + Bindestrich, mind. 8 Zeichen. Kein 'GARDENA-'-Praefix.
_DEVICE_ID_RE = re.compile(r"^[0-9A-Za-z\-]{8,}$")


def validate_device_id(device_id: str) -> bool:
    """Validates the Device ID (sticker label on the gateway).

    Requirements:
      - Non-empty, at least 8 characters
      - Allowed characters: alphanumeric + hyphen (UUID style, e.g. a1b2c3d4-...)
      - NO 'GARDENA-' prefix (that is the mDNS hostname prefix, NOT the credential)

    EN: Validates the Device ID (sticker label). Min 8 chars, alphanumeric/hyphens.
        No 'GARDENA-' prefix required or expected.
    DE: Prueft die Geraete-ID (Aufkleber). Mind. 8 Zeichen, alphanumerisch/Bindestrich.
        Kein 'GARDENA-'-Praefix erwartet oder erlaubt.
    """
    stripped = device_id.strip()
    if not stripped:
        return False
    return bool(_DEVICE_ID_RE.match(stripped))


# ---------------------------------------------------------------------------
# mDNS hostname suffix validation (for .local discovery only, NOT credential)
# ---------------------------------------------------------------------------

# Valid format: GARDENA-XXXXXX (at least 8 characters after 'GARDENA-' = 16 total)
# This function is used ONLY for the optional .local discovery prompt.
# NOT for credential input (use validate_device_id for that).
_SERIAL_RE = re.compile(r"^GARDENA-[0-9A-Za-z]{8,}$")


def validate_serial(serial: str) -> bool:
    """Validates a GARDENA mDNS hostname suffix (GARDENA-XXXXXX).

    Used ONLY for the optional .local discovery prompt ('GARDENA-<suffix>.local').
    NOT for credential input (Device ID) — use validate_device_id for that.

    Requirements:
      - Prefix: 'GARDENA-' (uppercase)
      - At least 8 alphanumeric characters after the prefix
      - Total length: at least 16 characters

    EN: Validates a GARDENA mDNS hostname (GARDENA-XXXXXX) — discovery only, NOT credential.
    DE: Prueft einen GARDENA-mDNS-Hostnamen (GARDENA-XXXXXX) — nur Discovery, NICHT Credential.
    """
    return bool(_SERIAL_RE.match(serial.strip()))
