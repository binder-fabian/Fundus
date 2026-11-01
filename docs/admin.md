# Admin-Handbuch

Stand: Phase 2 (Katalog, Erfassung, Etiketten). Ausleihe und Kamera-Scanner folgen in Phase 3.

## Rollen

| Rolle | Darf |
| --- | --- |
| Administrator | alles: Benutzer, Import und Export, dazu alles von „Verwalter“ |
| Verwalter | Katalog, Exemplare, Stammdaten pflegen; Änderungen ansehen und zurücknehmen |
| Lehrkraft | Katalog ansehen und durchsuchen |
| Sekretariat | wie Lehrkraft; später Nachbestellhinweise |

„Zuständige Person“ ist keine Rolle, sondern wird am einzelnen Titel eingetragen (mit Vertretung). Jede Person hat genau eine Rolle.

## Benutzer

- **Einzeln einladen:** „Benutzer → Person einladen“. Die Person bekommt eine E-Mail mit einem Link, der 14 Tage gilt und nur einmal funktioniert.
- **Kollegium auf einmal:** „Benutzer → Lehrkräfte aus CSV“. Die Datei braucht die Spalten Vorname, Nachname und E-Mail. Sie sehen eine Vorschau, bevor etwas angelegt wird.
- **Einladung verloren?** Die Person nutzt auf der Anmeldeseite „Passwort vergessen“, oder Sie klicken in der Liste auf „Erneut einladen“.
- **Ausgeschieden?** Konto deaktivieren statt löschen. So bleiben vergangene Vorgänge nachvollziehbar, bis sie nach der Löschfrist anonymisiert werden (Phase 5).
- Der letzte aktive Administrator kann nicht deaktiviert oder herabgestuft werden.
- **Anmeldeschutz:** Nach 5 falschen Passwörtern ist die Anmeldung für diese E-Mail-Adresse 15 Minuten gesperrt. „Passwort vergessen“ funktioniert trotzdem.

## Katalog pflegen

- **Titel** sind Werke oder Materialien, **Exemplare** die einzelnen Stücke mit eigener Inventarnummer.
- Beim Anlegen eines Titels können Sie gleich mehrere Exemplare erzeugen: als Liste oder als Nummernfolge (Präfix, Startnummer, Anzahl, z. B. `FS-` / `0101` / `5` → FS-0101 … FS-0105).
- Inventarnummern sind eindeutig; Groß- und Kleinschreibung spielt keine Rolle.
- **Ausleihbar** markieren Sie Titel, die später per Scan ausgeliehen werden (Tests, Technik, gefragte Medien). Alltagsmaterial bleibt einfach mit Standort im Katalog.
- **Stammdaten** (Kategorien mit Ausleihfrist, Förderschwerpunkte, Standorte) finden Verwalter unter „Stammdaten“. Was noch verwendet wird, lässt sich nicht löschen.

## Einstellungen

Unter „Einstellungen“ (nur Administratoren):

- **Name der Schule:** erscheint auf dem Plakat.
- **Nummernschema:** Präfix (z. B. `FS-`), Stellenzahl (z. B. 4 → `0101`) und nächste Nummer. Fundus setzt immer nach der höchsten vorhandenen Nummer mit diesem Präfix fort, auch nach einem Import. Die nächste Nummer wird angezeigt.
- **Veraltete Tests:** ab wie vielen Jahren nach dem Normjahr ein Test als veraltet markiert wird (Standard 10).
- **ISBN-Abruf:** an- oder abschalten (siehe unten).
- **Druckversatz** für Etiketten (siehe unten).

## Neue Exemplare und Nummern

Beim Anlegen eines Titels oder unter „Exemplare hinzufügen“ genügt die **Anzahl**: Fundus vergibt die nächsten freien Nummern nach dem Nummernschema. Eigene Nummern (Liste oder Nummernfolge) sind weiterhin möglich, aber nicht beides zugleich.

## ISBN-Abruf

Beim Anlegen eines Titels die ISBN eintippen oder mit dem USB-Handscanner scannen und auf **„Daten zur ISBN abrufen“** klicken. Fundus fragt nacheinander die Deutsche Nationalbibliothek und Open Library (mit eigenem Schlüssel in `GOOGLE_BOOKS_API_KEY` zusätzlich Google Books) und füllt nur leere Felder aus. Gespeichert wird erst, wenn Sie auf „Speichern“ klicken. Gibt es bei Open Library ein Cover, wird es beim Speichern übernommen.

Übermittelt wird nur die ISBN, und zwar vom Server aus; die Browser der Lehrkräfte laden nichts von außen. Ergebnisse werden 30 Tage zwischengespeichert. Ohne Internet erscheint ein Hinweis, alles andere funktioniert weiter. Abschalten unter „Einstellungen“.

## Bücher erfassen (Massenerfassung)

„Katalog → Bücher erfassen“:

1. ISBNs nacheinander scannen (jede landet in einer eigenen Zeile) oder eine CSV/TXT-Datei mit ISBNs hochladen. Mehrfach gescannte Bücher ergeben mehrere Exemplare.
2. In der **Vorschau** lädt jede Zeile ihre Daten einzeln. Bücher, die schon im Katalog stehen, bekommen nur neue Exemplare. Nicht gefundene Bücher sind abgewählt.
3. Kategorie, Standort und „ausleihbar“ für alle wählen und **Übernehmen**. Die Inventarnummern kommen aus dem Nummernschema; Cover werden danach im Hintergrund nachgeladen.

Nicht gefundene ISBNs stehen am Ende in einer Liste zum Nacharbeiten.

## Etiketten

„Katalog → Etiketten“ (oder auf einer Titel- bzw. Exemplarseite „Etiketten“):

- Der QR-Code enthält **nur die Inventarnummer**. So bleiben Etiketten auch gültig, wenn die Schule einmal ein anderes System nutzt.
- Bögen: Avery Zweckform 4732 (35,6 × 16,9 mm), 6021 (45,7 × 16,9 mm), 4780 (48,5 × 25,4 mm), 3651 (52,5 × 29,7 mm) und 3474 (70 × 37 mm).
- Auswahl: noch nicht gedruckte Exemplare, nach Kategorie, Standort, Titel, einzelne oder alle.
- **Angebrochener Bogen:** Bei „Beginnen bei Etikett Nr.“ die erste freie Position eintragen (zeilenweise von links oben gezählt).
- Nach dem Druck **„Als gedruckt markieren“**, damit „noch nicht gedruckt“ stimmt.

**Drucker ausrichten:** Im Druckdialog immer „Tatsächliche Größe“ bzw. „100 %“ wählen. Die **Testseite** auf Normalpapier drucken, auf einen Etikettenbogen legen und gegen das Licht halten. Sitzen die Rahmen versetzt, den Unterschied in Millimetern unter „Einstellungen → Druckversatz“ eintragen (rechts/unten positiv) und die Testseite erneut drucken.

## Plakat

Unter „Etiketten“ gibt es ein A4-Plakat mit QR-Code zur Adresse von Fundus (`SITE_URL`) und einer kurzen Anleitung, z. B. für das Lehrerzimmer.

## Änderungsprotokoll

Jede Änderung an Titeln, Exemplaren, Stammdaten und Benutzerkonten wird mit Zeitpunkt und Person gespeichert. Über „Änderungen“ sehen Verwalter, was vorher und nachher stand, und können einen älteren Stand wiederherstellen. Auch gelöschte Stammdaten lassen sich so zurückholen.

## Import vorhandener Listen

„Import/Export“ (nur Administratoren):

1. **Datei** hochladen: CSV oder Excel (.xlsx). Aus einer Microsoft List: „Exportieren → In CSV exportieren“.
2. **Spalten zuordnen.** Bekannte Spaltennamen sind schon zugeordnet. Pflicht sind Inventarnummer und Titel. Die Zuordnung lässt sich als Vorlage speichern.
3. **Vorschau** prüfen: Fehlerhafte Zeilen (z. B. fehlende oder doppelte Inventarnummer) werden übersprungen und rot markiert.
4. **Importieren.** Alles wird in einem Schritt übernommen, oder bei einem Problem gar nichts. Den Importbericht können Sie als CSV herunterladen.

Zeilen mit gleicher ISBN oder gleichem Titel und Autor werden zu einem Titel mit mehreren Exemplaren zusammengefasst, auch mit Titeln, die schon im Katalog stehen.

## Export und Sicherung

„Import/Export → Zum Export“ lädt ein ZIP mit allen Daten herunter:

- `katalog.csv`: eine Zeile pro Exemplar; lässt sich in Excel öffnen und über den Import wieder einlesen
- `csv/`: eine Datei pro Tabelle, auch das Änderungsprotokoll
- `fundus.json`: alles in einer Datei
- `dateien/`: Coverbilder

Passwörter sind nie enthalten. Auf dem Server:

```bash
docker compose exec app python manage.py export_all
```

legt den Export unter `/data/exporte/` im Daten-Volume ab. Automatische Sicherungen nach Zeitplan folgen in Phase 5.

## Einstellungen über `.env`

| Einstellung | Standard | Bedeutung |
| --- | --- | --- |
| `SESSION_DAYS` | 30 | So lange bleiben Personen angemeldet |
| `LOGIN_MAX_ATTEMPTS` | 5 | Falsche Passwörter, bevor die Anmeldung gesperrt wird (je Gerät das Vierfache) |
| `LOGIN_LOCK_MINUTES` | 15 | Dauer der Sperre |
| `GOOGLE_BOOKS_API_KEY` | leer | Optionaler Schlüssel für Google Books als dritte ISBN-Quelle |
| `INVITATION_TIMEOUT_DAYS` | 14 | Gültigkeit von Einladungslinks |
| `TIME_ZONE` | Europe/Berlin | Zeitzone |
| `LOG_LEVEL` | INFO | Ausführlichkeit der Protokolle |
