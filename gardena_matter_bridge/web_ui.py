#!/usr/bin/env python3
"""web_ui.py — Ingress-Status-UI des HA-Add-ons.

Minimaler, abhaengigkeitsfreier HTTP-Server (stdlib) hinter HA-Ingress (:8099).
Zeigt:
  - Deploy-Status (noch nicht deployt / laeuft / erfolgreich / Fehler)
  - Bridge-/Commissioning-Status (QR/Setup-Code aus dem Gateway-matter-status.json)
  - Re-Deploy-Knopf (POST /deploy -> orchestrate.run_full_deploy)
  - Link auf die Gateway-Seite /assets/matter.html

POST /api/deploy startet den ECHTEN Deploy (asynchron, Status-Polling).
Es werden REALE injizierte Implementierungen genutzt:
    - runner      = orchestrate.real_subprocess_runner (env ... bash <install-skript>)
    - http        = orchestrate.real_http_client       (HTTPS zum Gateway /login, /ssh_access_*)
    - downloader  = orchestrate.github_release_downloader (GitHub-Release, optional Token)
    - sig_verify  = None (optionaler Folge-Schritt, nicht aktiv)
expected_sha256 kommt aus resolve_expected_sha256(load_release_lock(...), tag)
-> Hash-Gate HART (Platzhalter/Tag-Mismatch => fail-closed VOR jedem Deploy).

Hard Constraints:
  - device_id (= Quelle des Login-PW, erste 8 Zeichen) wird NIE geloggt.
  - github_token wird NIE geloggt, nie in Antworten/Fehlern gespiegelt.

Diese Datei ist bewusst duenn: die testbare Logik liegt in orchestrate.py +
status.py. web_ui.py ist die HTTP-Glue-Schicht (Wiring + async Start).
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import orchestrate as orch
import status as status_mod

ADDON_DIR = os.environ.get("GARDENA_ADDON_DIR", "/opt/gardena")
WEB_DIR = os.path.join(ADDON_DIR, "web")
GATEWAY_HOST = os.environ.get("GARDENA_GATEWAY_HOST", "")

# In-Memory-Deploy-Status (idle bis der Nutzer den Deploy-Knopf drueckt).
DEPLOY_STATE = {
    "state": "idle",          # idle | running | success | error
    "message": "Noch nicht deployt. Aufkleber-Daten in den Add-on-Optionen eintragen.",
    "steps": [],
}

# Serialisiert konkurrierende Deploy-Starts (kein zweiter Lauf, solange einer laeuft).
_DEPLOY_LOCK = threading.Lock()


def _read_env_config() -> dict:
    """Liest die Deploy-Parameter aus den von run.sh exportierten ENV-Variablen.

    device_id + github_token sind Secrets -> werden NIE geloggt und nie in eine
    Antwort/Fehlermeldung gespiegelt.
    """
    return {
        "gateway_host": os.environ.get("GARDENA_GATEWAY_HOST", ""),
        "device_id": os.environ.get("GARDENA_DEVICE_ID", ""),
        "github_repo": os.environ.get(
            "GARDENA_GITHUB_REPO", "wuselAUT/gardena-matter-bridge"),
        "release_tag": os.environ.get("GARDENA_RELEASE_TAG", "v0.1.0"),
        "github_token": os.environ.get("GARDENA_GITHUB_TOKEN", ""),
        "priv_key": os.environ.get(
            "GARDENA_PRIV_KEY", "/data/ssh/addon_ed25519"),
        "pub_key": os.environ.get(
            "GARDENA_PUB_KEY", "/data/ssh/addon_ed25519.pub"),
        "disable_ssh_after": (
            os.environ.get("GARDENA_DISABLE_SSH_AFTER", "false") == "true"),
    }


def build_deploy_plan(cfg: dict, *, read_text=None) -> "orch.DeployPlan":
    """Baut den DeployPlan und verdrahtet das HARTE Hash-Gate.

    expected_sha256 = resolve_expected_sha256(load_release_lock(...), effective_tag)
    -> Platzhalter ODER Tag-Mismatch fuehren hier (vor jedem Gateway-/Deploy-
    Aufruf) zu einem fail-closed OrchestrationError. `read_text` ist injizierbar
    (Tests); produktiv liest load_release_lock die Lock-Datei.

    effective_tag: Ist cfg["release_tag"] leer/nur-Leerzeichen, wird automatisch
    lock.tag verwendet (keine Reibung nach Add-on-Updates). Ein EXPLIZIT gesetzter,
    zum Lock nicht passender Tag bricht weiterhin hart ab (fail-closed, Pin-Schutz
    bleibt erhalten). Denselben effective_tag nutzen sowohl der SHA-Pin-Resolve als
    auch DeployPlan.tag -> Download-Tag und Pin-Pfad sind immer konsistent.
    """
    if read_text is None:
        lock = orch.load_release_lock(orch._default_read_text)
    else:
        lock = orch.load_release_lock(read_text)
    # Effektiven Tag bestimmen: leer/whitespace -> Lock-Tag verwenden.
    effective_tag = (cfg["release_tag"] or "").strip() or lock.tag
    expected = orch.resolve_expected_sha256(lock, effective_tag)
    return orch.DeployPlan(
        gateway_host=cfg["gateway_host"],
        private_key_path=cfg["priv_key"],
        public_key_path=cfg["pub_key"],
        repo=cfg["github_repo"],
        tag=effective_tag,
        expected_sha256=expected,
        disable_ssh_after=cfg["disable_ssh_after"],
    )


def run_deploy(cfg: dict, state: dict, *,
               http=None, runner=None, downloader_factory=None,
               read_text=None, extractor=None,
               unpack_dir="/data/release") -> None:
    """Fuehrt den vollen Deploy aus + spiegelt den Fortschritt in `state`.

    REALE Implementierungen sind Default; die Tests injizieren Fakes. Der
    github_token wird NUR in den Downloader gegeben (Closure), NIE in `state`,
    Logs oder Fehlermeldungen. `extractor` ist injizierbar (Tests; produktiv =
    None -> orchestrate nutzt den default tarfile-Extractor).
    """
    http = http or orch.real_http_client
    runner = runner or orch.real_subprocess_runner

    def _default_downloader_factory(token):
        def _dl(repo, tag, dest):
            return orch.github_release_downloader(repo, tag, dest, token=token)
        return _dl

    factory = downloader_factory or _default_downloader_factory
    downloader = factory(cfg["github_token"])

    state["state"] = "running"
    state["message"] = "Deploy laeuft …"
    state["steps"] = []
    try:
        # build_deploy_plan setzt das harte Hash-Gate (fail-closed bei Platzhalter/
        # Tag-Mismatch) -> wirft VOR jedem Gateway-Aufruf.
        plan = build_deploy_plan(cfg, read_text=read_text)
        gateway = orch.GatewayClient(host=cfg["gateway_host"], http=http)
        result = orch.run_full_deploy(
            plan,
            gateway=gateway,
            device_id=cfg["device_id"],
            read_public_key=orch._default_read_text,
            downloader=downloader,
            read_bytes=_read_file_bytes,
            ssh_runner=runner,
            sig_verify=None,
            extractor=extractor,
            unpack_dir=unpack_dir,
        )
        state["steps"] = list(result.steps)
        state["state"] = "success"
        state["message"] = "Deploy erfolgreich. Die Bridge laeuft jetzt auf dem Gateway."
    except orch.OrchestrationError as exc:
        # OrchestrationError-Meldungen sind bewusst PW-/Token-frei formuliert.
        state["state"] = "error"
        state["message"] = str(exc)
    except Exception:  # noqa: BLE001
        # Generische Meldung -> niemals ein Secret durchsickern lassen.
        state["state"] = "error"
        state["message"] = "Deploy fehlgeschlagen (unerwarteter Fehler)."


def _read_file_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def start_deploy_async(cfg: dict, state: dict, *, spawn=None) -> bool:
    """Startet run_deploy im Hintergrund (Status-Polling via /api/status).

    Gibt True zurueck, wenn ein Deploy gestartet wurde; False, wenn bereits einer
    laeuft (kein paralleler Start). `spawn` ist injizierbar (Tests fuehren den
    Deploy synchron aus statt einen Thread zu starten).
    """
    if not _DEPLOY_LOCK.acquire(blocking=False):
        return False

    def _target():
        try:
            run_deploy(cfg, state)
        finally:
            _DEPLOY_LOCK.release()

    if spawn is not None:
        # Tests: synchron (oder kontrolliert) ausfuehren.
        try:
            spawn(_target)
        finally:
            pass
        return True

    threading.Thread(target=_target, name="gardena-deploy", daemon=True).start()
    return True


def _read_asset(name: str) -> bytes:
    path = os.path.join(WEB_DIR, name)
    with open(path, "rb") as fh:
        return fh.read()


class Handler(BaseHTTPRequestHandler):
    server_version = "GardenaMatterAddon/0.1"

    def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, obj: dict) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, _read_asset("index.html"))
            return
        if path == "/app.js":
            self._send(200, _read_asset("app.js"), "application/javascript")
            return
        if path == "/style.css":
            self._send(200, _read_asset("style.css"), "text/css")
            return
        if path == "/api/status":
            self._send_json(200, self._status_payload())
            return
        self._send(404, b"not found")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/deploy":
            # Deploy ist SCHARF — startet den echten Flow asynchron.
            # Status-Polling via /api/status. Laeuft bereits einer, kein Start.
            cfg = _read_env_config()
            started = start_deploy_async(cfg, DEPLOY_STATE)
            if not started:
                self._send_json(
                    409,
                    {
                        "accepted": False,
                        "reason": "deploy-already-running",
                        "message": "Es laeuft bereits ein Deploy — bitte warten.",
                    },
                )
                return
            # accepted:true -> der Deploy laeuft jetzt (kein accepted:false mehr).
            self._send_json(
                202,
                {
                    "accepted": True,
                    "reason": "deploy-started",
                    "message": (
                        "Deploy gestartet. Der Fortschritt erscheint hier "
                        "(Status wird laufend aktualisiert)."
                    ),
                },
            )
            return
        self._send(404, b"not found")

    def _status_payload(self) -> dict:
        # eine Session = mutierender Login-Flow). Wir liefern den Default-Status +
        # die ableitbaren Felder. Der Live-Status kommt mit dem Deploy.
        gw_status = status_mod.empty_status()
        if GATEWAY_HOST:
            gw_status["gateway_host"] = GATEWAY_HOST
            gw_status["gateway_matter_url"] = status_mod.gateway_matter_url(GATEWAY_HOST)
        gw_status["summary"] = status_mod.human_summary(gw_status)
        return {
            "deploy": DEPLOY_STATE,
            "gateway": gw_status,
        }

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        # Knapp loggen; NIE Request-Bodies (koennten Geheimnisse enthalten).
        print("[gardena-ui] " + (fmt % args))


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", 8099), Handler)
    print("[gardena-ui] Ingress-Status-UI laeuft auf :8099")
    server.serve_forever()


if __name__ == "__main__":
    main()
