# MailBucket

**Mail Archive Search & PDF Export — vollständig lokal.**

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
- Suche ohne Beachtung der Groß-/Kleinschreibung in Betreff, Body, Absender,
  Empfängern, CC, Anhangnamen und Labels; Felder einzeln abschaltbar.
- Dry Run zählt Treffer und Duplikate, ohne Ausgabeordner oder PDFs anzulegen.
- Chronologische Sortierung, stabile Nummerierung, optional Datum im Dateinamen.
- Lesbare PDFs mit Herkunft, Headern, Treffern und Anhanginventar.
- PDF-Originalseiten anhängen, JPEG/PNG proportional einfügen, optionale Trennblätter.
- Originalanhänge bytegetreu speichern, sichere Namen ohne stilles Überschreiben.
- Manifest, SHA-256-Hashes, Laufparameter und Fehlerprotokoll.
- Fortschrittsanzeige; längere Vorgänge laufen außerhalb der UI-Ereignisschleife.

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

| Quelle | Version 0.1 |
| --- | --- |
| `.mbox` | Ja, auch mehrere Dateien in einem Verzeichnis |
| `.eml` / EML-Ordner | Ja, rekursiv, Groß-/Kleinschreibung der Erweiterung egal |
| Maildir | Ja, `cur`, `new`, `tmp` und Unter-Maildirs; `tmp` wird nicht importiert |
| Takeout `.zip`, `.tar`, `.tar.gz`, `.tgz` | Ja, automatische rekursive MBOX-Erkennung |
| Entpacktes Takeout-Verzeichnis | Ja, rekursive MBOX-Suche |
| `.emlx`, `.msg`, `.pst`, `.ost` | Adapter vorgesehen, noch kein Import in 0.1 |

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
zeigt gelesene Nachrichten; eine Gesamtzahl wird beim Streaming-Import nicht vorab
ermittelt, daher ist der Balken dort unbestimmt. Bei PDF-Erzeugung ist die Trefferzahl bekannt.
Ein bestehender Laufordner erzeugt einen Fehler und wird niemals wiederverwendet.
Nach erfolgreichem Export schlägt das UI einen freien Namen mit numerischem Suffix vor.

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
│   ├── 345678_0001.pdf
│   ├── 345678_0002.pdf
│   └── attachments/
│       └── 345678_0001/
│           ├── Rechnung.pdf
│           └── Angebot.xlsx
└── Mustermann/
    └── Mustermann_0001.pdf
```

Mit Zeitstempel beispielsweise `345678_0001_20260915_215700.pdf`.
Für jede Mail wird einmal gerendert und das Ergebnis in die passenden Buckets kopiert.
Der PDF-Header nennt deshalb alle gefundenen Begriffe; das Manifest nennt pro Zeile
nur die Begriffe des jeweiligen Buckets. Trennblätter identifizieren die E-Mail über
Betreff und Message-ID bzw. Rohdatenhash, damit die PDF bucketübergreifend wiederverwendbar bleibt.

PDF-Anhangmodi:

- **Anhängen**: Originalseiten ohne Rasterisierung übernehmen.
- **Separat**: PDF-Anhang als Original unter `attachments/` speichern.
- **Beides**: Seiten integrieren und Original speichern.

JPEG/PNG können proportional als Seiten eingefügt werden. Andere Formate werden
mit einem Hinweis dokumentiert. Mit **Originalanhänge zusätzlich speichern** bleiben
auch DOCX/XLSX/ZIP usw. verfügbar; ohne diese Option nennt der Hinweis ausdrücklich,
dass die Datei nicht gespeichert wurde. Bei ausgeschalteter Anhangverarbeitung bleibt
nur das Inventar im Mail-PDF. Defekte oder verschlüsselte PDFs werden protokolliert;
andere Mails werden weiter verarbeitet. Gleiche Anhangnamen erhalten nummerierte Suffixe.

`_manifest.csv` ist UTF-8 mit einer Zeile pro Bucket-Mail. Es enthält Metadaten,
Herkunft, Treffer, relativen PDF-Pfad, PDF-SHA-256, Dedup-Schlüssel, Rohdatenhash und
eine JSON-Liste der Anhänge samt SHA-256, Größe und gespeichertem Pfad.
Der Rohdatenhash bezieht sich auf die vom jeweiligen Importer gelesenen Message-Bytes,
nicht auf das komplette Archiv. `_run.json` enthält Optionen, Quellen, Zuordnungen,
Statistiken und Status (`running`, `complete`, `complete_with_errors`, `failed`).
`_run.log` enthält Fehler mit Details; das UI zeigt maximal die ersten 100 Einträge.
Teilweise fehlgeschlagene Läufe bleiben zur Prüfung erhalten und werden nicht überschrieben.

## Architektur und Python-API

```text
src/mailbucket/
├── app.py, __main__.py       # UI und CLI
├── models.py, config.py      # gemeinsames Modell und Laufparameter
├── pipeline.py              # Streaming, Treffer-Spool, Sortierung, Export
├── importers/               # Normalisierung, EML, MBOX, Maildir, Takeout, Protocol
├── search/                  # ContainsMatcher, TXT/CSV, Dedup
├── export/                  # PDFs, Anhänge, Manifest, Laufmetadaten
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
PDF-Inhalte, defekte Anhänge sowie einen vollständigen MBOX-zu-Bucket-Lauf
mit Hashprüfung und Überschreibschutz.

## Bekannte Einschränkungen

- Keine Office-Konvertierung, OCR, Regex-, Wortgrenzen- oder exakte Suche.
- Keine EMLX/MSG/PST/OST-Importer in 0.1, keine Passwortentschlüsselung von Archiven/PDFs.
- PDF ist eine dokumentarische Textansicht, keine HTML-/Outlook-Nachbildung.
  ReportLabs eingebettete Vera-Schrift unterstützt deutsche Umlaute und zahlreiche
  lateinische Zeichen; CJK, Emoji und komplexe Schreibrichtungen sind nicht vollständig abgedeckt.
- Es wird höchstens eine Mail einschließlich ihrer Anhänge vollständig im RAM gehalten;
  während PDF-Erzeugung zusätzlich ihre PDF-Daten. Sehr große Einzelmails können viel RAM benötigen.
  Treffer-Binaries werden temporär auf Platte gespeichert; Metadaten und Dedup-Schlüssel
  wachsen mit der Nachrichten-/Trefferzahl im RAM. MBOX benötigt intern einen Offsetindex.
- Archive werden gestreamt bzw. eine Mailbox nach der anderen entpackt. Es gibt keine
  konfigurierbare Entpack-Quota; sehr große oder künstlich aufgeblähte Archive können
  den freien Speicher beanspruchen.
- Kein Abbrechen/Wiederaufnehmen oder persistenter Suchindex. Dry Run und Export
  lesen separat. Lokaler Dateiauswahldialog listet große Verzeichnisse vollständig.
- PDF-Seitenübernahme erhält visuelle Inhalte, aber keine Garantie für die Gültigkeit
  vorhandener digitaler Signaturen. Original-PDF-Dateien bleiben bei Speicherung bytegetreu.
- Manifest-Metadaten sind originalgetreu; beim Öffnen fremder Inhalte in Tabellenprogrammen
  CSV-Spalten als Text importieren. Keine rechtliche Beweissicherungs-/Archivierungszertifizierung.

## Geplante Erweiterungen

Optionale Outlook-/EMLX-Adapter, weitere Suchmodi, erweiterte Schriftabdeckung,
Abbrechen/Wiederaufnehmen, lokale Indizes und optionale Office-Konvertierung.

## Lizenz

MIT, siehe [LICENSE](LICENSE). Abhängigkeiten unterliegen ihren eigenen Lizenzen;
die von ReportLab mitgelieferte Vera-Schrift ihrer Bitstream-Vera-Lizenz.
