# Admin-Handbuch

Stand: Phase 1 (Katalog). Ausleihe, Etiketten und Scanner folgen in späteren Phasen.

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

## Katalog pflegen

- **Titel** sind Werke oder Materialien, **Exemplare** die einzelnen Stücke mit eigener Inventarnummer.
- Beim Anlegen eines Titels können Sie gleich mehrere Exemplare erzeugen: als Liste oder als Nummernfolge (Präfix, Startnummer, Anzahl, z. B. `FS-` / `0101` / `5` → FS-0101 … FS-0105).
- Inventarnummern sind eindeutig; Groß- und Kleinschreibung spielt keine Rolle.
- **Ausleihbar** markieren Sie Titel, die später per Scan ausgeliehen werden (Tests, Technik, gefragte Medien). Alltagsmaterial bleibt einfach mit Standort im Katalog.
- **Stammdaten** (Kategorien mit Ausleihfrist, Förderschwerpunkte, Standorte) finden Verwalter unter „Stammdaten“. Was noch verwendet wird, lässt sich nicht löschen.

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
| `INVITATION_TIMEOUT_DAYS` | 14 | Gültigkeit von Einladungslinks |
| `OUTDATED_NORM_YEARS` | 10 | Tests mit älterer Normierung werden als „veraltet“ markiert |
| `TIME_ZONE` | Europe/Berlin | Zeitzone |
| `LOG_LEVEL` | INFO | Ausführlichkeit der Protokolle |
