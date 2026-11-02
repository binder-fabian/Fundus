# Umsetzungsplan

Stand: 2. November 2026 · Grundlage: [SPEC.md](SPEC.md) · Status: **Phasen 1–4 umgesetzt, Phase 5 in Planung**

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

## 9. Phase 4 – Freigaben und Verbrauchsmaterial

Status: **umgesetzt** (3. November 2026)

Ziel laut SPEC: Anfrage-Workflow mit Übergabe-Scan, Vertretung, Nachbestellkarten. Dazu das Verbrauchsmaterial (z. B. Protokollbögen) mit Bestand, Mindestmenge und Nachbestellhinweis an das Sekretariat.

### Schritt 4.1 – Anfragen für freigabepflichtige Titel

- Lehrkräfte stellen statt „Ausleihen“ eine **Anfrage für den Titel** (nicht für ein bestimmtes Exemplar), optional mit Wunschzeitraum und kurzer Nachricht. Status „angefragt“.
- Alle anwesenden Mitglieder des zuständigen **Teams** bekommen eine E-Mail und sehen offene Anfragen auf ihrer Startseite; wer zuerst reagiert, erledigt sie.
- **Genehmigen** oder **Ablehnen** (mit Begründung); die Lehrkraft wird per E-Mail informiert.
- Lehrkräfte sehen ihre Anfragen unter „Meine Ausleihen“ und können sie zurückziehen.
- Genehmigte, aber nicht abgeholte Anfragen verfallen nach einer einstellbaren Frist (Vorschlag: 14 Tage).

### Schritt 4.2 – Übergabe-Scan

- Ausgeliehen ist ein freigabepflichtiges Exemplar **erst, wenn jemand aus dem zuständigen Team bei der Übergabe den QR-Code eines freien Exemplars scannt**. Die Exemplarseite zeigt dann die genehmigten Anfragen zu diesem Titel; ein Tipp bucht aus („übergeben von“ wird gespeichert).
- Für freigabepflichtige Titel entfällt damit das direkte Ausbuchen ohne Anfrage nicht ganz: Zuständige und Verwaltung können weiterhin direkt für jemanden ausbuchen (z. B. bei spontaner Übergabe).
- Verlängern ist nicht möglich, solange eine andere Anfrage vorliegt (schon so umgesetzt).

### Schritt 4.3 – Teams statt „zuständige Person + Vertretung“

- **Teams** als Stammdaten (z. B. „Diagnostik-Team“) mit einer bis beliebig vielen Personen; am Titel wird ein Team gewählt. Eine einzelne Person ist ein Team aus einer Person.
- Alle Teammitglieder haben die bisherigen Rechte der zuständigen Person (genehmigen, übergeben, zurückbuchen, für andere ausleihen); das Team vertritt sich gegenseitig.
- Wer sich in „Mein Konto“ als **abwesend bis …** einträgt, bekommt in der Zeit keine Anfragen. Sind alle abwesend, geht die Anfrage an die Verwaltung.
- Bestehende Einträge (zuständige Person + Vertretung) werden automatisch in Teams übernommen.
- Übersicht für Verwalter: freigabepflichtige Titel ohne Team.

### Schritt 4.4 – Verbrauchsmaterial

- Neuer Bereich „Verbrauchsmaterial“: Bezeichnung, Bezug zu einem Titel (z. B. Protokollbögen zum Test), Standort, Bestellhinweis (Lieferant, Artikelnummer, Packungsgröße).
- **Bestand zählen wahlweise je Material:** mit Bestand und Mindestmenge (Entnahme buchen) oder nur mit Nachbestellkarte.
- Entnahme und Auffüllen buchen; der Titel zeigt sein zugehöriges Verbrauchsmaterial.

### Schritt 4.5 – Nachbestellkarten und Nachbestellhinweise

- **Nachbestellkarte** als PDF (wie die Etiketten): QR-Code mit einer eigenen Kennung (z. B. `NB-0003`), Bezeichnung und Bestellhinweis. Die Karte liegt im Stapel an der Stelle, an der nachbestellt werden muss.
- Wer die Karte erreicht, **scannt sie** → ein Tipp auf „Nachbestellen“ erzeugt einen Nachbestellhinweis. Ebenso automatisch, wenn der Bestand die Mindestmenge unterschreitet.
- Hinweise gehen an alle mit der Rolle **Sekretariat** (Liste in Fundus und E-Mail) und zusätzlich per E-Mail an eine in den Einstellungen hinterlegte Adresse (z. B. sekretariat@schule.de). Das Sekretariat hakt sie als „bestellt“ und später „geliefert“ ab (geliefert = Bestand auffüllen).

### Schritt 4.6 – Dokumentation und Abnahme

### Entscheidungen zu Phase 4 (3. November 2026)

| Frage | Entscheidung |
| --- | --- |
| Anfrage bezieht sich auf | den Titel; bei der Übergabe wird ein freies Exemplar gescannt |
| Zuständigkeit und Vertretung | Teams als Stammdaten; alle Anwesenden bekommen jede Anfrage; sind alle abwesend, die Verwaltung |
| Bestand beim Verbrauchsmaterial | wahlweise je Material: zählen oder nur Nachbestellkarte |
| Nachbestellhinweise an | Rolle Sekretariat (Liste + E-Mail) und eine einstellbare E-Mail-Adresse |

Reihenfolge der Umsetzung: 4.3 (Teams) zuerst, weil Anfragen und Übergabe darauf aufbauen; danach 4.1, 4.2, 4.4, 4.5, 4.6.

### Stand nach Phase 4 (3. November 2026)

Alle Schritte umgesetzt; 231 automatische Tests (SQLite und PostgreSQL), CI und Image-Build grün. Migrationen auf bestehenden Daten geprüft (Zuständige → Teams, Ausleihen bekommen ihren Titel). Nachbestellkarten als PDF geprüft.

Hinweise:

- Eine Ausleihe bezieht sich jetzt immer auf einen **Titel**; das Exemplar steht bei Anfragen erst mit der Übergabe fest.
- Nicht geprüft: echter E-Mail-Versand über den Schul-Mailserver (bisher nur Mailpit) und die Kamera auf echten Handys.

## 10. Phase 5 – Datenschutz und Betrieb

Status: **Entwurf, Fragen beantwortet, wartet auf Freigabe** (2. November 2026)

Ziel laut SPEC: Anonymisierung, Sichtbarkeitsstufen, Modus ohne Namen, automatische Sicherung, Verarbeitungsbeschreibung. Leitgedanke: Personalrat und Datenschutzbeauftragte sollen zustimmen können, ohne dass die Schule etwas programmieren oder selbst formulieren muss.

### Vorab geprüft

- Schon vorhanden: Feld „Klasse oder Raum“ und Zeitpunkt „anonymisiert am“ an der Ausleihe, Sperre fehlgeschlagener Anmeldungen (Einträge werden nach einem Tag gelöscht), keine externen Ressourcen im Browser, Cover werden auf dem Server gespeichert.
- **Lücke:** Das Änderungsprotokoll speichert jede Fassung einer Ausleihe mit Namen. Eine Anonymisierung muss diese Protokollzeilen mit bereinigen, sonst stehen die Namen dort weiter.
- **Lücke:** Konten lassen sich nur deaktivieren, nicht löschen, solange Ausleihen auf sie verweisen.

### Schritt 5.1 – Anonymisierung nach Löschfrist

- Einstellung „Ausleihen anonymisieren nach … Tagen“ (Standard **90 Tage**, entschieden in Phase 1). Gilt für abgeschlossene Vorgänge: zurückgegeben, abgelehnt, zurückgezogen, verfallen.
- Entfernt werden: Lehrkraft, Klasse/Raum, „genehmigt von“, „übergeben von“, Nachricht und Ablehnungsgrund – auch in allen Protokollzeilen dieser Ausleihe. Es bleiben Titel, Exemplar und Daten, damit die Statistik („wie oft wurde der Test ausgeliehen?“) erhalten bleibt.
- Läuft täglich im Dienst `scheduler` mit; zusätzlich als Befehl `anonymize` für Installationen ohne Container.
- In den Einstellungen: Anzahl der Ausleihen, die beim nächsten Lauf anonymisiert werden, und Knopf „jetzt anonymisieren“.

### Schritt 5.2 – Sichtbarkeit der Namen

- Einstellung „Wer sieht, bei wem etwas ausgeliehen ist?“: **nur Verwaltung und zuständiges Team** (Standard, wie bisher) oder **alle angemeldeten Lehrkräfte** (damit man direkt nachfragen kann).
- Gilt für Exemplarseite, Titelseite und Scan-Ergebnis. Die Übersicht „Ausleihen“ bleibt der Verwaltung vorbehalten.

### Schritt 5.3 – Modus ohne Personenbezug

- Einstellung „Ausleihen ohne Namen (nur Klasse oder Raum)“ – für die Zeit bis zur Zustimmung des Personalrats.
- Beim Ausleihen wird statt der Person **Klasse oder Raum** erfasst (Freitext mit Vorschlägen aus früheren Einträgen, z. B. „3b“, „Raum 104“). Ausleihen dauert dadurch einen Tipp länger.
- Folgen, die die Oberfläche deutlich sagt: keine „Meine Ausleihen“, keine Erinnerungs-E-Mails an Lehrkräfte; Überfälliges sieht die Verwaltung in der Übersicht. **Anfragen** laufen in diesem Modus wie bisher mit Namen und E-Mail (die anfragende Person braucht die Antwort). Bei der Übergabe trägt das Team Klasse oder Raum ein; Name, Nachricht und „genehmigt von“ werden dabei sofort gelöscht, auch im Protokoll. Die Ausleihe selbst ist damit ohne Personenbezug.
- Umschalten wirkt nur auf neue Ausleihen; bestehende bleiben, wie sie sind.

### Schritt 5.4 – Konten löschen und „Meine Daten“

- Administratoren können ein Konto **löschen** (z. B. wenn eine Lehrkraft die Schule verlässt), sobald sie nichts mehr ausgeliehen hat. Ihre abgeschlossenen Ausleihen werden dabei sofort anonymisiert, ihr Name verschwindet aus dem Änderungsprotokoll.
- Unter „Konto“ kann jede Person **„Meine Daten herunterladen“**: alles, was Fundus über sie gespeichert hat (Auskunft nach Art. 15 DSGVO), als CSV in einer ZIP-Datei.

### Schritt 5.5 – Automatische Sicherung

- Der Dienst `scheduler` legt nach Zeitplan eine Sicherung als ZIP in ein eingebundenes Verzeichnis (`BACKUP_DIR`, Standard `DATA_DIR/sicherungen`). Inhalt: vollständiger Datenbankauszug (unabhängig von SQLite oder PostgreSQL), hochgeladene Bilder und zusätzlich der lesbare Export aus Phase 1.
- **Passwörter** sind als Hashwerte enthalten, damit sich nach einer Wiederherstellung alle wieder anmelden können. Die Sicherungen gehören deshalb in ein geschütztes Verzeichnis (steht in der Anleitung).
- Häufigkeit und Anzahl aufbewahrter Sicherungen in den Einstellungen (Standard: **täglich, 14 aufbewahren**); ältere werden automatisch gelöscht. Wichtig für den Datenschutz: Namen stehen bis zum Ende der Aufbewahrung auch in den Sicherungen. Das nennt die Verarbeitungsbeschreibung.
- Wiederherstellung über die Kommandozeile: `python manage.py restore_backup <datei.zip>` in eine leere Datenbank; prüft vorher die Programmversion. Damit geht auch der **Umzug von SQLite nach PostgreSQL**.
- In den Einstellungen: Zeitpunkt der letzten Sicherung und eine Warnung, wenn sie fehlgeschlagen oder älter als geplant ist. Knopf „jetzt sichern“.
- Dokumentiert in der Installationsanleitung, mit Hinweis, die Sicherungen zusätzlich außerhalb des Servers aufzubewahren (z. B. NAS).

### Schritt 5.6 – Änderungsprotokoll begrenzen

- Das Protokoll zeigt, **wer** einen Titel, ein Exemplar oder ein Konto wann geändert hat. Auch das ist ein Personenbezug (Verhaltens- und Leistungskontrolle ist ein Personalratsthema).
- Einstellung „Im Änderungsprotokoll den Namen entfernen nach …“ (Standard: **1 Jahr**). Was geändert wurde, bleibt; nur „wer“ wird entfernt.

### Schritt 5.7 – Verarbeitungsbeschreibung

- Fundus erzeugt aus den **aktuellen Einstellungen** eine Kurzbeschreibung der Verarbeitung: welche Daten, Zweck, Rechtsgrundlage (als Vorschlag zum Prüfen), wer worauf zugreift, Fristen, Empfänger (ISBN-Abruf: nur die ISBN geht an DNB, Open Library, ggf. Google), Sicherungen, technische Maßnahmen (HTTPS, Passwort-Hashing, Anmeldesperre, keine Cookies außer der Anmeldung, kein Tracking).
- Als Vorlage für Datenschutzbeauftragte und Personalrat, mit gelb markierten Stellen, die die Schule selbst ergänzt (Verantwortlicher, Serverstandort, Datenschutzbeauftragte). Format: **Word-Datei** (.docx, auch mit LibreOffice zu öffnen), erzeugt mit der Bibliothek python-docx (MIT-Lizenz).
- Ändert jemand eine datenschutzrelevante Einstellung, erinnert ein Hinweis daran, die Beschreibung neu zu erzeugen.

### Schritt 5.8 – Dokumentation und Abnahme

- Admin-Handbuch: Abschnitt „Datenschutz“ mit allen Einstellungen und Empfehlungen; Installationsanleitung: Sicherung und Wiederherstellung; Kurzanleitung für Lehrkräfte: Hinweis zum Modus ohne Namen.
- Tests für Anonymisierung (inkl. Protokollzeilen), Sichtbarkeit, Modus ohne Namen, Sicherung und Wiederherstellung (SQLite und PostgreSQL).

### Reihenfolge

5.1 und 5.6 zuerst (gemeinsame Bereinigungslogik für Protokollzeilen), dann 5.4, 5.2, 5.3, 5.5, 5.7, 5.8.

### Entscheidungen zu Phase 5 (2. November 2026)

| Frage | Entscheidung |
| --- | --- |
| Anfragen im Modus ohne Namen | Name nur bis zur Übergabe; dann Klasse/Raum, Name und Nachricht werden gelöscht |
| Automatische Sicherung | täglich, 14 Sicherungen aufbewahren (einstellbar) |
| „Wer hat geändert“ im Änderungsprotokoll | nach 1 Jahr entfernen (einstellbar) |
| Konto löschen und „Meine Daten“ | beides in Phase 5 |
| Verarbeitungsbeschreibung | Word-Datei (.docx) mit markierten Stellen zum Ergänzen |
| Löschfrist für Ausleihen | 90 Tage nach Abschluss (aus Phase 1) |
| Sichtbarkeit der Namen | Standard wie bisher: Verwaltung und zuständiges Team; „alle Lehrkräfte“ wählbar |
