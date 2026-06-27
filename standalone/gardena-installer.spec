# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec — Gardena Matter Bridge Standalone Installer
#
# Build: pyinstaller gardena-installer.spec
# Output: dist/gardena-installer-windows.exe  (Windows onefile)
#
# Requirements:
#   - Python >= 3.9
#   - PyInstaller >= 5.x
#   - Windows build host for Windows target
#
# What gets bundled:
#   - gardena_installer package (cli, deploy, discovery, __main__)
#   - orchestrate.py  (deploy core, from gardena_matter_bridge/)
#   - bridge-release.lock  (pinned bundle tag + sha256)
#
# Repository layout expected by this spec:
#   standalone/                      <- this file lives here
#     gardena_installer/
#     gardena-installer.spec
#   gardena_matter_bridge/           <- one level up from standalone/
#     orchestrate.py
#     bridge-release.lock
#
# To override, place orchestrate.py and bridge-release.lock directly
# next to this spec file (they take precedence).

import os

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# PyInstaller sets SPECPATH to the directory of the .spec file.
SPEC_DIR = os.path.abspath(SPECPATH)
REPO_ROOT = os.path.abspath(os.path.join(SPEC_DIR, ".."))
PUBLIC_BRIDGE_DIR = os.path.join(REPO_ROOT, "gardena_matter_bridge")

# orchestrate.py and bridge-release.lock: prefer a copy next to the spec
# (for reproducible packaging), fall back to canonical public-repo location.
ORCHESTRATE_SRC = os.path.join(SPEC_DIR, "orchestrate.py")
if not os.path.exists(ORCHESTRATE_SRC):
    ORCHESTRATE_SRC = os.path.join(PUBLIC_BRIDGE_DIR, "orchestrate.py")

LOCK_SRC = os.path.join(SPEC_DIR, "bridge-release.lock")
if not os.path.exists(LOCK_SRC):
    LOCK_SRC = os.path.join(PUBLIC_BRIDGE_DIR, "bridge-release.lock")

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    # Entry point: gardena_installer/__main__.py
    [os.path.join(SPEC_DIR, "gardena_installer", "__main__.py")],
    pathex=[
        SPEC_DIR,
        PUBLIC_BRIDGE_DIR,   # so orchestrate is importable during analysis
    ],
    binaries=[],
    datas=[
        # orchestrate.py embedded as data — deploy.py imports it at runtime
        # via _resolve_orchestrate_module() which searches sys.path incl. _MEIPASS
        (ORCHESTRATE_SRC, "."),
        # bridge-release.lock: pinned bundle version + sha256
        (LOCK_SRC, "."),
    ],
    hiddenimports=[
        "orchestrate",
        "gardena_installer",
        "gardena_installer.cli",
        "gardena_installer.deploy",
        "gardena_installer.discovery",
        "gardena_installer.native_deploy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="gardena-installer-windows",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,       # UPX disabled: avoids false AV positives
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,    # Console app (interactive CLI)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    onefile=True,    # Single .exe — no unpacked folder needed
)
