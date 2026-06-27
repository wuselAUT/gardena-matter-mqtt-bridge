"""cli.py — Interaktiver CLI-Ablauf des Standalone-Installers.

Ablauf:
  1. Discovery: ARP+OUI -> .local -> manuell (nummerierte Auswahl)
  2. Seriennummer-Eingabe + Validierung
  3. Bestaetigung (IP + Seriennummer)
  4. Deploy-Aufruf (deploy.run_deploy)
  5. Browser-Open (webbrowser) auf https://<gateway-ip>/assets/matter.html
  6. Logging in Datei (gardena-install.log)

Bilinguale nutzersichtbare Strings: EN + DE.

EN: Interactive CLI flow for the standalone installer.
DE: Interaktiver CLI-Ablauf des Standalone-Installers.
"""

from __future__ import annotations

import logging
import os
import sys
import webbrowser
from typing import List, Optional

from .discovery import (
    GatewayCandidate,
    discover_via_arp,
    discover_via_local,
    validate_device_id,
    GARDENA_OUIS,
)
from .deploy import run_deploy
from .native_deploy import preflight_check, PreflightError


# ---------------------------------------------------------------------------
# Logging-Setup
# ---------------------------------------------------------------------------
LOG_FILE = os.path.join(os.path.expanduser("~"), "gardena-install.log")


def _setup_logging() -> logging.Logger:
    """Richtet File + Console-Logger ein."""
    logger = logging.getLogger("gardena_installer")
    logger.setLevel(logging.DEBUG)

    # Datei-Handler
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    # Console-Handler (nur INFO und hoeher)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    if not logger.handlers:
        logger.addHandler(fh)
        logger.addHandler(ch)

    return logger


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _print(msg: str, logger: logging.Logger) -> None:
    """Gibt Nachricht aus und schreibt ins Log."""
    logger.info(msg)


def _prompt(prompt_text: str) -> str:
    """Eingabeaufforderung (ueberschreibbar in Tests)."""
    return input(prompt_text).strip()


def _banner(logger: logging.Logger) -> None:
    """Startbanner ausgeben."""
    _print("", logger)
    _print("=" * 55, logger)
    _print("  Gardena Matter Bridge — Standalone Installer", logger)
    _print("  Gardena Matter Bridge — Standalone-Installer", logger)
    _print("=" * 55, logger)
    _print("", logger)


# ---------------------------------------------------------------------------
# Schritt 1: Discovery
# ---------------------------------------------------------------------------

def _run_discovery(logger: logging.Logger) -> List[GatewayCandidate]:
    """Fuehrt Discovery in drei Stufen durch und liefert die Kandidaten-Liste.

    Stufe 1: ARP+OUI (primaer, Layer 2)
    Stufe 2: natives .local (sekundaer, falls kein ARP-Treffer)
    Stufe 3: manuell (Fallback)

    EN: Runs three-stage discovery and returns the candidate list.
    DE: Dreistufige Discovery; liefert Kandidaten-Liste.
    """
    def _progress(msg: str) -> None:
        _print(f"  {msg}", logger)

    # Stufe 1: ARP+OUI
    _print("", logger)
    _print("Step 1 / Schritt 1: Discovering Gardena gateways on local network...", logger)
    _print("Gardena-Gateways im lokalen Netz suchen...", logger)

    candidates = discover_via_arp(GARDENA_OUIS, do_sweep=True, progress_cb=_progress)

    # Stufe 2: Natives .local (nur wenn kein ARP-Treffer)
    if not candidates:
        _print("", logger)
        _print("  No devices found via ARP. / Keine Geraete via ARP gefunden.", logger)
        _print(
            "  [SECONDARY] Try native mDNS .local resolution? "
            "/ [SEKUNDAER] Natives mDNS .local-Aufloesung versuchen?",
            logger,
        )
        _print(
            "  If you know the Gateway serial suffix (e.g. 1a2b3c), we can resolve",
            logger,
        )
        _print(
            "  'GARDENA-<id>.local' natively (no Bonjour/avahi required).",
            logger,
        )
        print()
        suffix = _prompt(
            "  Enter serial suffix (e.g. 1a2b3c) or press Enter to skip "
            "/ Seriennummer-Suffix eingeben oder Enter druecken: "
        )
        if suffix:
            cand = discover_via_local(suffix, progress_cb=_progress)
            if cand:
                candidates.append(cand)

    return candidates


# ---------------------------------------------------------------------------
# Schritt 2: Geraete-Auswahl (nummerierte Liste)
# ---------------------------------------------------------------------------

def _select_gateway(candidates: List[GatewayCandidate], logger: logging.Logger) -> Optional[str]:
    """Zeigt nummerierte Liste an und fragt den User.

    Optionen: [0], [1], ... / [m] manuell / [q] beenden.
    Liefert die ausgewaehlte IP oder None bei Abbruch.

    EN: Displays numbered list and asks the user to select.
    DE: Zeigt nummerierte Liste und fragt den User.
    """
    _print("", logger)
    _print("Select Gardena Gateway / Gateway auswaehlen:", logger)
    _print("", logger)

    if candidates:
        for idx, cand in enumerate(candidates):
            mac_info = f"  MAC: {cand.mac}" if cand.mac else ""
            _print(f"  [{idx}] {cand.label}{mac_info} — {cand.ip}", logger)
    else:
        _print("  (No GARDENA devices found automatically / Keine Geraete automatisch gefunden)", logger)

    _print("", logger)
    _print("  [m] Enter IP manually / IP manuell eingeben", logger)
    _print("  [q] Quit / Beenden", logger)
    _print("", logger)

    max_idx = len(candidates) - 1 if candidates else -1
    prompt = f"  Choose / Waehle (0-{max_idx}/m/q): " if candidates else "  Choose / Waehle (m/q): "

    choice = _prompt(prompt)

    if choice.lower() == "q":
        _print("Installation aborted. / Installation abgebrochen.", logger)
        return None

    if choice.lower() == "m":
        ip = _prompt(
            "  Enter Gateway IP address / Gateway-IP-Adresse eingeben "
            "(e.g. / z.B. 192.168.1.50): "
        )
        logger.debug(f"User entered IP manually: {ip}")
        return ip or None

    # Numerische Auswahl
    try:
        idx = int(choice)
    except ValueError:
        _print("  Invalid choice. / Ungueltige Auswahl.", logger)
        return None

    if 0 <= idx < len(candidates):
        selected = candidates[idx]
        logger.debug(f"User selected [{idx}]: {selected.label} -> {selected.ip}")
        return selected.ip

    _print(
        f"  Index {idx} is out of range (valid: 0-{max_idx}). / "
        f"Index {idx} ausserhalb des Bereichs (gueltig: 0-{max_idx}).",
        logger,
    )
    return None


# ---------------------------------------------------------------------------
# Schritt 3: Device-ID-Eingabe + Validierung (Credential)
# ---------------------------------------------------------------------------

def _enter_device_id(logger: logging.Logger) -> Optional[str]:
    """Fragt nach der Geraete-ID (Device ID) vom Aufkleber und validiert.

    Die Device ID ist das einzige Credential (nicht-leer, mind. 8 Zeichen,
    alphanumerisch/UUID-artig). KEIN 'GARDENA-'-Praefix erwartet.
    Das Login-Passwort wird von orchestrate.derive_login_password aus den
    ersten 8 Zeichen abgeleitet — hier nur die Device ID entgegennehmen.
    Maximal 3 Versuche.

    EN: Prompts for the Device ID from the sticker and validates (max 3 attempts).
        No 'GARDENA-' prefix expected — just the raw Device ID.
    DE: Fragt nach der Geraete-ID vom Aufkleber und validiert (max. 3 Versuche).
        Kein 'GARDENA-'-Praefix erwartet — nur die reine Geraete-ID.
    """
    _print("", logger)
    _print("Step 2 / Schritt 2: Device ID / Geraete-ID", logger)
    _print(
        "  Enter the Device ID from the sticker on the underside of the Gateway.",
        logger,
    )
    _print(
        "  Geraete-ID vom Aufkleber auf der Unterseite des Gateways eingeben.",
        logger,
    )
    _print(
        "  Example / Beispiel: a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        logger,
    )
    _print(
        "  (This is the Device ID / Geraete-ID — NOT the GARDENA-XXXXXX mDNS hostname)",
        logger,
    )
    _print("", logger)

    for attempt in range(1, 4):
        device_id = _prompt(f"  Device ID / Geraete-ID (attempt {attempt}/3): ")
        if validate_device_id(device_id):
            logger.debug("Device ID format valid (value not logged).")
            return device_id.strip()
        _print(
            "  Invalid. Expected: Device ID from sticker, min. 8 characters "
            "(alphanumeric/UUID, e.g. a1b2c3d4-…).",
            logger,
        )
        _print(
            "  Ungueltig. Erwartet: Geraete-ID vom Aufkleber, mind. 8 Zeichen "
            "(alphanumerisch/UUID, z.B. a1b2c3d4-…).",
            logger,
        )

    _print("  Too many invalid attempts. / Zu viele ungueltige Versuche.", logger)
    return None


# ---------------------------------------------------------------------------
# Schritt 4: Bestaetigung
# ---------------------------------------------------------------------------

def _confirm(gateway_ip: str, serial: str, logger: logging.Logger) -> bool:
    """Zeigt die gewaehlten Parameter und fragt nach Bestaetigung.

    EN: Shows selected parameters and asks for confirmation.
    DE: Zeigt die gewaehlten Parameter und fragt nach Bestaetigung.
    """
    _print("", logger)
    _print("Step 3 / Schritt 3: Confirm / Bestaetigen", logger)
    _print("", logger)
    _print(f"  Gateway IP:        {gateway_ip}", logger)
    _print("  Serial number:     (entered, not shown / eingegeben, nicht angezeigt)", logger)
    _print("", logger)
    _print("  The Bridge will now be deployed. This may take 1-2 minutes.", logger)
    _print("  Die Bridge wird jetzt deployt. Das dauert ca. 1-2 Minuten.", logger)
    _print("", logger)

    choice = _prompt("  Proceed? / Fortfahren? (y/n / j/n): ")
    confirmed = choice.lower() in ("y", "j", "yes", "ja")
    if not confirmed:
        _print("  Installation aborted. / Installation abgebrochen.", logger)
    return confirmed


# ---------------------------------------------------------------------------
# Schritt 5: Deploy + Browser-Open
# ---------------------------------------------------------------------------

def _do_deploy(
    gateway_ip: str,
    serial: str,
    logger: logging.Logger,
    **deploy_kwargs,
) -> bool:
    """Ruft den Deploy-Flow auf und gibt True bei Erfolg zurueck.

    EN: Calls the deploy flow and returns True on success.
    DE: Ruft Deploy-Flow auf, liefert True bei Erfolg.
    """
    def _progress(msg: str) -> None:
        _print(f"  {msg}", logger)

    _print("", logger)
    _print("Step 4 / Schritt 4: Deploying Bridge... / Bridge deployen...", logger)

    try:
        # device_id (serial) is never logged (security requirement)
        result = run_deploy(
            gateway_ip=gateway_ip,
            device_id=serial,
            progress_cb=_progress,
            **deploy_kwargs,
        )
        _print("", logger)
        _print("=" * 55, logger)
        _print("  SUCCESS! Bridge installed and running.", logger)
        _print("  ERFOLG! Bridge installiert und laeuft.", logger)
        _print("=" * 55, logger)
        _print(f"  Steps completed: {', '.join(result.steps)}", logger)
        return True
    except Exception as exc:  # noqa: BLE001
        _print("", logger)
        _print("  ERROR / FEHLER: Deploy failed / Deploy fehlgeschlagen.", logger)
        _print(f"  {exc}", logger)
        _print(f"  Full log: {LOG_FILE}", logger)
        logger.debug("Deploy exception", exc_info=True)
        return False


def _open_browser(gateway_ip: str, logger: logging.Logger) -> None:
    """Oeffnet den Browser auf der Matter-Commissioning-Seite.

    EN: Opens the browser to the Matter commissioning UI.
    DE: Oeffnet den Browser auf der Matter-Commissioning-Seite.
    """
    url = f"https://{gateway_ip}/assets/matter.html"
    _print("", logger)
    _print(f"  Opening browser / Browser oeffnen: {url}", logger)
    try:
        webbrowser.open(url)
        _print("  Browser launched. / Browser geoeffnet.", logger)
    except Exception:  # noqa: BLE001
        _print(f"  Browser launch failed. Open manually: {url}", logger)
        _print(f"  Browser-Start fehlgeschlagen. Manuell oeffnen: {url}", logger)


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

def main(**deploy_kwargs) -> int:
    """Hauptfunktion des CLI.

    Gibt 0 bei Erfolg, 1 bei Abbruch/Fehler zurueck.

    EN: Main CLI entry point. Returns 0 on success, 1 on abort/error.
    DE: CLI-Einstiegspunkt. Gibt 0 bei Erfolg, 1 bei Abbruch/Fehler.
    """
    # --help / -h: show usage and exit (non-interactive, usable for smoke test)
    if "--help" in sys.argv or "-h" in sys.argv:
        print(
            "Gardena Matter Bridge — Standalone Installer\n"
            "\n"
            "Usage / Nutzung:\n"
            "  gardena-installer-vX.Y.Z.exe\n"
            "\n"
            "Installs the Gardena Matter Bridge on your gateway.\n"
            "Installiert die Gardena Matter Bridge auf dem Gateway.\n"
            "\n"
            "Requirements / Voraussetzungen:\n"
            "  - Windows 10+ with OpenSSH (ssh-keygen in PATH)\n"
            "  - Network access to the GARDENA gateway\n"
            "  - Device ID / Geraete-ID from the sticker on the gateway\n"
            "    (e.g. a1b2c3d4-..., NOT the GARDENA-XXXXXX mDNS hostname)\n"
            "\n"
            "The installer detects your gateway automatically via ARP+MAC or\n"
            "native GARDENA-<id>.local resolution, then authenticates and deploys.\n"
            "\n"
            "Log file / Log-Datei: ~/gardena-install.log\n"
        )
        return 0

    logger = _setup_logging()
    _banner(logger)

    _print(f"  Log file / Log-Datei: {LOG_FILE}", logger)
    _print("", logger)

    # Preflight check: verify ssh/scp/ssh-keygen/curl are available
    try:
        preflight_check()
    except PreflightError as exc:
        _print("", logger)
        _print("  ERROR / FEHLER: Required tools missing / Erforderliche Tools fehlen.", logger)
        _print("", logger)
        for line in str(exc).splitlines():
            _print(f"  {line}", logger)
        _print("", logger)
        return 1

    # Discovery
    candidates = _run_discovery(logger)

    # Gateway-Auswahl
    gateway_ip = _select_gateway(candidates, logger)
    if not gateway_ip:
        return 1

    # Device ID (Geraete-ID vom Aufkleber = einziges Credential)
    device_id = _enter_device_id(logger)
    if not device_id:
        return 1

    # Bestaetigung
    if not _confirm(gateway_ip, device_id, logger):
        return 1

    # Deploy
    success = _do_deploy(gateway_ip, device_id, logger, **deploy_kwargs)
    if not success:
        return 1

    # Browser oeffnen
    _open_browser(gateway_ip, logger)

    _print("", logger)
    _print(f"  Done! / Fertig! Log: {LOG_FILE}", logger)
    return 0
