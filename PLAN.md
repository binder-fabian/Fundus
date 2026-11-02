# Umsetzungsplan

Stand: 2. November 2026 · Grundlage: [SPEC.md](SPEC.md) · Status: **Phasen 1–3 umgesetzt**

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
| Auslieferung | Container-Image (python-slim, Nicht-Root), `docker-compose.yml` mit PostgreSQL 17, Caddy-Beispiel für HTTPS | Siehe SPEC „Technische Anforderungen“. Entwickelt wird mit Podman; Docker-Kompatibilität prüft die CI. |

**Erwartete Last**: ca. 150–250 MB RAM für App + PostgreSQL. Ein Mini-PC oder eine Synology reicht.

**Alternativen, kurz verworfen**:
- *Next.js/TypeScript wie OpenLibry*: Auth, Rollen, Änderungsprotokoll und i18n müssten aus Einzelteilen zusammengesetzt werden; Prisma braucht pro Datenbank ein eigenes Schema.
- *Laravel wie Snipe-IT*: ähnlich gut geeignet, aber PHP-Betrieb nativ unter Windows ist für Nicht-Experten umständlicher.

## 3. Grundsatzentscheidungen für das Datenmodell

- **Mandantenfähigkeit vorbereitet**: Modell `Schule`; Kategorien, Standorte, Titel und Exemplare haben einen Fremdschlüssel darauf. Im MVP gibt es genau eine Schule, die automatisch angelegt und in der Oberfläche nicht gezeigt wird. Inventarnummer ist **eindeutig je Schule**.
- **Zuständige Person ist keine globale Rolle**, sondern ergibt sich aus der Zuordnung am Titel (`zuständig`, `vertretung`). Globale Rollen als Django-Gruppen: Administrator, Verwalter, Lehrkraft, Sekretariat.
- **Ausleihstatus wird abgeleitet**: Ein Exemplar ist ausgeliehen, wenn es eine Ausleihe mit Status `ausgeliehen` gibt. Eine Datenbank-Bedingung erlaubt höchstens eine aktive Ausleihe je Exemplar.
- **Ausleihe ohne Personenbezug vorbereitet**: Feld `lehrkraft` optional, alternativ `klasse_oder_raum` (Freitext). Die Datenbank prüft, dass mindestens eins gesetzt ist.
- **Code und Bezeichner auf Englisch, Oberflächentexte auf Deutsch** und mit gettext markiert (Deutsch ist die Ausgangssprache). So sind die Texte übersetzbar angelegt, wie die SPEC verlangt, ohne dass für Deutsch Übersetzungsdateien und GNU-gettext-Werkzeuge nötig sind.
- Suche in Phase 1 als einfache Feldsuche (`icontains` über Titel, Autor, ISBN, Inventarnummer, Beschreibung), funktioniert gleich auf beiden Datenbanken. Für Schulbestände (einige tausend Titel) reicht das; PostgreSQL-Volltext ist bei Bedarf später möglich.

## 4. Phase 1 – MVP Katalog

Ziel laut SPEC: Datenmodell, Rollen, lokale Anmeldung, Titel/Exemplare/Standorte, CSV-Import, Suche, Export, Docker-Setup.
Jeder Schritt endet lauffähig (`docker compose up` startet) und mit grünen Tests.

### Schritt 1.1 – Projektgerüst und Betrieb

- `pyproject.toml` (uv), Django-Projekt `fundus`, App-Struktur (`core`, `accounts`, `catalog`, `loans`, ab Schritt 1.6 `transfer` für Import/Export).
- Einstellungen nur über Umgebungsvariablen; `.env.example`; SQLite per `DATABASE_URL=sqlite:////data/db.sqlite3`, PostgreSQL als Standard.
- `/health`-Endpunkt (prüft Datenbankverbindung).
- `Dockerfile` (mehrstufig, Nicht-Root, Daten nur unter `/data`), Entrypoint führt Migrationen aus.
- `docker-compose.yml` (App + PostgreSQL, benannte Volumes, Healthchecks), `docker-compose.sqlite.yml` als Variante.
- `deploy/Caddyfile.example`.
- ruff, pytest, Test-Matrix SQLite/PostgreSQL (lokal per Compose).
- `LICENSE` (AGPL-3.0), `.github/workflows/ci.yml` für GitHub Actions.
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
- Rollen als Feld am Benutzer (genau eine Rolle je Person) mit festen Rechten im Code statt Django-Gruppen: einfacher zu verwalten und für Personalrat/Datenschutz leichter nachvollziehbar.
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

## 5. Entscheidungen (1. November 2026)

| Frage | Entscheidung | Folge für den Plan |
| --- | --- | --- |
| Stack | **Django + htmx** | wie in Abschnitt 2 |
| Lizenz | **AGPL-3.0** | `LICENSE` kommt in Schritt 1.1 dazu |
| Projektname | **Fundus** | Python-Paket `fundus`, Image `fundus`, Titel in der Oberfläche „Fundus“ |
| Standardfristen | **14 / 28 / 90 Tage** | Tests und Technik 14 Tage, Bücher und Material 28 Tage, Anonymisierung 90 Tage nach Rückgabe; alles änderbar |
| Altdaten | **Microsoft List** vorhanden | Importvorlage „Microsoft-List-Export“ in Schritt 1.6; vorhandene Inventarnummern werden übernommen |
| Massenanlage Lehrkräfte | **in Phase 1** | wie in Schritt 1.3 |
| Hosting | **GitHub** (Codeberg scheidet nach dessen Nutzungsbedingungen aus) | CI über GitHub Actions: Tests mit SQLite und PostgreSQL, Image-Build und `docker compose up` mit Docker als Kompatibilitätstest |

### Was ich noch von dir brauche

- **Beispiel-Export der Microsoft List**: CSV oder Excel mit 10–20 Zeilen, Namen von Personen entfernt oder ersetzt. Am besten bis Schritt 1.6, früher hilft beim Datenmodell (Schritt 1.2).
- **GitHub-Repository**: Konto und leeres Repository (öffentlich oder privat, deine Wahl) legst du an; danach richte ich den Remote ein. Gepusht wird erst nach deinem Okay. Bis dahin laufen die Tests lokal.

## 6. Stand nach Phase 1 (2. November 2026)

Alle Schritte 1.1–1.8 sind umgesetzt, getestet (107 automatische Tests, je mit SQLite und PostgreSQL) und laufen in der CI auf GitHub, einschließlich `docker compose up` mit Docker.

### Bewusst offen oder vereinfacht

- **Navigation auf dem Handy:** Das Menü steht oben und bricht auf zwei Zeilen um. Eine Leiste unten am Bildschirm kommt mit dem Scanner in Phase 3.
- ~~Fertiges Container-Image~~ – erledigt in Schritt 2.7.
- ~~Schwelle für veraltete Tests als Umgebungsvariable~~ – jetzt in den Einstellungen (Schritt 2.1).
- **Wiederherstellen eines Titels** stellt die Förderschwerpunkte nicht mit zurück (Grenze von django-simple-history).
- **Native Installation** (Linux/Windows) ist dokumentiert, aber noch nicht auf einem frischen System durchgespielt.
- ~~Keine Begrenzung von Anmelde-Fehlversuchen~~ – erledigt in Schritt 2.7.

## 7. Phase 2 – Erfassung und Etiketten

Status: **umgesetzt** (2. November 2026)

Ziel laut SPEC: ISBN-Abruf einzeln und gesammelt, Nummernschema, Etiketten-PDF. Wie in Phase 1 endet jeder Schritt lauffähig, mit Tests, Commit und grüner CI.

### Vorab geprüft

- **DNB (SRU-Schnittstelle):** liefert ohne Zugangsschlüssel vollständige MARC21-Daten (Titel, Autor, Verlag, Auflage, Jahr). Die DNB-Titeldaten stehen unter CC0.
- **Open Library:** liefert ohne Schlüssel, oft auch für deutsche Titel, teils mit Cover.
- **Google Books:** lehnt Anfragen ohne eigenen API-Schlüssel ab (gemeinsames Kontingent erschöpft). Wird daher nur genutzt, wenn eine Schule einen Schlüssel einträgt (`GOOGLE_BOOKS_API_KEY`).
- **Etikettenmaße** stammen aus den Vorlagen des freien Etikettenprogramms gLabels; eine Testseite mit Rahmen und ein einstellbarer Druckversatz gleichen Druckerunterschiede aus.

### Schritt 2.1 – Einstellungsseite und Nummernschema

- Neues Modell „Schuleinstellungen“ (eine Zeile je Schule), Seite „Einstellungen“ für Administratoren.
- Nummernschema: Präfix, Stellenzahl, nächste Nummer (z. B. `FS-` / 4 / 101 → FS-0101). Vergabe kollisionssicher; vorhandene oder importierte Nummern werden übersprungen.
- Beim Anlegen von Exemplaren: „nächste freie Nummern verwenden“ – nur noch die Anzahl eingeben. Eigene Nummern bleiben möglich.
- Startwert: höchste vorhandene Nummer mit dem gewählten Präfix + 1, damit bestehende Folgen nahtlos weiterlaufen.
- Hierher wandern auch die Schwelle für veraltete Tests (bisher Umgebungsvariable) und der Schalter für den ISBN-Abruf.

### Schritt 2.2 – ISBN-Abruf einzeln

- Quellen in der Reihenfolge der SPEC: DNB → Open Library → Google Books (nur mit Schlüssel). Abruf serverseitig mit kurzer Zeitbegrenzung; das Frontend lädt nie etwas von außen.
- Ergebnisse werden 30 Tage zwischengespeichert (keine doppelten Anfragen).
- Cover nur von Open Library: Fundus lädt das Bild herunter und speichert es selbst, wie ein hochgeladenes Cover.
- Beim Titel-Anlegen: ISBN eintippen oder mit dem USB-Scanner scannen → „Daten abrufen“ füllt die Felder vor; gespeichert wird erst nach Bestätigung. Die Quelle wird angezeigt.
- Ohne Internet oder bei abgeschaltetem Abruf verschwindet der Knopf; alles andere funktioniert weiter.
- Das Scannen der ISBN mit der Handykamera kommt mit dem Scanner in Phase 3.

### Schritt 2.3 – Massenerfassung

- Seite „Bücher erfassen“: ISBNs nacheinander scannen (eine pro Zeile) oder als CSV hochladen. Mehrfach gescannte ISBN = mehrere Exemplare.
- Vorschau-Tabelle: Jede Zeile lädt ihre Daten einzeln nach (keine langen Wartezeiten), mit Status „gefunden / nicht gefunden / schon im Katalog“.
- Für alle gemeinsam wählbar: Kategorie, Standort, ausleihbar. Inventarnummern kommen automatisch aus dem Nummernschema.
- Übernehmen legt Titel und Exemplare an; vorhandene Titel (gleiche ISBN) bekommen nur neue Exemplare. Nicht gefundene ISBNs bleiben als Liste zum Nacharbeiten.

### Schritt 2.4 – Etiketten-PDF

- QR-Code enthält **nur die Inventarnummer**; darunter Inventarnummer und Kurztitel.
- Formate (Avery Zweckform, A4): 4732 (35,6 × 16,9 mm, 80 je Blatt), 6021 (45,7 × 16,9 mm, 64), 4780 (48,5 × 25,4 mm, 40), 3651 (52,5 × 29,7 mm, 40), 3474 (70 × 37 mm, 24). Weitere lassen sich leicht ergänzen.
- Auswahl: noch nicht gedruckte Exemplare, nach Kategorie, Standort oder Titel, einzelne Exemplare.
- Startposition wählbar, um angebrochene Bögen weiter zu nutzen; Testseite und Druckversatz in den Einstellungen.
- Nach dem Druck „als gedruckt markieren“, damit „noch nicht gedruckt“ stimmt.
- Neue Abhängigkeit: `reportlab` (BSD-Lizenz, erzeugt PDF und QR-Code ohne weitere Bibliotheken).

### Schritt 2.5 – Plakat mit QR-Code zur App

- A4-PDF mit großem QR-Code zur Adresse von Fundus (`SITE_URL`) und drei Sätzen Anleitung, zum Aufhängen im Lehrerzimmer.
- Nachbestellkarten für Verbrauchsmaterial folgen mit dem Verbrauchsmaterial in Phase 4.

### Schritt 2.6 – Dokumentation und Abnahme

- Admin-Handbuch ergänzen (Nummernschema, ISBN-Abruf, Massenerfassung, Etiketten, Druck-Kalibrierung).
- Abnahme: Massenerfassung mit echten ISBNs, Etiketten auf allen Formaten als PDF prüfen, Start ohne Internet.

### Schritt 2.7 – Anmeldeschutz und fertiges Container-Image

- **Anmeldeschutz:** Nach 5 falschen Passwörtern für dieselbe E-Mail-Adresse oder vom selben Gerät innerhalb von 15 Minuten ist die Anmeldung 15 Minuten gesperrt; die Seite sagt das verständlich. Ohne neue Abhängigkeit, Werte über Umgebungsvariablen änderbar.
- **Container-Image:** GitHub Actions baut bei jedem Stand auf `main` ein Image für Intel/AMD und ARM (Synology, Raspberry Pi) und legt es in der GitHub Container Registry ab (`ghcr.io/binder-fabian/fundus`). `docker-compose.yml` nutzt dann dieses Image; selbst bauen bleibt möglich. Solange das Repository privat ist, ist auch das Image privat; öffentlich wird es erst nach deiner ausdrücklichen Freigabe.

### Entscheidungen zu Phase 2 (2. November 2026)

| Frage | Entscheidung |
| --- | --- |
| Etikettenbögen | alle fünf: 4732, 6021, 4780, 3651, 3474 |
| Coverbilder | automatisch übernehmen, nur von Open Library |
| Inventarnummern | vorhanden als Präfix + Zahl; das Nummernschema setzt die Folge fort |
| Extras aus Phase 1 | Anmeldeschutz und fertiges Container-Image (Schritt 2.7) |

### Stand nach Phase 2 (2. November 2026)

Alle Schritte 2.1–2.7 sind umgesetzt; 152 automatische Tests (SQLite und PostgreSQL), CI und Image-Build auf GitHub grün. Abnahme: Massenerfassung mit echten ISBNs (DNB und Open Library, Cover übernommen), Etiketten und Plakat als PDF geprüft, Start und ISBN-Abruf ohne Internet.

Bewusst offen:

- **Image öffentlich machen:** Das Image `ghcr.io/binder-fabian/fundus` ist privat, solange das Repository privat ist. Öffentlich wird es nur mit deiner ausdrücklichen Freigabe.
- **Echter Probedruck:** Die Etiketten sind als PDF geprüft, aber noch nicht auf echten Bögen gedruckt und mit dem Handy gescannt. Das sollte vor dem Einsatz einmal je verwendetem Bogenformat passieren.
- **ISBN per Handykamera** kommt mit dem Scanner in Phase 3.
- **Google Books** braucht einen eigenen API-Schlüssel; ohne ihn fragt Fundus nur DNB und Open Library.

## 8. Phase 3 – Ausleihe

Status: **umgesetzt und freigegeben** (3. November 2026), über Pull Request #1 in `main` übernommen.

Ziel laut SPEC: Scanner-PWA, Ausleihen/Zurückgeben, Rückgabekiste-Modus, Testkoffer-Inhaltslisten, E-Mail-Erinnerungen. Leitprinzip: „App öffnen, scannen, fertig“ in unter 10 Sekunden.

### Schritte

- **3.1 Ausleihlogik:** Ausleihen, Zurückgeben, Verlängern als eigene, getestete Funktionen mit Rechteprüfung; Rückgabedatum aus der Ausleihfrist der Kategorie.
- **3.2 Oberfläche:** Exemplarseite mit der passenden Aktion (ausleihen / zurückgeben / verlängern), Startseite mit großem „Scannen“ und „Meine Ausleihen“, Übersicht für Verwalter (offen, überfällig, nach Lehrkraft, unvollständige Testkoffer).
- **3.3 Scanner-PWA:** Kamera-Scanner im Browser (QR-Codes der Etiketten und ISBN-Strichcodes), USB-Handscanner und Eintippen überall; installierbar als App (Manifest, Service Worker), Navigationsleiste unten auf dem Handy.
- **3.4 Rückgabekiste und Inhaltslisten:** Verwalter scannen viele Exemplare nacheinander zurück; bei Testkoffern wird die Inhaltsliste angezeigt und „vollständig / unvollständig“ abgefragt, fehlende Teile landen in der Notiz.
- **3.5 E-Mail-Erinnerungen:** Erinnerung am Tag vor der Rückgabe, Hinweis bei Überfälligkeit, danach zusätzlich an die Verwalter. Ein zweiter Dienst im selben Image (`scheduler`) verschickt täglich; ohne Container per Cron/Aufgabenplanung.
- **3.6 Dokumentation und Abnahme.**

### Technik

- Kamera: `barcode-detector` (Ponyfill der BarcodeDetector-Schnittstelle) mit ZXing als WebAssembly, lokal ausgeliefert – funktioniert auch auf iPhones, die keinen eingebauten Barcode-Scanner im Browser haben. Kamera braucht HTTPS (lokal geht `localhost`).
- Kein neuer Dienst außer dem `scheduler`, der dasselbe Image nutzt.

### Entscheidungen (am 3. November 2026 durchgegangen)

| # | Frage | Entschieden |
| --- | --- | --- |
| A | Wer sieht, **bei wem** etwas ist? | Vorerst nur Verwalter, Administratoren und zuständige Person; in Phase 5 wird es eine Einstellung für die Schule. |
| B | **Freigabepflichtige** Titel vor Phase 4? | Nur über die zuständige Person (oder Verwaltung) ausleihbar; Lehrkräfte sehen „Bitte an … wenden“. |
| C | Wer darf **zurückbuchen**? | Freigabepflichtige Titel nur die zuständige Person (mit Vertretung und Verwaltung); alle anderen Titel jede angemeldete Person. |
| D | **Verlängern** | Durch die ausleihende Lehrkraft, beliebig oft, solange keine Anfrage vorliegt. |
| E | **Erinnerungen** | 1 Tag vorher, 3 Tage überfällig, nach 14 Tagen zusätzlich an die Verwaltung. |
| F | **Für andere ausleihen** | Verwaltung und zuständige Personen; Lehrkräfte nur für sich. |
| G | **Unvollständige Testkoffer** | Ausleihbar mit deutlichem Hinweis. |

### Stand nach Phase 3 (Nacht zum 3. November 2026)

Schritte 3.1–3.6 umgesetzt; 198 automatische Tests (SQLite und PostgreSQL) grün. Geprüft im laufenden System: Ausleihen, „Meine Ausleihen“, Zurückgeben mit Inhaltsabfrage, Erinnerung per E-Mail (Mailpit), Scanner-Bibliothek erkennt QR-Codes (eingebauter Detektor und ZXing).

Nicht geprüft und vor dem Einsatz nötig:

- **Kamera auf echten Handys** (Android und iPhone) über HTTPS – im Entwicklungs-Browser ist die Kamera gesperrt.
