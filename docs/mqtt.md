# MQTT Frontend

> **Parallel path alongside Matter** — your GARDENA devices publish their sensor values to any
> MQTT broker. Home Assistant picks them up via auto-discovery; Node-RED, Grafana, ioBroker, and
> openHAB work too.

!!! info "Status"
    The MQTT frontend is **in active development**. The Matter bridge (the main path) is fully
    functional today. The MQTT publisher is **shipped as part of the HA add-on** once the add-on
    is released. Manual deploy is described below for people who want to test early.

## Why MQTT?

Matter handles **standard device profiles well** (sensors, valves, plugs). Diagnostic values
that do not fit a Matter cluster — **radio link quality, mower runtime, error codes** — are
visible in HA as MQTT `sensor` entities instead.

Both paths can run **at the same time**: the bridge does not know about the publisher, and the
publisher does not touch the bridge.

## How it works

```
GARDENA devices ──868 MHz──▶ lemonbeatd ──(writes LsDL files)──▶ /var/lib/lemonbeatd/
                                                                         │
                                                              gardena-mqtt-publisher
                                                              (polls every 30 s via
                                                               inotify, no IPC)
                                                                         │
                                                              MQTT broker (your network)
                                                                         │
                                                           Home Assistant MQTT integration
```

The publisher **reads the same device-description files** that the Matter bridge uses. There is
no shared socket, no shared process — coexistence is structurally guaranteed.

**Home Assistant auto-discovery**: the publisher sends retained config messages on
`homeassistant/<component>/gardena_<hash>/<id>/config`. Home Assistant picks them up
automatically. No manual entity configuration needed.

## What you get per device

| GARDENA device | MQTT entities |
|---|---|
| smart Sensor / Sensor II | soil temperature, battery |
| SILENO robotic mower | status (mowing / parked / charging), battery, RF link quality, runtime, error code |
| Water Control / Irrigation Control | battery, RF link quality |
| smart Power | battery, RF link quality |
| Pump | battery, RF link quality |

Entities marked as **diagnostic** (RF link quality, runtime, error code) appear under
"Diagnostic" in the HA device card — they do not show up on dashboards by default.

## Home Assistant add-on path (recommended)

Once the HA add-on is available, the MQTT publisher is wired up through the add-on options.

In the add-on configuration:

| Option | Example | Description |
|---|---|---|
| `enable_mqtt` | `true` | Enable the MQTT publisher. Default: `false`. |
| `mqtt_broker_host` | `homeassistant.local` | Hostname or IP of your MQTT broker. |
| `mqtt_broker_port` | `1883` | Broker port. Default: `1883`. |
| `mqtt_broker_user` | `mqttuser` | Broker username (leave empty if your broker needs no auth). |
| `mqtt_broker_password` | _(your password)_ | Broker password — stored encrypted, never logged. |
| `mqtt_topic_prefix` | `gardena` | Prefix for state topics (`gardena/<hash>/<resource>/state`). |
| `mqtt_ha_prefix` | `homeassistant` | Prefix for discovery topics — match your HA MQTT integration. |

Set `enable_mqtt: true`, fill in your broker details, and click **Save → Restart**. The
publisher will be deployed to the gateway and started automatically.

!!! tip "Mosquitto in Home Assistant"
    If you use the **Mosquitto add-on** in HA, the broker host is usually
    `homeassistant.local` (port `1883`). Create a dedicated MQTT user in the
    Mosquitto add-on settings for the GARDENA publisher.

## Gateway web UI

The gateway web UI (accessible at `http://<gateway-ip>:8099/matter.html`) shows the MQTT
publisher status and lets you change the broker settings **directly on the gateway**:

1. Open `http://<gateway-ip>:8099/matter.html` in your browser.
2. The **MQTT** card shows the current publisher status (active / inactive).
3. Click the **Settings** disclosure to expand the broker configuration form.
4. Fill in host, port, username, and password — then click **Save**.
5. The gateway writes the configuration to `/etc/gardena-matter/mqtt.env` (owner-read-only)
   and restarts the publisher service.

The password is **never shown** in the UI — only whether one has been set.

## Manual install (without HA add-on)

For testing before the add-on is released, you can install the publisher directly via SSH.

**Prerequisites:** The GARDENA Matter Bridge must already be installed on the gateway.

```bash
# 1. Copy the publisher binary to the gateway
scp gardena-mqtt-publisher root@<gateway-ip>:/usr/local/lib/gardena-matter/

# 2. Copy the systemd service unit
scp mqtt-publisher/gardena-mqtt-publisher.service \
    root@<gateway-ip>:/etc/systemd/system/

# 3. Create the configuration file
ssh root@<gateway-ip> "mkdir -p /etc/gardena-matter && cat > /etc/gardena-matter/mqtt.env" <<'EOF'
MQTT_BROKER_HOST=homeassistant.local
MQTT_BROKER_PORT=1883
MQTT_BROKER_USER=mqttuser
MQTT_BROKER_PASS=<your-password>
MQTT_TOPIC_PREFIX=gardena
MQTT_HA_PREFIX=homeassistant
EOF
ssh root@<gateway-ip> "chmod 600 /etc/gardena-matter/mqtt.env"

# 4. Enable and start the service
ssh root@<gateway-ip> "systemctl daemon-reload && \
  systemctl enable gardena-mqtt-publisher.service && \
  systemctl start gardena-mqtt-publisher.service"

# 5. Check the status
ssh root@<gateway-ip> "systemctl status gardena-mqtt-publisher.service"
```

Replace `<gateway-ip>` with your gateway's IP address and `<your-password>` with your MQTT
broker password.

!!! warning "Password hygiene"
    Keep `/etc/gardena-matter/mqtt.env` owner-read-only (`chmod 600`). The file contains
    your broker password in plain text — it must not be world-readable.

## Verify in Home Assistant

After the publisher starts, it takes up to 30 seconds for the first values to arrive.

1. In HA, go to **Settings → Devices & Services → MQTT**.
2. A device **"GARDENA smart Gateway"** should appear with the configured entities.
3. Check **Developer Tools → States** and filter by `gardena` to see raw state values.

If no entities appear, check the broker logs — the publisher logs connection attempts to
`journalctl -u gardena-mqtt-publisher`.

## Uninstall

```bash
ssh root@<gateway-ip> "systemctl stop gardena-mqtt-publisher.service && \
  systemctl disable gardena-mqtt-publisher.service && \
  rm /etc/systemd/system/gardena-mqtt-publisher.service && \
  rm -f /etc/gardena-matter/mqtt.env && \
  rm -f /usr/local/lib/gardena-matter/gardena-mqtt-publisher && \
  systemctl daemon-reload"
```

This does **not** touch the Matter bridge — it keeps running as before.

## Topic reference

State topics follow the pattern `<prefix>/<hash>/<resource>/state`, where `<hash>` is a
stable 4-hex-character identifier for the device (derived from its Lemonbeat ID — no
personal data).

Discovery topics follow `<ha-prefix>/sensor/gardena_<hash>/<object-id>/config`.

Example (soil temperature sensor, device hash `a1b2`):

```
State:     gardena/a1b2/temperature/state        → 18.5
Discovery: homeassistant/sensor/gardena_a1b2/soil_temperature/config  → { ... }
```
