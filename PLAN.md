# Umsetzungsplan

Stand: 1. November 2026 · Grundlage: [SPEC.md](SPEC.md) · Status: **Entwurf, wartet auf Freigabe**

## 1. Basis: Fork oder Neubau?

### OpenLibry (github.com/jzakotnik/openlibry)

Next.js + Prisma + SQLite, MIT-Lizenz, deutschsprachig, Docker-Image vorhanden, aktiv gepflegt (~1.200 Commits, kleine Community).

| Passt | Passt nicht |
| --- | --- |
| Schulkontext, deutsche Oberfläche | Datenmodell ist um **Schülerausleihe** gebaut: `User` speichert Vor-/Nachname, Klasse, Klassenlehrkraft von Schülerinnen und Schülern – widerspricht „keine Schülerdaten“ |
| Barcode-Scanner, Cover-Import, Etiketten, Mahnungen | **Titel und Exemplar nicht getrennt**: eine Tabelle `Book` hält Katalogdaten *und* Ausleihstatus – SPEC verlangt drei getrennte Objekte und abgeleiteten Status |
| Import aus OpenBiblio/Excel | Nur SQLite (Prisma-Provider fest), kein PostgreSQL |
| MIT-Lizenz erlaubt alles | Keine Standorte als Stammdaten, Rollen nur als String, Audit ohne Bezüge, kein Wiederherstellen, kein Freigabe-Workflow |

### Snipe-IT (github.com/grokability/snipe-it)

Laravel/PHP, AGPL-3.0, sehr ausgereift (15k Sterne), Inventar mit Ausgabe/Rücknahme, Verbrauchsmaterial, Standorte, QR-Etiketten, LDAP/SAML, Änderungshistorie, anforderbare Assets.

| Passt | Passt nicht |
| --- | --- |
| Viele Bausteine vorhanden (Standorte, Verbrauchsmaterial, Etiketten, LDAP/SAML, Audit) | Für IT-Abteilungen gebaut: Abschreibung, Lizenzen, Lieferanten – Oberfläche für Lehrkräfte viel zu komplex |
| Ausgereifte Rechteverwaltung | **Nur MySQL/MariaDB**, kein PostgreSQL, kein SQLite |
| | Kein Katalog-/Bibliotheksmodell (ISBN, Normjahr, Testkoffer-Inhalt), keine Scanner-PWA |
| | Großer PHP-Codebestand: Fork heißt dauerhaftes Mitziehen von Upstream oder Abspaltung; schwer für den „unter 10 Sekunden“-Ablauf umzubauen |
| | Ressourcenhungriger (PHP-FPM + Webserver + MySQL) |

### Empfehlung: **Neubau**, beide als Inspiration

Bei beiden Kandidaten müsste genau der Kern umgebaut werden, der die SPEC ausmacht: das getrennte Datenmodell Titel/Exemplar/Protokoll, Datensparsamkeit und PostgreSQL plus SQLite. Ein Fork würde nach dem Umbau kaum noch Upstream-Code teilen. Übernehmen wir stattdessen Ideen:

- **OpenLibry**: Scan-Ablauf und Suche-beim-Tippen, Cover-Handling, OpenBiblio-Importformat als zusätzliche Importvorlage.
- **Snipe-IT**: Trennung Asset/Verbrauchsmaterial mit Mindestmenge, „requestable“-Logik als Vorbild für Freigaben, Etikettenlayouts, Struktur der Änderungshistorie.

Keinen Code kopieren, solange die Lizenzfrage (s. u.) offen ist. Bei AGPL von Snipe-IT gilt das ohnehin.

## 2. Technologie-Stack (Vorschlag)

| Bereich | Wahl | Begründung |
| --- | --- | --- |
| Sprache/Framework | **Python 3.12+, Django 5.2 LTS** (Support bis April 2028) | Ein ORM für **PostgreSQL und SQLite** mit denselben Modellen und Migrationen. Mitgeliefert: Benutzer, Gruppen/Rechte, Passwort-Reset, Formulare, CSRF, i18n (gettext), Admin-Oberfläche als Notfallwerkzeug. Läuft nativ unter Linux und Windows. |
| Oberfläche | Server-gerenderte Templates + **htmx** (lokal ausgeliefert) | Kein JS-Build, keine externen Ressourcen, mobile first mit wenig Code. Suche-beim-Tippen und Scan-Abläufe gehen mit htmx-Partials. |
| CSS | Eigenes schlankes Stylesheet (CSS-Variablen, große Schaltflächen, hoher Kontrast) | Kein Node-Toolchain nötig, Barrierearmut gezielt steuerbar. |
| Änderungsprotokoll | `django-simple-history` | Wer/wann/was für alle Modelle, Wiederherstellen alter Stände eingebaut. |
| Konfiguration | `django-environ` (`DATABASE_URL`, `SECRET_KEY`, `EMAIL_URL` …) | Twelve-Factor, `.env.example`. |
| Import | `csv` (Standardbibliothek) + `openpyxl` für Excel | Kein Pandas, bleibt klein. |
| Hintergrundjobs (ab Phase 3) | Ein Management-Befehl `run_scheduler` im selben Image (eigener Compose-Dienst, gleiches Image) oder Cron/Windows-Aufgabenplanung | Kein Redis/Celery nötig: weiterhin „ein Image plus Datenbank“. |
| Später | `segno` (QR), `reportlab` (Etiketten-PDF), `mozilla-django-oidc`, `django-auth-ldap`, `python3-saml`, Scanner via `BarcodeDetector` + `zxing-wasm` als lokaler Fallback | Alles reifes Python-Ökosystem. |
| Server | `gunicorn` (Linux/Container), `waitress` (Windows nativ), `whitenoise` für statische Dateien | Ein Prozess, kein separater Webserver im Container. |
| Tests/Qualität | `pytest`, `pytest-django`, `factory_boy`, `ruff`; Tests laufen gegen SQLite **und** PostgreSQL | Spec verlangt Tests für Datenmodell, Ausleihe, Freigabe, Anonymisierung, Import. |
| Paketverwaltung | `uv` mit `pyproject.toml` + Lockfile | Schnell, reproduzierbar. |
| Auslieferung | Docker-Image (python-slim, Nicht-Root), `docker-compose.yml` mit PostgreSQL 17, Caddy-Beispiel für HTTPS | Siehe SPEC „Technische Anforderungen“. |

**Erwartete Last**: ca. 150–250 MB RAM für App + PostgreSQL. Ein Mini-PC oder eine Synology reicht.

**Alternativen, kurz verworfen**:
- *Next.js/TypeScript wie OpenLibry*: Auth, Rollen, Änderungsprotokoll und i18n müssten aus Einzelteilen zusammengesetzt werden; Prisma braucht pro Datenbank ein eigenes Schema.
- *Laravel wie Snipe-IT*: ähnlich gut geeignet, aber PHP-Betrieb nativ unter Windows ist für Nicht-Experten umständlicher.

## 3. Grundsatzentscheidungen für das Datenmodell

- **Mandantenfähigkeit vorbereitet**: Modell `Schule`; Kategorien, Standorte, Titel und Exemplare haben einen Fremdschlüssel darauf. Im MVP gibt es genau eine Schule, die automatisch angelegt und in der Oberfläche nicht gezeigt wird. Inventarnummer ist **eindeutig je Schule**.
- **Zuständige Person ist keine globale Rolle**, sondern ergibt sich aus der Zuordnung am Titel (`zuständig`, `vertretung`). Globale Rollen als Django-Gruppen: Administrator, Verwalter, Lehrkraft, Sekretariat.
- **Ausleihstatus wird abgeleitet**: Ein Exemplar ist ausgeliehen, wenn es eine Ausleihe mit Status `ausgeliehen` gibt. Eine Datenbank-Bedingung erlaubt höchstens eine aktive Ausleihe je Exemplar.
- **Ausleihe ohne Personenbezug vorbereitet**: Feld `lehrkraft` optional, alternativ `klasse_oder_raum` (Freitext). Die Datenbank prüft, dass mindestens eins gesetzt ist.
- **Code und Bezeichner auf Englisch**, Oberfläche auf Deutsch über gettext-Übersetzungsdateien. So sind die Texte übersetzbar angelegt, wie die SPEC verlangt.
- Suche in Phase 1 als einfache Feldsuche (`icontains` über Titel, Autor, ISBN, Inventarnummer, Beschreibung), funktioniert gleich auf beiden Datenbanken. Für Schulbestände (einige tausend Titel) reicht das; PostgreSQL-Volltext ist bei Bedarf später möglich.

## 4. Phase 1 – MVP Katalog

Ziel laut SPEC: Datenmodell, Rollen, lokale Anmeldung, Titel/Exemplare/Standorte, CSV-Import, Suche, Export, Docker-Setup.
Jeder Schritt endet lauffähig (`docker compose up` startet) und mit grünen Tests.

### Schritt 1.1 – Projektgerüst und Betrieb

- `pyproject.toml` (uv), Django-Projekt, App-Struktur (`core`, `accounts`, `catalog`, `loans`, `io`).
- Einstellungen nur über Umgebungsvariablen; `.env.example`; SQLite per `DATABASE_URL=sqlite:////data/db.sqlite3`, PostgreSQL als Standard.
- `/health`-Endpunkt (prüft Datenbankverbindung).
- `Dockerfile` (mehrstufig, Nicht-Root, Daten nur unter `/data`), Entrypoint führt Migrationen aus.
- `docker-compose.yml` (App + PostgreSQL, benannte Volumes, Healthchecks), `docker-compose.sqlite.yml` als Variante.
- `deploy/Caddyfile.example`.
- ruff, pytest, Test-Matrix SQLite/PostgreSQL (lokal per Compose).
- **Fertig, wenn**: `docker compose up` liefert eine Startseite und `/health` meldet OK; Start ohne Internet klappt.

### Schritt 1.2 – Datenmodell

- Modelle: `School`, `Category` (mit Standard-Ausleihfrist in Tagen), `SupportFocus` (Förderschwerpunkt), `Location` (Raum, Regal, als Baum oder zweistufig), `Title`, `Copy`, `Loan`.
- `Title`: alle Felder aus der SPEC inkl. Normjahr, Inhaltsliste (Freitext, eine Zeile pro Teil), Flags `lendable` und `approval_required`, `responsible` und `deputy`.
- `Copy`: Inventarnummer (eindeutig je Schule), Standort, Zustand, Notiz, Flag `incomplete`.
- `Loan`: alle Felder und Status aus der SPEC; nur Modell und Statuslogik, **keine Ausleih-Oberfläche** (kommt in Phase 3).
- Abgeleiteter Status als Queryset-Methode (`with_availability()`), damit Listen ohne N+1-Abfragen auskommen.
- Änderungsprotokoll (`simple_history`) an allen Stammdaten- und Katalogmodellen.
- Tests: Eindeutigkeit Inventarnummer, höchstens eine aktive Ausleihe, Status-Ableitung, Pflichtfeld Lehrkraft-oder-Klasse, Historie wird geschrieben.

### Schritt 1.3 – Anmeldung, Rollen, Benutzerverwaltung

- Benutzermodell mit E-Mail als Login (eigenes `User`-Modell von Anfang an, später nicht mehr änderbar).
- Login, Logout, Passwort vergessen, Passwort ändern; Einladung per E-Mail mit Einmal-Link zum Setzen des Passworts.
- Rollen als Gruppen mit festen Rechten, per Datenmigration angelegt.
- Benutzerverwaltung für Administratoren: anlegen/einladen, Rolle ändern, deaktivieren.
- **Massenanlage von Lehrkräften per CSV** (Name, E-Mail) mit Vorschau und Einladungsversand.
- Management-Befehl `createadmin` für die Ersteinrichtung; Hinweis in der Oberfläche, solange nur ein Administrator existiert.
- E-Mail über SMTP (`EMAIL_URL`); in der Entwicklung Mailpit als Compose-Dienst.
- Tests: Rechtematrix (Lehrkraft kann Stammdaten nicht ändern usw.), Einladungs-Token läuft ab, deaktivierter Benutzer kann sich nicht anmelden.

### Schritt 1.4 – Katalog-Oberfläche

- Grundlayout mobile first: große Schaltflächen, gute Kontraste, Navigation unten auf dem Handy.
- Stammdaten pflegen (Verwalter): Kategorien, Förderschwerpunkte, Standorte.
- Titel anlegen, bearbeiten, ansehen; **mehrere Exemplare in einem Schritt** anlegen (Anzahl + Startnummer oder Liste von Inventarnummern).
- Coverbild-Upload (gespeichert im Datenverzeichnis, verkleinert).
- Titel-Detailseite mit Exemplaren, Standort und Verfügbarkeit (Verfügbarkeit nur bei `lendable`).
- Änderungsprotokoll je Datensatz ansehen; Verwalter können einen alten Stand wiederherstellen.
- Lehrkräfte sehen alles lesend.
- Tests: Formulare, Rechte je Ansicht, Mehrfach-Exemplaranlage, Wiederherstellen.

### Schritt 1.5 – Suche und Filter

- Eine Suchleiste (Suche beim Tippen via htmx) über Titel, Autor, ISBN, Inventarnummer, Beschreibung.
- Filter: Kategorie, Förderschwerpunkt, Standort, Verfügbarkeit; Filter in der URL, damit Links teilbar sind.
- Direkttreffer: Eingabe einer exakten Inventarnummer (auch per USB-Handscanner) springt sofort zum Exemplar.
- Hinweis auf veraltete Tests (Normjahr älter als einstellbare Schwelle), da das nur eine Anzeige ist.
- Tests: Treffer, Filterkombinationen, Direktsprung.

### Schritt 1.6 – Import-Assistent (CSV/Excel)

- Upload CSV (Trennzeichen und Kodierung automatisch erkennen, UTF-8/Windows-1252) oder `.xlsx`.
- Schritt 2: Spaltenzuordnung per Auswahlliste; gespeicherte Vorlagen (z. B. „Microsoft-List-Export“).
- Schritt 3: Vorschau mit Validierung je Zeile (fehlende Pflichtfelder, doppelte Inventarnummern, unbekannte Kategorien → anlegen oder zuordnen).
- Schritt 4: Import in einer Transaktion; Titel werden anhand von ISBN oder Titel+Autor zusammengeführt, ein Exemplar pro Zeile; **vorhandene Inventarnummern werden übernommen**.
- Importbericht (angelegt, übersprungen, Fehler) zum Herunterladen.
- Tests mit Beispieldateien (auch fehlerhafte), Rollback bei Fehler, Zusammenführung von Titeln.

### Schritt 1.7 – Export

- Knopf „Alle Daten exportieren“ (nur Administrator): ZIP mit einer CSV-Datei pro Tabelle **und** einer JSON-Datei; enthält Stammdaten, Katalog, Exemplare, Ausleihen, Benutzer (ohne Passwort-Hashes) und Änderungsprotokoll.
- Gleicher Export als Management-Befehl `export_all` (Grundlage für die automatische Sicherung in Phase 5).
- Tests: Export → leere Datenbank → Re-Import der CSVs über den Assistenten ergibt denselben Katalog.

### Schritt 1.8 – Dokumentation und Abnahme

- `README.md` (Kurzüberblick), `docs/installation.md` (Docker/Synology, Schritt für Schritt für Nicht-Experten), `docs/native-install.md` (Entwurf Linux/Windows), `docs/admin.md` (Ersteinrichtung, Import, Export).
- Beispieldaten (`loaddemo`), damit man die App sofort ausprobieren kann.
- Abnahme-Checkliste: frische Installation mit PostgreSQL und SQLite, Import einer Beispiel-Liste, Suche am Handy, Export.

**Nicht in Phase 1**: ISBN-Abruf, Nummernschema, Etiketten (Phase 2), Ausleih-Oberfläche und Scanner-PWA (Phase 3). Bis dahin werden Inventarnummern von Hand vergeben oder importiert.

## 5. Offene Fragen an dich

1. **Stack**: Einverstanden mit Python/Django + htmx? (Alternativ TypeScript/Next.js, wenn du selbst lieber in TS mitliest.)
2. **Lizenz**: AGPL-3.0 (schützt davor, dass ein Anbieter es als geschlossenen Dienst weiterverkauft – passt zur Idee „Daten gehören der Schule“) oder MIT (maximale Verbreitung)? Meine Tendenz: AGPL.
3. **Projektname**: Arbeitstitel im Code vorerst `ausleihe`. Hast du einen Namen?
4. **Standardfristen**: Rückgabe z. B. 14 Tage (Tests) / 28 Tage (Bücher)? Anonymisierung nach z. B. 90 Tagen? In Phase 1 brauche ich nur die Ausleihfrist je Kategorie als Feld, ein Standardwert genügt.
5. **Vorhandene Daten**: Gibt es schon eine Microsoft List oder Excel-Datei mit Inventarnummern? Ein (anonymisierter) Beispiel-Export würde den Import-Assistenten passgenau machen.
6. **Massenanlage Lehrkräfte** in Phase 1 einverstanden (ist wenig Mehraufwand und macht die App früh nutzbar)?
7. **Hosting des Repos**: Nur lokal, oder später GitHub/Codeberg? (Beeinflusst, ob ich CI-Konfiguration gleich mit anlege.)
