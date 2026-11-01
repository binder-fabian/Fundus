# Ausleihsystem für Schulen – Feature-Set für die Entwicklung

Stand: 1. November 2026 · Autor: Fabian Binder

## Auftrag an Claude Code

Entwickle eine eigenständige Web-Anwendung, mit der Schulen ihren Bestand an Büchern, Diagnostiktests, Fördermaterial und Technik verwalten und ausleihen. Sie läuft selbst gehostet in Docker und braucht **kein Microsoft 365**. Zielgruppe sind vor allem Förder-, Grund- und Mittelschulen ohne eigene IT-Abteilung.

Arbeitsweise:

1. Lies diese Datei vollständig und lege einen Umsetzungsplan an (Phasen siehe unten).
2. Prüfe zuerst, ob **OpenLibry** (Open-Source-Schulbibliothek, Docker) als Basis oder Inspiration taugt, und begründe kurz die Entscheidung für Fork oder Neubau.
3. Baue in kleinen, lauffähigen Schritten mit Tests. Jede Phase endet mit einem funktionierenden `docker compose up`.
4. Offene Entscheidungen (Abschnitt am Ende) nicht still treffen, sondern als Frage festhalten.

## Leitprinzipien

- **Ausleihen geht schneller, als es zu lassen**: App öffnen, scannen, fertig – Ziel unter 10 Sekunden, keine Pflichtfelder außer vorausgefülltem Rückgabedatum.
- **Hauptziel ist Übersicht**: Jede Lehrkraft sieht zentral, was es gibt und wo es gerade ist.
- **Datensparsam**: Keine Schülerdaten. Namen von Lehrkräften nur, wo nötig, mit Löschfristen (Personalrat und Datenschutz müssen zustimmen können).
- **Daten gehören der Schule**: Vollständiger Export jederzeit, offene Formate, keine Abhängigkeit von Cloud-Diensten.
- **Einfach zu betreiben**: Ein Container plus Datenbank, Konfiguration über Umgebungsvariablen, läuft auf kleinem Schulserver.
- **Deutsche Oberfläche**, verständlich für Nicht-Techniker.

## Datenmodell

Drei Kernobjekte, getrennt gehalten:

| Objekt | Inhalt |
| --- | --- |
| **Titel (Katalog)** | Ein Eintrag pro Werk/Material: Titel, Autor, Verlag, ISBN (optional), Kategorie, Förderschwerpunkt, Beschreibung, Coverbild, Auflage, Normjahr (Tests), Inhaltsliste (Testkoffer), Flag „ausleihbar“, Flag „freigabepflichtig“, zuständige Person + Vertretung |
| **Exemplar** | Ein Eintrag pro physischem Stück: Inventarnummer (eindeutig, Inhalt des QR-Codes), Verweis auf Titel, Standort (Raum, Regal), Zustand, Notiz, Flag „unvollständig“ |
| **Ausleihe (Protokoll)** | Ein Eintrag pro Vorgang: Exemplar, Lehrkraft (oder nur Klasse, siehe Datenschutzmodus), Ausleihdatum, geplantes und tatsächliches Rückgabedatum, Status (angefragt, genehmigt, ausgeliehen, zurück, abgelehnt), genehmigt von, übergeben von |

Zusätzlich:

- **Verbrauchsmaterial** (z. B. Protokollbögen): Bestand, Mindestmenge, Bezug zum Test, Bestellhinweis an eine konfigurierbare Stelle (Sekretariat).
- **Kategorien und Standorte** als pflegbare Stammdaten.
- Der Ausleihstatus eines Exemplars wird **aus dem Protokoll abgeleitet**, nicht am Exemplar gespeichert.

## Zwei Ebenen

1. **Katalog**: Alles Material steht drin, auch frei zugängliches Alltagsmaterial, jeweils mit festem Standort.
2. **Ausleihe mit Scan**: Nur für Titel mit Flag „ausleihbar“ (Tests, Technik, wertvolle oder gefragte Medien). Diese zeigen zusätzlich: verfügbar / ausgeliehen bis / bei wem (je nach Rechten).

## Rollen und Rechte

| Rolle | Rechte |
| --- | --- |
| Administrator | Alles inkl. Einstellungen, Benutzer, Import/Export, Löschfristen |
| Verwalter | Katalog, Exemplare, Etiketten, Rückgabekiste, alle Ausleihen einsehen und korrigieren |
| Zuständige Person | Freigaben und Übergabe-Scan für die ihr zugeordneten Titel |
| Lehrkraft | Katalog lesen, ausleihen, eigene Ausleihen sehen und verlängern |
| Sekretariat (optional) | Nachbestellhinweise empfangen und abhaken |

- Lehrkräfte können Stammdaten nicht verändern.
- **Änderungsprotokoll** (wer, wann, was) für alle Datensätze; Wiederherstellen alter Stände durch Verwalter.
- Mindestens zwei Administratoren empfohlen (Hinweis in der Einrichtung).

## Funktionen

### Erfassen und Importieren

- Titel und Exemplare manuell anlegen, bearbeiten, mehrere Exemplare eines Titels in einem Schritt.
- **ISBN-Abruf**: ISBN scannen oder eintippen, Daten automatisch füllen. Quellen in dieser Reihenfolge: Deutsche Nationalbibliothek (SRU-Schnittstelle), dann Open Library, dann Google Books. Ergebnis vor dem Speichern bestätigen lassen.
- **Massenerfassung**: Liste von ISBNs (gescannt in Folge oder als CSV) einlesen, Daten gesammelt abrufen, Vorschau-Tabelle, dann importieren.
- **CSV/Excel-Import** vorhandener Bestände (z. B. Export einer Microsoft List) mit Spaltenzuordnung im Assistenten; vorhandene Inventarnummern übernehmen.
- Konfigurierbares **Nummernschema** für neue Inventarnummern (Präfix, laufende Nummer), damit alte und neue Nummern einheitlich sind.
- Materialien ohne ISBN (z. B. Tests der Testzentrale) normal von Hand anlegen.

### QR-Codes und Etiketten

- QR-Code enthält **nur die Inventarnummer** (kein Link, keine Daten), damit Etiketten auch nach Systemwechsel gültig bleiben.
- Druck als PDF für gängige Etikettenbögen (z. B. Avery Zweckform), Layout wählbar; auf dem Etikett: QR-Code, Inventarnummer, Kurztitel.
- Auswahl, welche Exemplare gedruckt werden (neue, nach Kategorie, einzeln).
- Zusätzlich druckbar: **Nachbestellkarten** für Verbrauchsmaterial und ein **Plakat** mit QR-Code zur App.

### Scannen

- Mobil optimierte Web-App (PWA) mit **Kamera-Scanner** im Browser, gedacht für die privaten Handys der Lehrkräfte; keine App-Store-Installation.
- **USB-Handscanner** am PC (Tastatureingabe) wird überall unterstützt.
- Immer möglich: Inventarnummer von Hand eintippen.
- Scannen eines Codes öffnet sofort das Exemplar mit der passenden Aktion (ausleihen, zurückgeben, anfragen).

### Ausleihen und Zurückgeben

- Ausleihen: Scan → Bestätigen. Rückgabedatum vorausgefüllt (Standardfrist je Kategorie einstellbar).
- Verlängern durch die Lehrkraft, sofern keine Anfrage vorliegt.
- **Rückgabekiste-Modus**: Verwalter scannt viele Exemplare nacheinander zurück; bei Testkoffern wird die Inhaltsliste angezeigt und „vollständig / unvollständig“ abgefragt.
- Übersicht „Meine Ausleihen“ für jede Lehrkraft.

### Freigabepflichtige Medien

- Lehrkraft stellt nur eine **Anfrage**; Status „angefragt“.
- Zuständige Person (bei Abwesenheit die Vertretung) wird benachrichtigt und genehmigt oder lehnt ab.
- Als ausgeliehen gilt das Exemplar **erst, wenn die zuständige Person bei der Übergabe den QR-Code scannt**.
- Nur zuständige Personen und Verwalter dürfen freigabepflichtige Medien ausbuchen.

### Reservierung (spätere Phase)

- Exemplar für ein Datum oder eine Unterrichtsstunde vormerken, ähnlich der Ressourcenbuchung in Untis.
- Kalenderansicht pro Titel; Konflikte anzeigen.

### Benachrichtigungen

- Versand per **E-Mail (SMTP)**, optional später Webhooks (z. B. für Teams oder Matrix).
- Erinnerung am Tag vor der Rückgabe, Hinweis bei Überfälligkeit nach einstellbarer Frist, dann zusätzlich an Verwalter.
- Freigabe-Anfragen an zuständige Person.
- Nachbestellhinweis an das Sekretariat, ausgelöst durch Scan der Nachbestellkarte oder Unterschreiten der Mindestmenge.

### Suchen und Übersichten

- Volltextsuche, Filter nach Kategorie, Förderschwerpunkt, Standort, Verfügbarkeit.
- Ansichten: offene Ausleihen, überfällige, nach Lehrkraft, nach Exemplar, unvollständige Testkoffer.
- **Hinweis auf veraltete Tests** anhand des Normjahrs (Schwelle einstellbar).
- Statistik: Ausleihen pro Titel und Zeitraum (auch nach Anonymisierung verfügbar).

### Datenschutz

- **Löschfrist** einstellbar: abgeschlossene Ausleihen werden nach Ablauf automatisch **anonymisiert** (Name entfernt, Statistik bleibt).
- **Sichtbarkeit der Namen** einstellbar: nur Verwalter und zuständige Personen, oder alle Lehrkräfte (damit man nachfragen kann).
- **Modus ohne Personenbezug**: statt Lehrkraft nur Klasse oder Raum erfassen – für die Zeit bis zur Zustimmung des Personalrats.
- Keine Schülerdaten. Kein Tracking, keine externen Ressourcen im Frontend außer den ISBN-Abfragen (abschaltbar).
- Erzeugbare **Kurzbeschreibung der Verarbeitung** (welche Daten, Zweck, Fristen, Zugriff) als Vorlage für Datenschutzbeauftragte und Personalrat.

### Export und Sicherung

- Vollständiger Export aller Daten als CSV (eine Datei pro Tabelle) und als JSON, per Knopfdruck.
- **Automatische Sicherung** nach Zeitplan (z. B. monatlich) in ein eingebundenes Verzeichnis; Anzahl aufbewahrter Sicherungen einstellbar.
- Wiederherstellung aus einer Sicherung über die Kommandozeile, dokumentiert.

### Anmeldung

- Lokale Benutzerkonten mit Passwort und Einladung per E-Mail.
- Optional **OIDC/SAML** (z. B. Microsoft Entra, Google, Landes-Identitätsdienste) und LDAP, damit Schulen vorhandene Konten nutzen können.
- Massenanlage von Lehrkräften per CSV.

## Technische Anforderungen

- **Docker ist der Standardweg der Auslieferung, aber keine Abhängigkeit der App.** Die App folgt den Twelve-Factor-Prinzipien: Konfiguration ausschließlich über Umgebungsvariablen, Zustand nur in Datenbank und einem Datenverzeichnis, keine Annahmen über Container-Interna im Code. So muss sie ohne Umbau auch laufen:
    - mit Podman,
    - nativ installiert unter Linux und Windows (Installationsanleitung beilegen),
    - auf NAS-Systemen mit Container-Unterstützung (z. B. Synology),
    - später als gehosteter Dienst oder auf Kubernetes für Sachaufwandsträger mit vielen Schulen.
- Auslieferung als **Docker-Image** plus `docker-compose.yml` (App + Datenbank). SQLite für kleine Schulen als Option, PostgreSQL als Standard.
- Konfiguration über Umgebungsvariablen und `.env.example`; persistente Daten nur in benannten Volumes.
- Healthcheck, sauberer Start ohne Internetzugang (ISBN-Abruf dann deaktiviert).
- Betrieb hinter Reverse Proxy mit **HTTPS** (für den Kamerazugriff im Browser zwingend) – Beispielkonfiguration für Caddy beilegen.
- Ressourcenschonend: läuft auf einem kleinen Server oder Mini-PC.
- Mobile first, barrierearm (große Schaltflächen, gute Kontraste), Oberfläche auf Deutsch, Texte übersetzbar angelegt.
- Eine Instanz pro Schule als Standard; Mandantenfähigkeit (mehrere Schulen in einer Instanz, z. B. für einen Sachaufwandsträger) im Datenmodell vorbereiten, aber nicht im MVP umsetzen.
- Automatisierte Tests für Datenmodell, Ausleihlogik, Freigabeablauf, Anonymisierung und Import.
- Dokumentation: Installationsanleitung für Nicht-Experten, Kurzanleitung für Lehrkräfte (1 Seite), Admin-Handbuch.

## Phasen

1. **MVP – Katalog**: Datenmodell, Rollen, Anmeldung lokal, Titel/Exemplare/Standorte, CSV-Import, Suche, Export, Docker-Setup.
2. **Erfassung und Etiketten**: ISBN-Abruf einzeln und gesammelt, Nummernschema, Etiketten-PDF.
3. **Ausleihe**: Scanner-PWA, Ausleihen/Zurückgeben, Rückgabekiste-Modus, Testkoffer-Inhaltslisten, E-Mail-Erinnerungen.
4. **Freigaben und Verbrauchsmaterial**: Anfrage-Workflow mit Übergabe-Scan, Vertretung, Nachbestellkarten.
5. **Datenschutz und Betrieb**: Anonymisierung, Sichtbarkeitsstufen, Modus ohne Namen, automatische Sicherung, Verarbeitungsbeschreibung.
6. **Erweiterungen**: Reservierung nach Datum/Stunde, OIDC/LDAP, Statistik, Webhooks, Mandantenfähigkeit.

## Offene Entscheidungen

- Fork von OpenLibry oder Neubau?
- Technologie-Stack (Vorschlag von Claude Code mit Begründung).
- Lizenz für eine Veröffentlichung (z. B. AGPL oder MIT).
- Name des Projekts.
- Standardfristen für Rückgabe und Anonymisierung.
