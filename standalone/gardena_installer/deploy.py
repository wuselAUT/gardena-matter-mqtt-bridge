"""deploy.py — Thin wrapper around orchestrate.py for the standalone installer.

Reuses the proven deploy core (orchestrate.py) — no reimplementation of the
auth flow. The deploy step is executed via native_deploy.deploy
(scp.exe/ssh.exe via subprocess — no bash, no WSL, no third-party packages).

Call sequence:
  1. Generate SSH keypair via ssh-keygen (subprocess, temporary directory).
  2. Read bridge-release.lock (orchestrate.load_release_lock).
  3. Build DeployPlan (gateway_host, repo, tag, sha256, key paths).
  4. Instantiate GatewayClient(host, real_http_client).
  5. Use orchestrate building blocks for auth + download + unpack (no bash deploy):
       ssh_reachable -> (login -> install_public_key -> set_ssh_enabled) ->
       fetch_and_verify_release -> unpack_bundle ->
       native_deploy.deploy(...) [pure Python, Windows built-in tools]
  MQTT: disabled by default (mqtt_config=None).

Hard constraints:
  - device_id (= serial number) is NEVER logged (security requirement).
  - The password is derived by orchestrate.derive_login_password — this wrapper
    only passes the device_id, NEVER the derived password.

EN: Thin wrapper. Auth + download via orchestrate.py; deploy step via native_deploy.py
    (ssh.exe/scp.exe subprocess — no bash, no WSL, no third-party packages).
DE: Duenner Wrapper. Auth + Download via orchestrate.py; Deploy-Schritt via native_deploy.py
    (ssh.exe/scp.exe subprocess — kein bash, kein WSL, kein Fremdpaket).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, List, Optional

# ---------------------------------------------------------------------------
# Import orchestrate.py — do NOT reimplement.
# Strategies (in order):
#   1. orchestrate.py is in the same directory as this module
#      (when packaged as a copy alongside the installer).
#   2. Public repo layout: gardena_matter_bridge/ next to standalone/
#      (relative to standalone/gardena_installer/ this is ../../gardena_matter_bridge/).
#   3. Same directory as this package (when bundled together).
# ---------------------------------------------------------------------------
def _resolve_orchestrate_module() -> None:
    """Adds the directory containing orchestrate.py to sys.path (idempotent).

    EN: Adds the orchestrate.py directory to sys.path (idempotent).
    DE: Fuegt das orchestrate.py-Verzeichnis zum sys.path hinzu (einmalig).
    """
    # Already importable? -> nothing to do.
    try:
        import orchestrate  # noqa: F401
        return
    except ImportError:
        pass

    # Directory of this file (standalone/gardena_installer/)
    _here = Path(__file__).parent.resolve()

    # Possible locations where orchestrate.py may live:
    candidates = [
        _here,                                               # next to deploy.py (packaged)
        _here.parent,                                        # standalone/
        _here.parent.parent / "gardena_matter_bridge",      # public repo layout
    ]

    for candidate in candidates:
        if (candidate / "orchestrate.py").exists():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return

    raise ImportError(
        "orchestrate.py not found. Expected in gardena_matter_bridge/ or next to deploy.py. "
        "/ orchestrate.py nicht gefunden."
    )


_resolve_orchestrate_module()

import orchestrate  # noqa: E402 (after sys.path setup)


# ---------------------------------------------------------------------------
# Generate SSH keypair
# ---------------------------------------------------------------------------

def generate_ssh_keypair(key_dir: str) -> tuple[str, str]:
    """Generates a temporary ed25519 SSH keypair via ssh-keygen.

    Returns (private_key_path, public_key_path).
    The keypair is placed in key_dir; the caller is responsible for cleanup.

    EN: Generates a temporary ed25519 SSH keypair via ssh-keygen.
    DE: Erzeugt ein temporaeres ed25519-SSH-Keypaar via ssh-keygen.
    """
    private_key = os.path.join(key_dir, "gardena_installer_key")
    public_key = private_key + ".pub"

    try:
        result = subprocess.run(
            [
                "ssh-keygen",
                "-t", "ed25519",
                "-N", "",           # empty passphrase
                "-f", private_key,
                "-C", "gardena-standalone-installer",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise orchestrate.OrchestrationError(
            "ssh-keygen not found. Please install OpenSSH. / "
            "ssh-keygen nicht gefunden. Bitte OpenSSH installieren."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise orchestrate.OrchestrationError(
            "ssh-keygen timed out. / ssh-keygen Zeitlimit ueberschritten."
        ) from exc

    if result.returncode != 0:
        raise orchestrate.OrchestrationError(
            f"ssh-keygen failed (exit {result.returncode}): {result.stderr.strip()}"
        )

    return private_key, public_key


# ---------------------------------------------------------------------------
# Read public key (injectable for tests)
# ---------------------------------------------------------------------------

def _default_read_public_key(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


def _default_read_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def _default_read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Locate bridge-release.lock
# ---------------------------------------------------------------------------

def _find_release_lock_path() -> str:
    """Locates bridge-release.lock in the repository.

    EN: Locates bridge-release.lock in the repository.
    DE: Sucht bridge-release.lock im Repository.
    """
    _here = Path(__file__).parent.resolve()
    candidates = [
        _here / "bridge-release.lock",                      # next to deploy.py (packaged)
        _here.parent / "bridge-release.lock",               # standalone/
        _here.parent.parent / "gardena_matter_bridge" / "bridge-release.lock",  # public repo
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    # Last fallback: default path in orchestrate (resolved at runtime)
    return orchestrate.RELEASE_LOCK_PATH


# ---------------------------------------------------------------------------
# Main deploy function
# ---------------------------------------------------------------------------

def _ssh_reachable_with_key(
    ssh_runner,
    host: str,
    private_key_path: str,
) -> bool:
    """SSH reachability probe using IdentitiesOnly=yes and -i <key>.

    Replaces orchestrate.ssh_reachable() in the standalone deploy path.
    orchestrate.ssh_reachable() does not set IdentitiesOnly=yes — on Windows
    with a loaded ssh-agent this causes false negatives: the agent offers all
    keys, the gateway's SSH server rejects after too many attempts (MaxAuthTries),
    even though our key is not yet installed.

    Using IdentitiesOnly=yes ensures only our specific key is offered,
    preventing spurious authentication failures.

    EN: SSH reachability probe with IdentitiesOnly=yes + -i (prevents false
        negatives on Windows when an ssh-agent with multiple keys is running).
    DE: SSH-Probe mit IdentitiesOnly=yes + -i (verhindert Falsch-Negative auf
        Windows mit gefuelltem ssh-agent).
    """
    from .native_deploy import _ssh_opts, find_tool

    try:
        ssh_bin = find_tool("ssh") or "ssh"
        cmd = [ssh_bin] + _ssh_opts(private_key_path) + [
            f"root@{host}",
            "true",
        ]
        rc = ssh_runner(cmd)
        return rc == 0
    except Exception:  # noqa: BLE001
        return False


def run_deploy(
    gateway_ip: str,
    device_id: str,
    *,
    progress_cb: Optional[Callable[[str], None]] = None,
    unpack_dir: Optional[str] = None,
    download_dir: Optional[str] = None,
    # Injection points for unit tests (production = None -> real implementations)
    http_client=None,
    ssh_runner=None,
    downloader=None,
    read_bytes=None,
    read_public_key_fn=None,
    read_text_fn=None,
    release_lock_path: Optional[str] = None,
    addon_version: str = "",
    # Native deploy runner (injectable for tests)
    native_deploy_runner=None,
) -> orchestrate.DeployResult:
    """Full deploy flow using native ssh/scp (no bash, no WSL).

    Steps:
      1. Generate SSH keypair in a temporary directory.
      2. Read bridge-release.lock -> repo/tag/sha256.
      3. Use orchestrate building blocks for auth:
           ssh_reachable -> (login -> install_public_key -> set_ssh_enabled)
      4. fetch_and_verify_release (SHA256 gate)
      5. unpack_bundle
      6. native_deploy.deploy(...) [pure Python, Windows built-in tools]
         instead of orchestrate.deploy_via_ssh (bash scripts)

    MQTT is disabled by default (mqtt_config=None).

    Hard constraints:
      - device_id is NEVER logged; the password is derived by orchestrate.
      - Error messages NEVER contain device_id or the derived password.

    EN: Full deploy flow — SSH keypair, lock, auth, download, native deploy.
    DE: Vollstaendiger Deploy-Flow — Auth via orchestrate, Deploy via native_deploy.
    """
    from .native_deploy import deploy as _native_deploy_fn
    from .native_deploy import real_ssh_runner as _real_native_runner

    def _progress(msg: str) -> None:
        if progress_cb:
            progress_cb(msg)

    _progress("Preparing deploy... / Deploy vorbereiten...")

    # Productive defaults
    _http_client = http_client or orchestrate.real_http_client
    # ssh_runner: used for the ssh_reachable probe (orchestrate building block)
    _ssh_probe_runner = ssh_runner or orchestrate.real_subprocess_runner
    _downloader = downloader or orchestrate.github_release_downloader
    _read_bytes = read_bytes or _default_read_bytes
    _read_text = read_text_fn or _default_read_text
    _read_public_key = read_public_key_fn or _default_read_public_key
    _lock_path = release_lock_path or _find_release_lock_path()
    # Native deploy runner (injectable for tests)
    _nd_runner = native_deploy_runner or _real_native_runner

    if not gateway_ip:
        raise orchestrate.OrchestrationError(
            "gateway_host fehlt — bitte Gateway-IP eingeben."
        )

    # Derive login password from device_id (error here aborts before any network call)
    login_password = orchestrate.derive_login_password(device_id)

    # Read release lock
    _progress("Reading release lock / Release-Lock lesen...")
    lock = orchestrate.load_release_lock(read_text=_read_text, path=_lock_path)
    expected_sha256 = orchestrate.resolve_expected_sha256(lock, configured_tag="")

    _progress(f"Using bundle tag {lock.tag} / Bundle-Tag: {lock.tag}")

    result = orchestrate.DeployResult()

    # Generate SSH keypair
    _progress("Generating SSH keypair... / SSH-Keypaar erzeugen...")
    with tempfile.TemporaryDirectory() as key_dir:
        private_key_path, public_key_path = generate_ssh_keypair(key_dir)

        # Local unpack and download directories (not /data/release)
        _unpack_dir = unpack_dir or os.path.join(tempfile.gettempdir(), "gardena-release")
        _download_dir = download_dir or os.path.join(tempfile.gettempdir(), "gardena-download")

        # Instantiate GatewayClient (for auth flow)
        gateway = orchestrate.GatewayClient(
            host=gateway_ip,
            http=_http_client,
        )

        _progress("Checking SSH reachability... / SSH-Erreichbarkeit pruefen...")
        # Use IdentitiesOnly=yes probe instead of orchestrate.ssh_reachable()
        # to avoid false negatives when an ssh-agent with multiple keys is running.
        if _ssh_reachable_with_key(_ssh_probe_runner, gateway_ip, private_key_path):
            # SSH already reachable (key installed, enable still active)
            result.steps.append("ssh_already_available")
            _progress("SSH already available, skipping auth. / SSH bereits erreichbar, Auth ueberspringen.")
        else:
            # First install: login -> key -> enable (verbatim orchestrate order)
            _progress("Authenticating at gateway... / Am Gateway authentifizieren...")
            gateway.login(login_password)
            result.steps.append("login")

            public_key = _read_public_key(public_key_path)
            gateway.install_public_key(public_key)
            result.steps.append("install_credentials")

            gateway.set_ssh_enabled(True)
            result.steps.append("enable_ssh")
            _progress("SSH enabled. / SSH freigegeben.")

        # Download release + SHA256 gate
        _progress(f"Downloading bundle {lock.tag}... / Bundle {lock.tag} herunterladen...")
        artifact = orchestrate.fetch_and_verify_release(
            _downloader,
            _read_bytes,
            repo=lock.repo,
            tag=lock.tag,
            expected_sha256=expected_sha256,
            download_dir=_download_dir,
        )
        result.steps.append("release_verified")
        result.artifact_sha256 = artifact.sha256
        _progress("Bundle verified. / Bundle verifiziert.")

        # Unpack bundle
        _progress("Unpacking bundle... / Bundle entpacken...")
        bundle = orchestrate.unpack_bundle(
            artifact.path,
            _unpack_dir,
        )
        result.bundle_version = bundle.version
        result.steps.append("bundle_unpacked")
        _progress(f"Bundle unpacked (version {bundle.version}). / Bundle entpackt.")

        # Native deploy via ssh.exe/scp.exe (no bash)
        _progress("Deploying via native ssh/scp... / Native ssh/scp Deploy...")
        _native_deploy_fn(
            gateway_ip,
            private_key_path,
            bundle.binary_path,
            bundle.libs_tgz_path,
            bundle.web_ui_dir,
            addon_version=addon_version or orchestrate.load_addon_version(),
            build_version=bundle.version or "dev",
            runner=_nd_runner,
        )
        result.executed_scripts = ["install_bridge", "install_web_ui", "install_restore"]
        result.steps.append("deploy")
        _progress("Deploy complete. / Deploy abgeschlossen.")

    _progress(f"Deploy complete. Steps: {', '.join(result.steps)}")
    _progress(f"Deploy abgeschlossen. Schritte: {', '.join(result.steps)}")

    return result
