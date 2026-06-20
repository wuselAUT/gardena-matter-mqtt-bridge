#!/usr/bin/env python3
"""status.py — Status-/Commissioning-Logik.

Reine, testbare Funktionen zum Aufbereiten des Bridge-/Commissioning-
Status fuer die Ingress-UI. Quelle = das vom Gateway gelieferte matter-status.json
(Schema, siehe matter/web-ui/update-matter-status.sh):

  {
    "qr_payload": "MT:...",
    "manual_code": "34970112332",
    "commissioning": "open" | "closed",
    "commissioning_remaining": <int>,
    "commissioning_close_epoch": <int>,
    "bridge_active": true | false,
    "services": {"matter": "active"|"inactive"},
    "updated_at": "...Z"
  }

T3 = halb-manuelles Commissioning (b): Add-on zeigt QR/Setup-Code an, der Nutzer
fuegt ihn in HA -> "Geraet hinzufuegen -> Matter" ein. KEINE HA-Commissioning-API.
"""

from __future__ import annotations

import json
from typing import Any, Dict


def empty_status() -> Dict[str, Any]:
    """Default-Status, wenn das Gateway (noch) keine Daten liefert."""
    return {
        "reachable": False,
        "bridge_active": False,
        "commissioning": "unknown",
        "commissioning_remaining": 0,
        "qr_payload": "",
        "manual_code": "",
        "updated_at": "",
        "gateway_host": "",
        "gateway_matter_url": "",
    }


def gateway_matter_url(host: str) -> str:
    """Link auf die Gateway-lokale Matter-Seite (/assets/matter.html)."""
    return f"https://{host}/assets/matter.html"


def parse_matter_status(raw: str) -> Dict[str, Any]:
    """Parst die matter-status.json des Gateways defensiv -> UI-Status.

    Wirft NICHT bei fehlenden Feldern; liefert sinnvolle Defaults, damit die UI
    nie crasht. Unbekannte/leere Eingabe -> reachable=False.
    """
    out = empty_status()
    if not raw or not raw.strip():
        return out
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return out
    if not isinstance(data, dict):
        return out

    out["reachable"] = True
    out["bridge_active"] = bool(data.get("bridge_active", False))
    out["qr_payload"] = str(data.get("qr_payload", "") or "")
    out["manual_code"] = str(data.get("manual_code", "") or "")
    out["updated_at"] = str(data.get("updated_at", "") or "")

    commissioning = data.get("commissioning", "unknown")
    if commissioning not in ("open", "closed"):
        commissioning = "unknown"
    out["commissioning"] = commissioning

    try:
        out["commissioning_remaining"] = max(0, int(data.get("commissioning_remaining", 0)))
    except (ValueError, TypeError):
        out["commissioning_remaining"] = 0

    return out


def commissioning_ready(status: Dict[str, Any]) -> bool:
    """True wenn ein QR/Manual-Code fuer das Einfuegen in HA bereitsteht."""
    return bool(status.get("qr_payload")) or bool(status.get("manual_code"))


def human_summary(status: Dict[str, Any]) -> str:
    """Kurzer, nutzerlesbarer Status-Satz fuer die UI (kein Secret)."""
    if not status.get("reachable"):
        return "Gateway nicht erreichbar oder Bridge noch nicht deployt."
    if not status.get("bridge_active"):
        return "Bridge ist deployt, aber gerade nicht aktiv."
    if commissioning_ready(status):
        if status.get("commissioning") == "open":
            return "Bridge aktiv — Commissioning-Fenster offen, QR/Code bereit."
        return "Bridge aktiv — QR/Code bereit (Fenster ggf. geschlossen)."
    return "Bridge aktiv — warte auf QR/Setup-Code."
