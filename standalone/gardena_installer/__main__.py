"""__main__.py — Einstiegspunkt fuer `python -m gardena_installer`.

EN: Entry point for `python -m gardena_installer`.
DE: Einstiegspunkt fuer `python -m gardena_installer`.
"""

import sys

# Relativer Import für `python -m gardena_installer`; absoluter Fallback für den
# eingefrorenen PyInstaller-Build, wo __main__.py als oberstes Skript ohne
# Paketkontext läuft (sonst: "attempted relative import with no known parent package").
try:
    from .cli import main
except ImportError:  # frozen / no package context
    from gardena_installer.cli import main

if __name__ == "__main__":
    sys.exit(main())
