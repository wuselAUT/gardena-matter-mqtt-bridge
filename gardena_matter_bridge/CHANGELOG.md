# Changelog

## 0.1.10
- **Fix:** The automatic storage clean-up during deploy now works reliably on the gateway as well. Previously, the clean-up ran but freed no space (the gateway's minimal shell does not support the `find -delete` flag), causing the subsequent file transfer to fail with "No space left on device". The deploy now removes leftover files using a compatible method and logs the freed space.

## 0.1.9
- **Fix:** Re-deploying failed when the gateway storage was full — the add-on now checks first whether a secure connection is already available and, if so, skips the redundant connection setup that would have failed. The deploy then runs normally and cleans up the storage itself.

## 0.1.8
- **Fix:** Repeated deploying accumulated unused library files on the gateway (names ending with a stray `"` character), eventually filling the flash and causing the next deploy to fail with "No space left on device". The deploy now automatically cleans up any such leftover files before writing, and no longer creates new ones.

## 0.1.7
- **Fix:** The MQTT switch on the gateway page now switches off and on reliably and permanently (survives a reboot). Previously, MQTT could come back on its own after being switched off.
- **Improvement:** The gateway page footer now shows both the add-on version and the bridge version ("Add-on vX · Bridge vY").

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

## 0.1.10
- **Fix:** Die automatische Speicher-Aufräumung beim Deploy funktioniert jetzt auch auf dem Gateway zuverlässig. Bisher lief die Aufräumung durch, gab aber keinen Speicher frei (die minimale Shell des Gateways unterstützt den `find -delete`-Flag nicht), sodass die anschließende Dateiübertragung mit „Kein Speicherplatz mehr" scheiterte. Der Deploy entfernt Überreste jetzt mit einer kompatiblen Methode und protokolliert den freigewordenen Platz.

## 0.1.9
- **Fix:** Ein erneuter Deploy schlug fehl, wenn der Gateway-Speicher voll war — das Add-on prüft jetzt zuerst, ob bereits eine sichere Verbindung besteht, und überspringt in diesem Fall das redundante Verbindungs-Setup, das sonst fehlgeschlagen wäre. Der Deploy läuft danach normal durch und räumt den Speicher selbst auf.

## 0.1.8
- **Fix:** Wiederholtes Deployen häufte ungenutzte Bibliotheksdateien auf dem Gateway an (Namen mit einem überschüssigen `"`-Zeichen), bis der Flash voll war und der nächste Deploy mit „Kein Speicherplatz mehr" fehlschlug. Der Deploy räumt solche Überreste jetzt automatisch auf, bevor er schreibt, und erzeugt keine neuen fehlerhaften Dateien mehr.

## 0.1.7
- **Fix:** Der MQTT-Schalter auf der Gateway-Seite schaltet jetzt zuverlässig dauerhaft aus/ein (bleibt auch nach einem Neustart in dem gesetzten Zustand). Bisher konnte MQTT nach dem Ausschalten von selbst wieder aktiv werden.
- **Verbesserung:** Der Footer der Gateway-Seite zeigt jetzt sowohl die Add-on-Version als auch die Bridge-Version an („Add-on vX · Bridge vY").

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
