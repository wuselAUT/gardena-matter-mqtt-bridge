# Mitwirken

Beiträge sind willkommen — das ist ein Hobby-Projekt, und es gibt viel zu tun.

## Hardware zum Testen (der hilfreichste Beitrag!)

Die Bridge ist **generisch**, kann aber nur gegen die GARDENA-Geräte *verifiziert* werden,
die wir physisch haben (Bodensensoren + ein SILENO-Mäher). Das mit Abstand Nützlichste,
was du beisteuern kannst, ist **Zugang zu weiterer GARDENA-smart-system-Hardware**, damit
sie gemappt, getestet und eingebunden werden kann:

- Water Control / Ventile, smart Power Zwischenstecker, Pressure Pumps, weitere Sensoren oder Mäher, …
- Ein solches Gerät **leihen oder überlassen**, **oder** helfen, seine **Datenschicht** auf
  deinem eigenen Gateway zu **testen und einzufangen**, damit das Mapping ergänzt werden kann.

Öffne ein Issue mit der Gerätebeschreibung (Modell — SGTIN/Seriennummer bitte **schwärzen**),
und wir stimmen uns ab.

## Weitere Wege zu helfen

- **Testberichte** aus deinem Setup (welche Geräte, was ging / was nicht). Was hineingehört,
  steht im Troubleshooting-Abschnitt der Add-on-Doku — und bitte **Secrets schwärzen**.
- **Fehlermeldungen und Fixes**, Doku-Verbesserungen, Übersetzungen.
- Build-/Test-Experimente an der Cross-Compile-Toolchain.

## Ein Problem melden — und welche Daten uns beim Fixen helfen

Das größte Hindernis beim Beheben eines Bugs ist, **nicht sehen zu können, was dein Gateway sieht**.
Die Bridge läuft lokal auf deinem Gateway — ein guter Bericht lässt uns über dein genaues Setup
nachdenken. Wenn etwas nicht funktioniert, öffne bitte ein Issue mit:

- **Versionen:** Add-on-Version (im Footer der Add-on-UI), deine Home-Assistant-Version und die
  Gateway-Firmware-Version.
- **Erwartet vs. tatsächlich** — welches Gerät, welcher Wert, und ob es Matter, MQTT oder beides
  betrifft.
- **Das Bridge-Log:** `journalctl -u gardena-matter-bridge -n 200 --no-pager` — das eigene
  Service-Log der Bridge auf dem Gateway; es zeigt Geräte-Erkennung und Fehler.
- **Bei MQTT-Problemen:** ob das Speichern der MQTT-Einstellungen geklappt hat, und — falls MQTT an
  ist — die erkannten Topics und ein Beispiel-Payload, z. B. `mosquitto_sub -h <broker> -t 'gardena/#' -v`.

> **Vorher Secrets schwärzen.** Geräte-IDs, Seriennummern / SGTINs, das Aufkleber-Passwort,
> Pairing-/Setup-Codes und Broker-Passwörter müssen entfernt oder maskiert werden, bevor du etwas einfügst.

## Ein neues GARDENA-Gerät unterstützen (seine Datenschicht einfangen)

Die Bridge ist generisch: Sie liest Schema und Live-Werte jedes Geräts direkt aus der
selbstbeschreibenden **LsDL-Dateischicht**, die `lemonbeatd` unter **`/var/lib/lemonbeatd/`** auf dem
Gateway pflegt (siehe [technische Doku](technical.de.md#datenschicht-wie-die-bridge-sensorwerte-liest)).
Genau dieses Verzeichnis brauchen wir, um ein Gerät zu mappen, das wir nicht besitzen — Water Control /
Ventile, Druckpumpen, smart-Power-Stecker, weitere Sensoren oder Mäher.

Wenn du so ein Gerät und SSH-Zugriff auf dein Gateway hast, ist das Nützlichste ein **geschwärzter
Schnappschuss dieses Verzeichnisbaums**, während das Gerät gekoppelt ist und meldet:

```bash
# 1) Struktur + Dateinamen (noch keine Werte)
find /var/lib/lemonbeatd -type f | sort

# 2) die Inhalte, damit wir Schema und Wert-Kodierung sehen
#    — vor dem Teilen jede Seriennummer / SGTIN / Adresse schwärzen
```

Häng es an ein Issue mit der Gerätebeschreibung. Damit ergänzen wir das Mapping und geben dir einen
Build zum Nachtesten — und du hast das Gerät für alle freigeschaltet, die dasselbe besitzen.

## Bitte beachten

- **Niemals Geräte-IDs, Passwörter, Pairing-/Setup-Codes oder Keys** in Issues/PRs posten — schwärzen.
- Die Bridge installiert ins **beschreibbare Overlay** des Gateways (kein Flashen, reversibel über
  die Uninstall-Skripte), bleibt aber ein Hobby-Projekt: **keine Gewähr, Nutzung auf eigenes Risiko.**
- Apple Home und Google Home wurden **nicht getestet** — andere Matter-Controller als experimentell betrachten.
- Bitte technische Diskussion mit einer Quelle belegen (Kommando-Ausgabe, Repo-Link, Commit).

## Sprache der Doku

Die Doku ist zweisprachig (Englisch / Deutsch). **Englisch ist die kanonische Quelle** — inhaltliche
Änderungen zuerst in der englischen Datei (`docs/<seite>.md`), dann in der deutschen nachziehen
(`docs/<seite>.de.md`). Die deutsche Fassung darf kurz hinterherhängen.
