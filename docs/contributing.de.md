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
