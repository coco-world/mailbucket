# MailBucket

**Durchsucht Mailboxes nach Suchbegriffen und legt Suchbegriffordner an.**

MailBucket durchsucht E-Mail-Archive nach frei wählbaren Begriffen und exportiert
Treffer als einzelne, chronologisch nummerierte PDFs in passende Ordner („Buckets“).
Die Oberfläche läuft im Browser auf `http://127.0.0.1:8080`.
Python 3.11 oder neuer ist erforderlich. Kein Docker, Node-Build, Datenbankserver,
Konto, API-Key oder Cloud-Dienst nötig.

## Schnellstart (Windows PowerShell)

Repository: [coco-world/mailbucket](https://github.com/coco-world/mailbucket).

```powershell
git clone https://github.com/coco-world/mailbucket.git
cd mailbucket
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
mailbucket
```

> Das Repository wird nicht in den `.venv`-Ordner geklont. `.venv` enthält ausschließlich
> die isolierte Python-Umgebung und installierte Python-Pakete.

## Funktionen

- Mehrere auswählbare Quellen gemeinsam durchsuchen.
- MBOX, einzelne EMLs, rekursive EML-/MBOX-Verzeichnisse, Maildir mit Unterordnern.
- Takeout: ZIP, TAR, TAR.GZ und TGZ direkt einlesen; beliebige verschachtelte
  `.mbox`-Dateinamen, Gmail-Labels aus `X-Gmail-Labels`.
- Ein Suchbegriff pro Zeile; alternativ UTF-8-TXT oder validierte CSV mit Bucket-Zuordnungen.
- Gruppierte Suchfelder mit einzeln auswählbarem Betreff, Body, Absendername/-Adresse,
  Empfängern, CC/BCC, Anhangnamen, Labels, Message-ID, Ordnerpfad und Antwort-Headern.
- Reine Zahlenbegriffe treffen nur außerhalb längerer Zahlenfolgen.
- Optionale lokale Anhangsuche in Text, HTML und textbasierten PDFs; Fundstellen im Manifest.
- Dry Run zählt Treffer und Duplikate, ohne Ausgabeordner oder PDFs anzulegen.
- Chronologische Sortierung, stabile Nummerierung, optional Datum im Dateinamen.
- PDFs im Outlook-Memo-Stil mit einzeln wählbaren Maildaten und technischen Metadaten.
- Konfigurierbare Fußzeilen einschließlich finaler Seitenzahl und Exportdateiname.
- PDF-Originalseiten anhängen, JPEG/PNG proportional einfügen, optionale Trennblätter.
- Originalanhänge bytegetreu speichern, sichere Namen ohne stilles Überschreiben.
- Bucket-Ordner nur bei Treffern; je Ordner eine gleichnamige, Excel-taugliche CSV.
- Freier, gespeicherter Kopftext auf jeder exportierten Mail-PDF.
- Manifest, SHA-256-Hashes, Laufparameter und Fehlerprotokoll.
- Fortschrittsanzeige mit Datenmenge, Laufzeit, Durchsatz und geschätzter Restzeit.
- Persistente lokale SQLite-/FTS5-Indizes pro Quelle; aktuelle Indizes werden bei
  späteren Suchen wiederverwendet, ohne das gesamte Archiv erneut zu parsen.
- Einstellbare Parallelität für Suche (1–8 Worker) und PDF-Ablage (1–4 Worker).
- Lokales Logo, gespeicherte Such-/Exportoptionen und Auswahlhilfen für PDF-Einstellungen.

**Screenshot-Platzhalter:** Hier kann ein Screenshot der lokalen Oberfläche mit
rein synthetischen Daten ergänzt werden.

## Datenschutz und lokale Verarbeitung

Alle Mailinhalte bleiben auf dem Computer. Die Anwendung nutzt keine Telemetrie,
externen KI-Dienste oder Mail-APIs. NiceGUI liefert die Oberfläche lokal aus.
Die Installation lädt Python-Pakete aus PyPI; danach braucht der Betrieb keine
Internetverbindung. Auch TXT-/CSV-„Uploads“ gehen nur an den lokalen Prozess.
Große Archive werden direkt über ihre lokalen Dateipfade geöffnet.

Der Server bindet ausschließlich an Loopback (`127.0.0.1`, `localhost` oder `::1`).
Er ist für einen vertrauenswürdigen lokalen Benutzer gedacht, nicht für öffentliche
Server oder Mehrbenutzer-Hosting. Es gibt bewusst kein Login. Nicht per Reverse Proxy
im Netz freigeben. Beenden mit **Strg+C** im Terminal.

HTML wird nur in Text umgewandelt, nie als Mail-HTML im Browser ausgeführt.
Scripts/Styles werden entfernt, externe Bilder werden nicht geladen. Anhänge
werden nie ausgeführt. Aus ZIP/TAR werden ausschließlich reguläre MBOX-Dateien
in einen temporären, intern benannten Speicher kopiert; absolute Pfade, Traversal
und Links werden verworfen. PDF-Seiten werden übernommen; interaktive Annotationen
und Seitenaktionen werden im exportierten Dokument entfernt. Originalanhänge bleiben unverändert.

Temporäre entpackte Mailboxen und Treffer liegen im lokalen System-Tempverzeichnis
und werden nach dem Lauf gelöscht. Bei Prozessabbruch oder Stromausfall können
Reste verbleiben. Normales Löschen ist kein sicheres Überschreiben des Datenträgers.

## Unterstützte Formate

| Quelle | Version 0.2 |
| --- | --- |
| `.mbox` | Ja, auch mehrere Dateien in einem Verzeichnis |
| `.eml` / EML-Ordner | Ja, rekursiv, Groß-/Kleinschreibung der Erweiterung egal |
| Maildir | Ja, `cur`, `new`, `tmp` und Unter-Maildirs; `tmp` wird nicht importiert |
| Takeout `.zip`, `.tar`, `.tar.gz`, `.tgz` | Ja, automatische rekursive MBOX-Erkennung |
| Entpacktes Takeout-Verzeichnis | Ja, rekursive MBOX-Suche |
| `.emlx`, `.msg`, `.pst`, `.ost` | Adapter vorgesehen, noch kein Import in 0.2 |

Entpackte MBOX-Dateien erscheinen im Manifest als `MBOX`; bei Archivimporten
stehen `Google Takeout`, Archivpfad und interner Memberpfad getrennt im Manifest.
Die genaue Google-Verzeichnisstruktur wird nicht vorausgesetzt.

## Installation unter Windows

Python 3.11+ und Git installieren, dann Voraussetzungen prüfen:

```powershell
py --version
git --version
cd C:\Users\DEINNAME\Documents
git clone https://github.com/coco-world/mailbucket.git
cd mailbucket
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Falls PowerShell die Aktivierung blockiert, nur für diese Sitzung freigeben:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Installieren und starten:

```powershell
python -m pip install --upgrade pip
pip install -e .
mailbucket
```

Browser: `http://127.0.0.1:8080`. Wenn kein Browser aufgeht, die Adresse selbst öffnen.
Später erneut starten:

```powershell
cd C:\Users\DEINNAME\Documents\mailbucket
.\.venv\Scripts\Activate.ps1
mailbucket
```

Update innerhalb der aktivierten Umgebung:

```powershell
git pull
pip install -e .
mailbucket
```

Nach Beenden der Anwendung:

```powershell
deactivate
```

CMD statt PowerShell: `.venv\Scripts\activate.bat` verwenden.
Ein bereits vorhandener lokaler Projektordner muss nicht noch einmal geklont werden.

## Installation unter macOS

Python 3.11+ und Git vorausgesetzt (das alte macOS-System-Python genügt eventuell nicht):

```bash
git clone https://github.com/coco-world/mailbucket.git
cd mailbucket
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
mailbucket
```

## Installation unter Linux

Python 3.11+, Git und das zur Python-Version passende `venv`-Paket benötigen.
Unter Debian/Ubuntu heißt Letzteres beispielsweise `python3-venv`.

```bash
git clone https://github.com/coco-world/mailbucket.git
cd mailbucket
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
mailbucket
```

Später unter macOS/Linux: in den Projektordner wechseln,
`source .venv/bin/activate` und `mailbucket` ausführen. Update mit `git pull`
und `pip install -e .`. Die Umgebung mit `deactivate` verlassen.

## Start und Bedienung

```bash
mailbucket
# Gleichwertig:
python -m mailbucket
# Ohne automatischen Browserstart oder mit anderem lokalen Port:
mailbucket --host 127.0.0.1 --port 8081 --no-browser
```

1. **Quelle hinzufügen**: Datei anklicken oder in einen Ordner navigieren und
   **Diesen Ordner auswählen**. Der Pfad kann direkt eingegeben werden; das hilft
   auch bei Windows-Laufwerkswechseln. Mehrere Quellen hinzufügen und per Checkbox auswählen.
2. Suchbegriffe eingeben, **ein Begriff pro Zeile**. Leere Zeilen werden ignoriert,
   äußere Leerzeichen entfernt. Mehrere Wörter in einer Zeile bilden einen Suchbegriff.
3. Suchfelder und Anhangoptionen festlegen.
4. Ausgabeordner wählen oder einen neuen Pfad eingeben. Laufname z. B. `260915_Lauf1`.
5. **Dry Run** ausführen und Treffer/Fehler prüfen.
6. **Export starten**. Der Export liest die aktuellen Quellen erneut; Änderungen seit
   dem Dry Run können deshalb zu anderen Trefferzahlen führen.
7. Ergebnis, Protokoll und **Ausgabeordner öffnen** nutzen.

Während eines Laufs sind Startbuttons und Formular gesperrt. Die Fortschrittsanzeige
zeigt die Phase, aktuelle Mailbox, Suchbegriffe, geprüfte Nachrichten, gefundene Mails,
exportierte PDFs, verarbeitete Datenmenge, Laufzeit, Durchsatz und geschätzte Restzeit.
Alle ausgewählten Begriffe werden pro Nachricht gemeinsam geprüft; beim Export stehen
die Begriffe der gerade abgeschlossenen Nachricht in der Anzeige. Für MBOX, EML,
Maildir und ZIP wird der Quelldatenumfang ohne vollständigen Vorab-Scan ermittelt.
Bei komprimierten TAR/TGZ-Streams bleibt der Balken beim Einlesen unbestimmt, zeigt
aber weiterhin Nachrichtenzahl, gelesene Datenmenge und Laufzeit. Die Restzeit ist eine
laufend aktualisierte Schätzung und erscheint erst, wenn genügend Messdaten vorliegen.
Bei der PDF-Erzeugung bezieht sich die Prozentanzeige auf alle Bucket-PDFs.
Scrollen, Fortschritt und Ergebnisansicht bleiben bedienbar.
Ein bestehender Laufordner erzeugt einen Fehler und wird niemals wiederverwendet.
Nach erfolgreichem Export schlägt das UI einen freien Namen mit numerischem Suffix vor.

## Leistung und Parallelität

Unter **08 Leistung** lassen sich parallele Such- und Ablage-Worker einstellen.
Standardmäßig verwendet MailBucket abhängig vom Rechner bis zu vier Such- und zwei
PDF-Worker. Jeder Worker läuft als eigener Prozess, sodass CPU-intensive MIME-, Such-
und PDF-Arbeit tatsächlich mehrere Prozessorkerne nutzen kann. Suche und Export bleiben
getrennte Phasen, damit die chronologische
Sortierung und stabile Bucket-Nummerierung erhalten bleiben. Innerhalb einer Phase
werden Nachrichten beziehungsweise Treffer parallel verarbeitet; Manifest und Bucket-CSV
werden anschließend weiterhin in deterministischer Reihenfolge geschrieben.

Mehr Worker sind nicht automatisch schneller. Große Anhänge, PDF-Textsuche und
PDF-Erzeugung benötigen zusätzlichen Arbeitsspeicher, während HDDs durch parallele
Zugriffe langsamer werden können. Für SSD-Systeme sind 4/2 ein sinnvoller Startwert;
bei knappem RAM oder HDD eher 2/1. Die interne Warteschlange ist begrenzt, sodass auch
bei großen Archiven nur eine kleine Anzahl Nachrichten gleichzeitig vorgeladen wird.

## Persistenter lokaler Suchindex

MailBucket legt für jede ausgewählte Quelle einen eigenen SQLite-Index mit FTS5 an.
Beim ersten Lauf wird die Quelle einmal vollständig eingelesen. Spätere Dry Runs und
Exporte verwenden den vorhandenen Index, solange die Quelle unverändert ist. Dadurch
entfallen das wiederholte Parsen der kompletten MBOX und die wiederholte Textextraktion
aus unterstützten Anhängen. Beim Export werden anschließend nur die gefundenen
Originalnachrichten aus MBOX, EML, Maildir oder Takeout geladen.

Jeder Index ist fest an eine kanonische absolute Quelle und ihren Typ gebunden. Eine
SHA-256-basierte `source_id` verhindert, dass zwei gleichnamige Dateien in verschiedenen
Ordnern denselben Index verwenden. Zusätzlich speichert MailBucket einen Fingerprint:
bei Dateien unter anderem Größe, Nanosekunden-Änderungszeit sowie Hashes vom Anfang und
Ende; bei Verzeichnissen eine sortierte Liste aus relativem Pfad, Größe und
Änderungszeit. Ändert sich die Quelle oder die Indexstruktur, wird der Zustand
**veraltet** und der Index vollständig neu aufgebaut. Ein veralteter Index wird nie
stillschweigend für eine Suche verwendet.

Der Index enthält normalisierte Mailfelder, Suchtexte, Hashes, Quellpositionen und den
extrahierten Text unterstützter Anhänge. Die Binärdaten der Anhänge werden nicht
dauerhaft in SQLite dupliziert. FTS5 dient als schneller Kandidatenfilter; jeder
Kandidat wird mit derselben exakten Matching-Logik wie beim klassischen Scan geprüft.
Kurze, nicht zuverlässig per FTS abbildbare oder nicht-ASCII-Suchen werden korrekt auf
den gespeicherten normalisierten Texten geprüft. Reine Zahlenbegriffe behalten ihre
Zifferngrenzen.

Der Aufbau erfolgt in einer temporären `.building.sqlite3`-Datei. Erst nach erfolgreicher
Integritätsprüfung und erneuter Fingerprint-Prüfung ersetzt sie atomar den bisherigen
Index. Ein Abbruch oder Fehler lässt einen zuvor gültigen Index bestehen; die Anwendung
fällt bei Bedarf auf den klassischen Scan zurück. Fortschritt, verarbeitete Datenmenge,
Durchsatz und Restzeitschätzung werden auch während des Indexaufbaus angezeigt.

In **01 Quellen** zeigt jede Quelle den Zustand *nicht indexiert*, *aktuell*, *veraltet*,
*wird aufgebaut* oder *Fehler*. Dort lassen sich Indizes erstellen, aktualisieren,
neu aufbauen und löschen. **Index automatisch erstellen bzw. aktualisieren** ist
standardmäßig aktiv und wird mit den übrigen Einstellungen gespeichert. Unter
**Indexverwaltung** sind auch Indizes momentan nicht angeschlossener Quellen sichtbar.
Das Löschen eines Index entfernt nur die lokale SQLite-Datei, niemals das Mailarchiv.

Speicherorte der Indizes:

- Windows: `%APPDATA%\MailBucket\indexes\<source_id>.sqlite3`
- macOS: `~/Library/Application Support/MailBucket/indexes/<source_id>.sqlite3`
- Linux: `$XDG_CONFIG_HOME/MailBucket/indexes/<source_id>.sqlite3` bzw.
  `~/.config/MailBucket/indexes/<source_id>.sqlite3`

Für portable Installationen und Tests kann `MAILBUCKET_INDEX_PATH` auf ein anderes
Indexverzeichnis gesetzt werden. Die Indizes enthalten lokale Mailinhalte und
Quellpfade und sollten deshalb wie die Archive selbst geschützt und nicht ungeprüft
weitergegeben werden. MailBucket überträgt diese Daten nicht ins Netzwerk.

## Suchfelder und Fundstellen

Standardmäßig sind Betreff, Body, Absendername, Absender-E-Mail-Adresse und An aktiviert.
CC, BCC, Gmail-Labels, Anhangnamen/-inhalte, Message-ID, Mailbox-/Ordnerpfad sowie
Reply-To, In-Reply-To und References sind optional. „Message-ID / Internet Message ID“
ist eine gemeinsame Option, weil beide Bezeichnungen denselben Header meinen.
BCC ist nur durchsuchbar, wenn es in der exportierten Nachricht vorhanden ist.
Outlook-Ordner/Kategorien und interne UIDs werden mangels entsprechender Importer nicht angeboten.

Anhanginhalte werden nur bei aktivierter Option extrahiert: Textdateien (UTF-8,
UTF-16 mit BOM, ersatzweise Windows-1252), HTML und vorhandener PDF-Text. Keine OCR,
Office- oder Archiv-Inhaltssuche. Originalbytes bleiben unverändert. Die Suche ist
pro Anhang auf 20 MiB, 500 PDF-Seiten und 2 Millionen extrahierte Zeichen begrenzt.
Überschreitungen sowie beschädigte/verschlüsselte Anhänge erscheinen im Protokoll;
bei Erreichen einer Grenze kann ein Treffer außerhalb des geprüften Bereichs fehlen.
`match_locations` im Manifest nennt für jeden Begriff die tatsächlichen Suchfelder,
bei Anhanginhalten zusätzlich den Anhangnamen.

## PDF-Inhalt, Fußzeile und gespeicherte Einstellungen

Ein frei eingebbarer Kopftext erscheint auf Wunsch oben auf jeder exportierten Mail-PDF
und wird mit den übrigen Optionen gespeichert. Der Standard-Memo-Kopf enthält Von,
Gesendet, An, Cc, Betreff und eine kompakte Anlagenliste. Danach folgt der Nachrichtentext
mit engem Zeilenabstand. Jede dieser Angaben sowie BCC kann
einzeln ausgeblendet werden. Optionale technische Angaben (Herkunft, Message-ID,
Labels, Antwort-Header) und MailBucket-Daten (Treffer, Fundstellen, Exportzeitpunkt,
Version) stehen in einem abgegrenzten Bereich **MailBucket-Metadaten** hinter dem Text.
„Alle auswählen“, „Alle abwählen“ und „Standard wiederherstellen“ erleichtern die Auswahl.
Die Sichtbarkeitseinstellungen bearbeiten weder den Nachrichtentext noch den Inhalt
übernommener Originalanhänge; dort vorhandene Werte können daher weiterhin sichtbar sein.
Das Manifest dokumentiert unabhängig von der PDF-Auswahl weiterhin die Herkunft und Hashes.

Die Fußzeile ist vollständig abschaltbar. Einzeln wählbar sind MailBucket, Exportdatum,
Maildatum, Suchbegriffe, Mailbox, Seite/Gesamtseiten und tatsächlicher Exportdateiname.
Standard: MailBucket und Seitenzahl. Die Seitenzählung erfolgt nach der Integration
aller Anhänge. Es wird unter jeder Seite ein zusätzlicher Bereich angelegt, damit
kein Anhanginhalt überdeckt wird. **Dadurch wird die exportierte Seite etwas höher**;
beim Drucken auf A4 ggf. „An Seite anpassen“ verwenden. Originalanhänge im
attachments-Verzeichnis behalten ihre ursprünglichen Maße und Bytes. Lange Fußzeilen
brechen um; einzelne Werte werden auf 240 Zeichen begrenzt. Vollständige Werte stehen
weiterhin in Mail-Metadaten bzw. Manifest. Bereits im Original-PDF enthaltene Fußzeilen bleiben erhalten.

„Einstellungen speichern“ oder der Start eines Laufs speichert Suchfelder, Duplikat-,
Anhang- und PDF-Optionen lokal für den nächsten Start. Quellen, Suchbegriffe und
Ausgabepfade werden nicht gespeichert. Speicherorte:

- Windows: `%APPDATA%\MailBucket\settings.json`
- macOS: `~/Library/Application Support/MailBucket/settings.json`
- Linux: `$XDG_CONFIG_HOME/MailBucket/settings.json` bzw. `~/.config/MailBucket/settings.json`

Für portable Installationen und Tests überschreibt `MAILBUCKET_SETTINGS_PATH` den
vollständigen Dateipfad. Ungültige Einstellungen werden protokolliert und durch
Standards ersetzt. Das mitgelieferte Logo wird aus den Paket-Assets geladen; bei
fehlendem Paketlogo wird im Projektordner `assets` nach einem Logo gesucht.

## Google Takeout

1. Google Takeout im eigenen Browser öffnen.
2. Gmail/Mail auswählen und einen Export erzeugen.
3. Exportdateien herunterladen.
4. ZIP/TGZ muss **nicht** manuell entpackt werden.
5. Archiv direkt als Quelle in MailBucket auswählen; bei mehreren Exportteilen jede Datei hinzufügen.
6. MailBucket sucht automatisch nach allen `.mbox`-Dateien, unabhängig von Namen und Ordnerstruktur.
7. Gmail-Labels werden berücksichtigt, wenn `X-Gmail-Labels` vorhanden ist.

Bereits entpackte Takeout-Ordner können ebenfalls direkt ausgewählt werden.
Die Archive selbst werden nicht verändert. Genügend freien Speicher für die größte
entpackte Mailbox, temporäre Treffer und fertige PDFs vorsehen.

## TXT und CSV

TXT: UTF-8, ein Suchbegriff pro Zeile. CSV: UTF-8 (BOM erlaubt), Komma als
Trennzeichen und exakt diese Kopfzeile:

```csv
term,bucket
345678,345678
Mustermann GmbH,Mustermann
Herr Mustermann,Mustermann
"Müller, GmbH",Müller
```

- `term` = Suchtext.
- `bucket` = gewünschter Ausgabeordnername.
- Mehrere Begriffe dürfen demselben Bucket zugeordnet sein; jede Mail wird dort nur einmal abgelegt.
- Ein Treffer in verschiedenen Buckets erzeugt eine PDF-Kopie pro Bucket.
- Leere Werte, zusätzliche Spalten und kaputte CSV-Syntax werden mit Zeilenhinweis abgelehnt.
- Änderungen im Textfeld nach CSV-Import setzen die CSV-Zuordnung zurück.
- Suchbegriffe werden als wörtlicher Text behandelt, keine Regex-Auswertung.

Bucketnamen werden für Windows/macOS/Linux bereinigt. Bei Namenskollisionen,
auch durch Groß-/Kleinschreibung, wird ein stabiler Hashsuffix ergänzt. Die Zuordnung
zwischen Original-Bucket und Verzeichnis steht in `_run.json`.

Reine Ziffernbegriffe verwenden Zifferngrenzen: `123` trifft `A123B`, aber nicht `91235`.

## Sortierung und Duplikate

Zuerst sammeln, danach sortieren: älteste Mail zuerst. Zeitzonen werden bei der
Sortierung berücksichtigt. Datumswerte ohne Zeitzone gelten als UTC. Fehlende oder
ungültige Datumswerte kommen ans Ende (`date_status` im Manifest).
Bei gleichem Zeitpunkt entscheiden Message-ID, Quelldatei, Quellindex und zuletzt
Quellordner. Nummerierung ist immer mindestens vierstellig, unabhängig von der Archivposition.
Optionale Dateinamen-Zeitstempel verwenden die Zeitzone des ursprünglichen Headers.

Duplikate werden primär über die Message-ID erkannt. Fehlt sie, wird ein stabiler
SHA-256 über normalisierte Metadaten, Text und Anhanghashes gebildet. Die erste
Kopie in der ausgewählten Quellenreihenfolge gewinnt. Unterschiede in Labels oder
Inhalten späterer Kopien mit gleicher Message-ID werden nicht zusammengeführt.
Bei Bedarf Duplikatentfernung ausschalten. Treffer derselben Mail in verschiedenen
Buckets sind ausdrücklich erlaubt. Der Dry Run zählt auch bei ausgeschalteter
Entfernung die erkannten Duplikate.

## Ausgabe und Anhänge

```text
260915_Lauf1/
├── _manifest.csv
├── _run.json
├── _run.log
├── 345678/
│   ├── 345678.csv
│   ├── 345678_0001.pdf
│   ├── 345678_0002.pdf
│   └── attachments/
│       └── 345678_0001/
│           ├── Rechnung.pdf
│           └── Angebot.xlsx
└── Mustermann/
    ├── Mustermann.csv
    └── Mustermann_0001.pdf
```

Mit Zeitstempel beispielsweise `345678_0001_20260915_215700.pdf`.
Standard-PDFs werden einmal pro Mail gerendert und in die passenden Buckets kopiert.
Wenn Treffer/Fundstellen oder bucketabhängige Fußzeilen gewählt sind, enthält jede PDF
die Begriffe ihres Buckets und den passenden Dateinamen. Reine Fußzeilenvarianten nutzen
denselben gerenderten Memo-Inhalt wieder. Trennblätter übernehmen Betreff bzw. Message-ID
nur bei aktivierter PDF-Auswahl dieser Felder.

PDF-Anhangmodi:

- **Anhängen**: Originalseiten ohne Rasterisierung übernehmen.
- **Separat**: PDF-Anhang als Original unter `attachments/` speichern.
- **Beides**: Seiten integrieren und Original speichern.

JPEG/PNG können proportional als Seiten eingefügt werden. Andere Formate werden
mit einem Hinweis dokumentiert. Mit **Originalanhänge zusätzlich speichern** bleiben
auch DOCX/XLSX/ZIP usw. verfügbar; ohne diese Option nennt der Hinweis ausdrücklich,
dass die Datei nicht gespeichert wurde. Bei ausgeschalteter Anhangverarbeitung bleibt
nur die optional ausgewählte Anlagenliste im Mail-PDF. Defekte oder verschlüsselte PDFs werden protokolliert;
andere Mails werden weiter verarbeitet. Gleiche Anhangnamen erhalten nummerierte Suffixe.

`_manifest.csv` ist UTF-8 mit einer Zeile pro Bucket-Mail. Es enthält Metadaten,
Herkunft, Treffer, relativen PDF-Pfad, PDF-SHA-256, Dedup-Schlüssel, Rohdatenhash und
eine JSON-Liste der Anhänge samt SHA-256, Größe und gespeichertem Pfad.
Der Rohdatenhash bezieht sich auf die vom jeweiligen Importer gelesenen Message-Bytes,
nicht auf das komplette Archiv. `_run.json` enthält Optionen, Quellen, Zuordnungen,
Statistiken und Status (`running`, `complete`, `complete_with_errors`, `failed`).
`_run.log` enthält Fehler mit Details; das UI zeigt maximal die ersten 100 Einträge.
Teilweise fehlgeschlagene Läufe bleiben zur Prüfung erhalten und werden nicht überschrieben.
Ein Lauf ohne Treffer erzeugt keinen Ausgabeordner; Buckets ohne Treffer werden ebenfalls
nicht angelegt.

Jeder Bucket enthält zusätzlich eine gleichnamige CSV mit den Spalten `Datum`, `Uhrzeit`,
`von`, `an` und `Text`. Sie verwendet UTF-8 mit BOM und Semikolon als Trennzeichen, damit
deutsche Excel-Installationen Umlaute und Spalten direkt korrekt erkennen.

## Architektur und Python-API

```text
src/mailbucket/
├── app.py, __main__.py       # UI und CLI
├── models.py, config.py      # gemeinsames Modell und Laufparameter
├── settings.py, branding.py  # lokale Optionen und Logo-Erkennung
├── pipeline.py              # Streaming, Treffer-Spool, Sortierung, Export
├── importers/               # Normalisierung, EML, MBOX, Maildir, Takeout, Protocol
├── index/                   # Fingerprints, SQLite/FTS5, atomarer Aufbau, Treffer-Laden
├── search/                  # ContainsMatcher, Anhangtext, TXT/CSV, Dedup
├── export/                  # Memo-PDFs, Fußzeilen, Anhänge, Manifest, Laufmetadaten
└── utils/                   # Daten, Dateinamen, Text, Hashes
```

```python
from pathlib import Path
from mailbucket.config import RunConfig
from mailbucket.pipeline import execute
from mailbucket.search.matcher import parse_terms

config = RunConfig(
    sources=[Path("archiv.mbox")],
    terms=parse_terms("345678\nMustermann"),
    output_dir=Path("exports"),
)
preview = execute(config, dry_run=True)
result = execute(config)
```

Importer implementieren `supports(path)` und `iter_emails(path)` und werden mit
`register_importer()` ergänzt. Jeder Adapter liefert `NormalizedEmail`; Suche und
Export kennen das Ursprungsformat nicht. Weitere Suchmodi können an der Matcher-Grenze
hinzukommen. `pip install -e ".[outlook]"` installiert optional `extract-msg` für
Adapterentwicklung, **aktiviert aber noch keinen MSG/PST/OST-Importer**.

## Tests und Entwicklung

Alle Testmails sind synthetisch (`example.com`) und werden zur Laufzeit erzeugt.
Keine echten Archive ins Repository legen; `.gitignore` schließt verbreitete
Mail-/Takeout-Formate, virtuelle Umgebungen und Exportordner aus.

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
ruff format --check src tests
```

Tests prüfen MIME/HTML/Unicode, Adressen, Labels, Suchfelder, CSV-Validierung,
Duplikate, Datumsreihenfolge, Pfadbereinigung, Archiv-Traversal und Links,
PDF-Inhalte, einzeln auswählbare Metadaten/Fußzeilen, Seitenzählung mit Anhängen,
defekte Anhänge, gespeicherte Optionen sowie MBOX-/Takeout-zu-Bucket-Läufe
mit Hashprüfung, Fundstellen und Überschreibschutz. Für die lokalen Indizes werden
zusätzlich Quellenwechsel, Fingerprints, Wiederverwendung, FTS5, exakte Trefferparität,
numerische Grenzen, Takeout-Treffer, abgebrochene Builds und defekte SQLite-Dateien geprüft.

## Bekannte Einschränkungen

- Keine Office-Konvertierung, OCR, Regex- oder exakte Suche; allgemeine Wortgrenzen sind
  nicht konfigurierbar. Reine Ziffernbegriffe erhalten automatisch Zifferngrenzen.
- Keine EMLX/MSG/PST/OST-Importer in 0.2, keine Passwortentschlüsselung von Archiven/PDFs.
- PDF verwendet einen Outlook-ähnlichen Memo-Kopf und lesbaren Text; HTML-Layout wird nicht nachgebildet.
  ReportLabs eingebettete Vera-Schrift unterstützt deutsche Umlaute und zahlreiche
  lateinische Zeichen; CJK, Emoji und komplexe Schreibrichtungen sind nicht vollständig abgedeckt.
- Pro Such-Worker werden höchstens zwei Aufgaben vorgeladen; während der PDF-Erzeugung
  gilt dieselbe begrenzte Warteschlange pro Ablage-Worker. Sehr große Einzelmails und
  Anhänge können daher besonders bei hoher Parallelität viel RAM benötigen.
  Treffer-Binaries werden temporär auf Platte gespeichert; Metadaten und Dedup-Schlüssel
  wachsen mit der Nachrichten-/Trefferzahl im RAM. MBOX benötigt intern einen Offsetindex.
- Archive werden gestreamt bzw. eine Mailbox nach der anderen entpackt. Es gibt keine
  konfigurierbare Entpack-Quota; sehr große oder künstlich aufgeblähte Archive können
  den freien Speicher beanspruchen.
- Kein Abbrechen/Wiederaufnehmen eines begonnenen Laufs. Der lokale Index beschleunigt
  die Suche; Dry Run und Export prüfen die Quelle jeweils erneut auf Änderungen.
  Lokaler Dateiauswahldialog listet große Verzeichnisse vollständig.
- PDF-Seitenübernahme erhält visuelle Inhalte, aber keine Garantie für die Gültigkeit
  vorhandener digitaler Signaturen. Original-PDF-Dateien bleiben bei Speicherung bytegetreu.
- Manifest-Metadaten sind originalgetreu; beim Öffnen fremder Inhalte in Tabellenprogrammen
  CSV-Spalten als Text importieren. Keine rechtliche Beweissicherungs-/Archivierungszertifizierung.

## Geplante Erweiterungen

Optionale Outlook-/EMLX-Adapter, weitere Suchmodi, erweiterte Schriftabdeckung,
Abbrechen/Wiederaufnehmen, inkrementelle Indexaktualisierung und optionale Office-Konvertierung.

## Lizenz

MIT, siehe [LICENSE](LICENSE). Abhängigkeiten unterliegen ihren eigenen Lizenzen;
die von ReportLab mitgelieferte Vera-Schrift ihrer Bitstream-Vera-Lizenz.
