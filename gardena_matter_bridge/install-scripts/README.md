# install-scripts/ — Install Scripts

These are the three install scripts used by the add-on to deploy the bridge
components to your gateway:

- `install_bridge.sh`     — deploys the Matter bridge binary and service
- `install_web_ui.sh`     — deploys the web UI and OTA restore service
- `install_restore.sh`    — sets up the persistent restore source

The add-on **orchestrates** these scripts (runs them container-locally via SSH/scp
to the gateway) — it does not build anything new.

## EN / DE

**EN:** These scripts are copied into the add-on container image during build.
The add-on runs them with the gateway's IP, the SSH key, and the unpacked bundle
paths as environment variables. They scp the files to the gateway themselves.

**DE:** Diese Skripte werden beim Build in das Add-on-Container-Image kopiert.
Das Add-on führt sie mit der Gateway-IP, dem SSH-Key und den entpackten Bundle-Pfaden
als Umgebungsvariablen aus. Sie übertragen die Dateien per scp selbst auf das Gateway.
