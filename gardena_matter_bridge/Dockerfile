#
# Echte HA-Add-on-Base (ghcr.io/hassio-addons/base) -> bringt bashio (inkl.
# bash/curl/jq) mit. BUILD_FROM wird vom HA-Supervisor je Architektur eingesetzt
# (build.yaml).
#
# 15.0.7 ist veraltet (kein BUILD_FROM-Fallback mehr seit Supervisor 2026.04).
ARG BUILD_FROM=ghcr.io/hassio-addons/base:18.2.0
# hadolint ignore=DL3006
FROM ${BUILD_FROM}

# BUILD_VERSION wird vom offiziellen Image-Builder (GitHub home-assistant/builder) gesetzt,
# Deshalb wird ADDON_VERSION nicht mehr per ENV aus BUILD_VERSION gesetzt (leere Env-Var
# bei lokalem Build wuerde load_addon_version() mit leerem Wert beenden, kein Fallback).
# Die Version wird zur Laufzeit aus zwei build-unabhaengigen Quellen ermittelt:
#   1. run.sh fragt http://supervisor/addons/self/info (SUPERVISOR_TOKEN) ab.
#   2. Fallback: load_addon_version() liest /opt/gardena/config.yaml (COPY unten).
# ARG BUILD_VERSION + LABEL duerfen bleiben (fuer offizielle Builds korrekt).
ARG BUILD_VERSION

# Add-on braucht NUR: openssh-client (ssh/scp fuer Deploy) + python3 (Orchestrator
# + Ingress-UI). bash/curl/jq bringt die bashio-Base bereits mit -> weggelassen.
#
# des libssl3-Pin-Konflikts (Base pinnt libssl3=3.5.4, openssl-3.5.7 braucht
# libssl3=3.5.7) -> apk-Build brach hart ab. python3/openssh-client bauen sauber
# (sie brauchen nur libssl3>=3.3.0, vom Base erfuellt). Die Release-Integritaet
# laeuft jetzt ueber SHA256-Hash-Pinning (python hashlib, pure-python, konfliktfrei)
# als primaeres Gate -> siehe orchestrate.py.
# hadolint ignore=DL3018
RUN apk add --no-cache \
    openssh-client \
    python3

# Add-on-Dateien
COPY run.sh /run.sh
COPY orchestrate.py /opt/gardena/orchestrate.py
COPY status.py /opt/gardena/status.py
COPY web_ui.py /opt/gardena/web_ui.py
COPY web/ /opt/gardena/web/
# Die drei vorhandenen Install-Skripte (werden NICHT neu gebaut, nur deployt).
COPY install-scripts/ /opt/gardena/install-scripts/
# Hash-Pin-Quelle: orchestrate.py liest sie zur Laufzeit unter
# /opt/gardena/bridge-release.lock (RELEASE_LOCK_PATH neben dem Modul). MUSS ins
# Image — sonst fail-closed "bridge-release.lock nicht lesbar".
COPY bridge-release.lock /opt/gardena/bridge-release.lock
# liest os.path.dirname(__file__)/config.yaml = /opt/gardena/config.yaml, falls
# ADDON_VERSION-Env (Supervisor-API via run.sh) nicht gesetzt ist.
COPY config.yaml /opt/gardena/config.yaml
RUN chmod a+x /run.sh

# Add-on-Metadaten (HA liest Labels)
LABEL \
  io.hass.name="GARDENA Matter & MQTT Bridge" \
  io.hass.description="Installiert die GARDENA Matter & MQTT Bridge auf dem Gateway - ohne SSH, ohne Bauen." \
  io.hass.type="addon" \
  io.hass.version="${BUILD_VERSION}"

CMD [ "/run.sh" ]
