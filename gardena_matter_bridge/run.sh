#!/usr/bin/env bash
# run.sh — HA-Add-on "GARDENA Matter Bridge" Entrypoint
#
# Liest die Add-on-Optionen via bashio, erzeugt (einmalig) das Add-on-Keypair,
# und startet die Ingress-Status-UI. Der eigentliche Deploy laeuft NICHT
# automatisch beim Boot, sondern wird ueber die UI (Re-Deploy-Knopf) oder
# beim ersten Onboarding ausgeloest -> orchestrate.py.
#
# Credential-Modell:
#   Es gibt nur EIN Credential-Feld: device_id. Das Login-Passwort ist
#   device_id[:8] (erste 8 Zeichen, vorher getrimmt). Kein label_password mehr.
#
# Hard Constraints:
#   - device_id (= Quelle des Login-PW) NIEMALS loggen (nur Praesenz melden);
#     geht nur transient an orchestrate.py, das daraus device_id[:8] ableitet
#   - Kein Roh-SSH-Hack: nur offizieller /ssh_access_*-Flow (orchestrate.py)
#   - Bridge wird NICHT neu gebaut, nur per GitHub-Release gezogen + deployt
#
# bashio: https://github.com/hassio-addons/bashio
set -euo pipefail

# bashio ist in der hassio-addons-Base vorhanden.
# shellcheck disable=SC1091
source /usr/lib/bashio/bashio.sh 2>/dev/null || true

ADDON_DIR="/opt/gardena"
DATA_DIR="/data"                       # persistentes Add-on-Volume (HA)
KEY_DIR="${DATA_DIR}/ssh"
PRIV_KEY="${KEY_DIR}/addon_ed25519"
PUB_KEY="${PRIV_KEY}.pub"

log()  { if command -v bashio >/dev/null 2>&1; then bashio::log.info "$*"; else echo "[gardena] $*"; fi; }
warn() { if command -v bashio >/dev/null 2>&1; then bashio::log.warning "$*"; else echo "[gardena][warn] $*"; fi; }

# ── Optionen lesen (bashio; Fallback fuer lokales Testen ohne bashio) ────────
read_opt() {
    local key="$1" def="${2:-}"
    if command -v bashio >/dev/null 2>&1 && bashio::config.exists "${key}"; then
        bashio::config "${key}"
    else
        echo "${def}"
    fi
}

GATEWAY_HOST="$(read_opt 'gateway_host' '')"
DEVICE_ID="$(read_opt 'device_id' '')"
ENABLE_WEB_UI="$(read_opt 'enable_web_ui' 'true')"
DISABLE_SSH_AFTER="$(read_opt 'disable_ssh_after_deploy' 'false')"
GITHUB_REPO="$(read_opt 'github_repo' 'wuselAUT/gardena-matter-mqtt-bridge')"
RELEASE_TAG="$(read_opt 'release_tag' 'v0.1.0')"
# Leer = unauth (public). NIE loggen (R12) — nur transient an Python durchgereicht.
GITHUB_TOKEN="$(read_opt 'github_token' '')"
# device_id ist das einzige Credential: Login-Passwort = die ersten 8 Zeichen
# (Ableitung in orchestrate.py: device_id[:8]). device_id wird NIE geloggt,
# nur transient an Python durchgereicht (R12).

# enable_mqtt: aktiviert den additiven Publisher-Deploy (Matter laeuft weiter).
# mqtt_broker_host: FQDN/IP des Brokers; leer = HA-Host als Default genutzt.
# mqtt_broker_user: MQTT-Zugangsdaten (User).
# mqtt_broker_password: Secret — NIE loggen, NIE ausgeben (R12).
# mqtt_topic_prefix: Topic-Praefix (Standard "gardena").
# mqtt_ha_prefix: HA-Discovery-Prefix (Standard "homeassistant").
ENABLE_MQTT="$(read_opt 'enable_mqtt' 'false')"
MQTT_BROKER_HOST="$(read_opt 'mqtt_broker_host' '')"
MQTT_BROKER_USER="$(read_opt 'mqtt_broker_user' '')"
MQTT_BROKER_PASSWORD="$(read_opt 'mqtt_broker_password' '')"
MQTT_TOPIC_PREFIX="$(read_opt 'mqtt_topic_prefix' 'gardena')"
MQTT_HA_PREFIX="$(read_opt 'mqtt_ha_prefix' 'homeassistant')"
log "  enable_mqtt=${ENABLE_MQTT}  mqtt_broker_host=${MQTT_BROKER_HOST}  mqtt_topic_prefix=${MQTT_TOPIC_PREFIX}"
# Passwort NIEMALS loggen (R12)
if [ -n "${MQTT_BROKER_PASSWORD}" ]; then log "  mqtt_broker_password=<gesetzt>"; else log "  mqtt_broker_password=<leer>"; fi

log "GARDENA Matter & MQTT Bridge Add-on startet."
log "  gateway_host=${GATEWAY_HOST}"
# device_id NICHT vollstaendig loggen (R12); nur Praesenz melden.
if [ -n "${DEVICE_ID}" ]; then log "  device_id=<gesetzt>"; else warn "  device_id=<leer>"; fi
log "  enable_web_ui=${ENABLE_WEB_UI}  release=${GITHUB_REPO}@${RELEASE_TAG}"

# ── Add-on-Keypair erzeugen (einmalig, add-on-lokal; nur Public-Key wird gesendet) ──
mkdir -p "${KEY_DIR}"
chmod 700 "${KEY_DIR}"
if [ ! -f "${PRIV_KEY}" ]; then
    log "Erzeuge Add-on-SSH-Keypair (ed25519, add-on-lokal) ..."
    ssh-keygen -t ed25519 -N "" -C "gardena-matter-addon" -f "${PRIV_KEY}" >/dev/null
    chmod 600 "${PRIV_KEY}"
    log "Keypair erzeugt: ${PUB_KEY} (nur Public-Key wird ans Gateway gesendet)"
else
    log "Add-on-Keypair vorhanden (wiederverwendet, OTA-fest hinterlegt)."
fi

# Fragt http://supervisor/addons/self/info ab; SUPERVISOR_TOKEN ist vom HA-Framework
# im Container gesetzt. Fehlertolerant: bei Netzwerkfehler oder leerem Ergebnis
# bleibt ADDON_VERSION ungesetzt -> load_addon_version() greift auf config.yaml-Fallback.
# SUPERVISOR_TOKEN wird NIEMALS geloggt (R12).
_api_version="$(curl -sSL \
    -H "Authorization: Bearer ${SUPERVISOR_TOKEN}" \
    http://supervisor/addons/self/info 2>/dev/null \
    | jq -r '.data.version // empty' 2>/dev/null || true)"
if [ -n "${_api_version}" ]; then
    export ADDON_VERSION="${_api_version}"
    log "  ADDON_VERSION=${ADDON_VERSION} (Supervisor-API)"
else
    log "  ADDON_VERSION: Supervisor-API nicht erreichbar; config.yaml-Fallback greift."
fi

# ── Ingress-Status-UI starten () ───────────────────────────────────────
# Die UI ruft orchestrate.py fuer Deploy/Status auf. Sie laeuft im Vordergrund
# (Add-on-Hauptprozess). Onboarding/Deploy wird ueber die UI ausgeloest.
if [ "${ENABLE_WEB_UI}" = "true" ]; then
    log "Starte Ingress-Status-UI auf :8099 ..."
    export GARDENA_GATEWAY_HOST="${GATEWAY_HOST}"
    # device_id transient an Python (Secret) — NIE geloggt; orchestrate.py leitet
    # daraus device_id[:8] als Login-Passwort ab.
    export GARDENA_DEVICE_ID="${DEVICE_ID}"
    export GARDENA_GITHUB_REPO="${GITHUB_REPO}"
    export GARDENA_RELEASE_TAG="${RELEASE_TAG}"
    # github_token transient an Python (Secret) — NIE geloggt.
    export GARDENA_GITHUB_TOKEN="${GITHUB_TOKEN}"
    export GARDENA_DISABLE_SSH_AFTER="${DISABLE_SSH_AFTER}"
    export GARDENA_PRIV_KEY="${PRIV_KEY}"
    export GARDENA_PUB_KEY="${PUB_KEY}"
    export GARDENA_ADDON_DIR="${ADDON_DIR}"
    export PYTHONPATH="${ADDON_DIR}"
    # Broker-Passwort NIE loggen (R12) — nur als Env-Var an Python weitergeben.
    export GARDENA_ENABLE_MQTT="${ENABLE_MQTT}"
    export GARDENA_MQTT_BROKER_HOST="${MQTT_BROKER_HOST}"
    export GARDENA_MQTT_BROKER_USER="${MQTT_BROKER_USER}"
    export GARDENA_MQTT_BROKER_PASSWORD="${MQTT_BROKER_PASSWORD}"
    export GARDENA_MQTT_TOPIC_PREFIX="${MQTT_TOPIC_PREFIX}"
    export GARDENA_MQTT_HA_PREFIX="${MQTT_HA_PREFIX}"
    exec python3 "${ADDON_DIR}/web_ui.py"
else
    warn "enable_web_ui=false -> keine UI. Add-on bleibt im Leerlauf (Onboarding via UI deaktiviert)."
    while true; do sleep 3600; done
fi
