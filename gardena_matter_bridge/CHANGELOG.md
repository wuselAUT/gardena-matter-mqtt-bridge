# Changelog

## 0.1.6
- **Fix:** Re-deploying or updating the bridge failed with "Text file busy" — the toggle service is now properly stopped before the binary is replaced and restarted afterwards.
- **Improvement:** Leaving the "Release tag" option empty now automatically uses the pinned version — no manual update needed after an add-on upgrade.

## 0.1.5
- **Fix:** MQTT settings on the gateway page could not be saved (HTTP 404) — resolved.
- **Fix:** The version number in the gateway page footer now shows the correct release version instead of "dev".
- **Fix:** The gateway page footer now shows the correct product name "GARDENA Matter & MQTT Bridge".

## 0.1.4
- **Unique pairing code per gateway** — each gateway now generates its own random, secure Matter pairing code on first start (shown in the gateway web UI), instead of a shared default code.
- **Fix:** the gateway web UI (pairing page + toggle) now installs reliably.
- **MQTT:** the measurement interval is now a graphable sensor (full sensor data).

## 0.1.3
- Robustness: the bridge starts only once a routable IPv6 address is available (reliable first pairing); stable, non-identifying device IDs and names; faster web-UI toggle.

## 0.1.2
- Generic device auto-discovery for all GARDENA devices; display of the official product names.

## 0.1.1
- Bridge deploy bundle for the add-on (binary + libraries + web UI), integrity-pinned by SHA-256.

## 0.1.0
- Initial add-on.

---

# Änderungsprotokoll (Deutsch)

## 0.1.6
- **Fix:** Re-Deploy oder Update der Bridge schlug mit „Text file busy" fehl — der Toggle-Dienst wird jetzt vor dem Ersetzen des Binarys korrekt gestoppt und danach wieder gestartet.
- **Verbesserung:** Ein leeres „Release-Tag"-Feld verwendet jetzt automatisch die gepinnte Version — kein manuelles Nachziehen nach einem Add-on-Update mehr nötig.

## 0.1.5
- **Fix:** MQTT-Einstellungen auf der Gateway-Seite konnten nicht gespeichert werden — behoben.
- **Fix:** Versionsanzeige im Footer der Gateway-Seite zeigt jetzt die korrekte Release-Version statt „dev".
- **Fix:** Footer-Name auf der Gateway-Seite auf „GARDENA Matter & MQTT Bridge" korrigiert.

## 0.1.4
- **Eindeutiger Pairing-Code pro Gateway** — jedes Gateway erzeugt jetzt beim ersten Start seinen eigenen zufälligen, sicheren Matter-Pairing-Code (im Gateway-Web-UI angezeigt), statt eines gemeinsamen Standard-Codes.
- **Fix:** Das Gateway-Web-UI (Pairing-Seite + Toggle) installiert jetzt zuverlässig.
- **MQTT:** Das Messintervall ist jetzt ein graphfähiger Sensor (vollständige Sensordaten).

## 0.1.3
- Robustheit: Die Bridge startet erst, wenn eine routbare IPv6-Adresse verfügbar ist (zuverlässiges Erstpairing); stabile, nicht-identifizierende Geräte-IDs und -Namen; schnellerer Web-UI-Toggle.

## 0.1.2
- Generische Geräte-Erkennung für alle GARDENA-Geräte; Anzeige der offiziellen Produktnamen.

## 0.1.1
- Bridge-Deploy-Bundle für das Add-on (Binary + Bibliotheken + Web-UI), per SHA-256 integritätsgepinnt.

## 0.1.0
- Erstes Add-on.
