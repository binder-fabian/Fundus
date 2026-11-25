# Fundus – Funktionsumfang

Stand: 25. November 2026 (Phasen 1–6) · Autor: Fabian Binder

Diese Datei beschreibt fachlich, was Fundus kann: Rollen, Datenobjekte, Abläufe, Regeln und automatische Aufgaben. Sie ist unabhängig von der Technik geschrieben, damit sich die Funktionen auf einer anderen Plattform nachbauen lassen, zum Beispiel mit SharePoint-Listen, Power Apps und Power Automate. Wie Fundus selbst technisch gebaut ist (Django, PostgreSQL), steht in `PLAN.md`.

Fundus ist unter der AGPL-3.0 lizenziert. Die hier beschriebenen Funktionen und Regeln darf jede Schule frei nachbauen. Wer Quelltext aus Fundus übernimmt, muss die AGPL beachten.

**Hinweis für Claude oder andere KI-Assistenten:** Diese Datei ist die verbindliche Beschreibung des umgesetzten Stands. `SPEC.md` ist der ursprüngliche Auftrag und weicht an mehreren Stellen ab (zum Beispiel Teams statt „zuständige Person + Vertretung“, Reservierungen statt Wunschzeitraum bei Anfragen). Bei Widersprüchen gilt diese Datei.

## 1. Leitgedanken

- **Ausleihen geht schneller, als es zu lassen:** App öffnen, QR-Code scannen, „Ausleihen“ antippen. Einziges Feld ist das vorausgefüllte Rückgabedatum.
- **Übersicht:** Jede Lehrkraft sieht, was es gibt, wo es steht und ob es frei ist.
- **Datensparsam:** Keine Daten von Schülerinnen und Schülern. Namen von Lehrkräften nur, wo nötig, und mit Löschfristen. Keine Auswertung nach Personen.
- **Daten gehören der Schule:** Vollständiger Export jederzeit, offene Formate.
- **Deutsche Oberfläche** mit „Sie“, große Schaltflächen, gute Kontraste, zuerst fürs Handy gestaltet.

## 2. Rollen und Rechte

Jede Person hat genau eine Rolle. Zuständigkeit für einzelne Titel ist keine Rolle, sondern ergibt sich aus der Mitgliedschaft in einem **Team** (Abschnitt 4).

| Rolle | Darf |
| --- | --- |
| Administrator | alles: Benutzer, Einstellungen, Import/Export, Sicherung, dazu alles von „Verwalter“ |
| Verwalter | Katalog, Exemplare, Stammdaten, Teams, Etiketten pflegen; alle Ausleihen sehen und korrigieren; Rückgabekiste; Änderungsprotokoll ansehen und alte Stände wiederherstellen; Statistik; Nachbestellungen bearbeiten |
| Lehrkraft | Katalog lesen und durchsuchen; für sich selbst ausleihen, zurückgeben, verlängern, reservieren, anfragen |
| Sekretariat | wie Lehrkraft, dazu Nachbestellhinweise empfangen und abhaken |
| Mitglied eines Teams (zusätzlich zur Rolle) | für die Titel des Teams: Anfragen genehmigen oder ablehnen, übergeben, zurückbuchen, für andere ausleihen |

Weitere Regeln:

- Lehrkräfte können Stammdaten nicht ändern.
- Der letzte aktive Administrator kann nicht deaktiviert oder herabgestuft werden. Solange es nur einen gibt, zeigt Fundus einen Hinweis.
- **Wer sieht, bei wem etwas ist?** Einstellbar: nur Verwaltung und zuständiges Team (Standard) oder alle angemeldeten Lehrkräfte. Andere sehen nur „ausgeliehen bis …“. Die Gesamtübersicht aller Ausleihen bleibt immer der Verwaltung vorbehalten.

## 3. Datenobjekte

Kern sind drei getrennte Objekte: **Titel** (was), **Exemplar** (welches Stück) und **Ausleihe** (Protokoll der Vorgänge). Ob ein Exemplar ausgeliehen ist, wird **nie am Exemplar gespeichert**, sondern immer aus den Ausleihen abgeleitet.

### Titel (Katalogeintrag)

Ein Eintrag je Werk oder Material, unabhängig von der Zahl der Stücke.

| Feld | Art | Hinweis |
| --- | --- | --- |
| Titel | Text, Pflicht | |
| Untertitel, Autor/Herausgeber, Verlag, Auflage | Text | |
| ISBN | Text | wird normalisiert und auf Prüfziffer geprüft |
| Kategorie | Verweis, Pflicht | bestimmt Ausleihfrist und Nummernpräfix |
| Förderschwerpunkte | Mehrfachverweis | |
| Beschreibung | langer Text | |
| Coverbild | Bild | hochgeladen oder per ISBN-Abruf |
| Normjahr | Zahl | bei Tests; daraus „Normierung veraltet“ |
| Inhaltsliste | langer Text, ein Teil je Zeile | bei Testkoffern; wird bei der Rückgabe abgefragt |
| ausleihbar | Ja/Nein | nur diese Titel werden per Scan ausgeliehen und zeigen ihren Status |
| freigabepflichtig | Ja/Nein | nur zusammen mit „ausleihbar“; Ausleihe nur über Anfrage und Übergabe |
| zuständiges Team | Verweis | genehmigt und übergibt |
| angelegt am, geändert am | Zeitpunkt | |

### Exemplar

Ein Eintrag je physischem Stück.

| Feld | Art | Hinweis |
| --- | --- | --- |
| Titel | Verweis, Pflicht | |
| Inventarnummer | Text, Pflicht | eindeutig ohne Rücksicht auf Groß-/Kleinschreibung; einziger Inhalt des QR-Codes |
| Standort | Verweis | |
| Zustand | Auswahl | gut, Gebrauchsspuren, beschädigt |
| Notiz | langer Text | fehlende Teile werden hier vermerkt |
| unvollständig | Ja/Nein | gesetzt bei Rückgabe mit fehlenden Teilen; bleibt ausleihbar, mit deutlichem Hinweis |
| Etikett gedruckt am | Zeitpunkt | für die Auswahl „noch nicht gedruckt“ |

### Ausleihe (Protokoll)

Ein Eintrag je Vorgang. Auch Anfragen und Reservierungen sind Ausleihen, nur mit anderem Status. Dadurch gelten Anonymisierung, Auskunft und Konto löschen automatisch für alle Vorgänge.

| Feld | Art | Hinweis |
| --- | --- | --- |
| Titel | Verweis, Pflicht | Anfragen und Reservierungen gelten dem Titel |
| Exemplar | Verweis | steht erst bei Ausgabe fest |
| Lehrkraft | Verweis auf Person | entweder Lehrkraft … |
| Klasse oder Raum | Text | … oder dies (Modus ohne Namen); eins von beiden ist Pflicht, außer nach Anonymisierung |
| Status | Auswahl | siehe unten |
| ausgeliehen am | Zeitpunkt | Pflicht bei „ausgeliehen“ und „zurück“ |
| Rückgabe geplant am | Datum | |
| zurückgegeben am | Zeitpunkt | Pflicht bei „zurück“ |
| angefragt am, entschieden am | Zeitpunkt | |
| genehmigt von, übergeben von | Verweis auf Person | |
| Nachricht, Begründung der Ablehnung | Text | |
| reserviert ab, reserviert bis | Zeitpunkt | Zeitraum; Ende ausschließlich |
| Stunden | Text | z. B. „3.–4. Stunde“; leer bei ganzen Tagen |
| Reservierungsgruppe | Kennung | verbindet mehrere Exemplare einer Reservierung („2 Tablet-Koffer“) |
| Versandmarken | Zeitpunkte | je Erinnerungsart einer, damit jede Mail nur einmal rausgeht |
| anonymisiert am | Zeitpunkt | |

**Status:**

| Status | Bedeutung |
| --- | --- |
| angefragt | Anfrage für einen freigabepflichtigen Titel, wartet auf das Team |
| genehmigt | Team hat zugestimmt, Material noch nicht übergeben |
| reserviert | Zeitraum für einen nicht freigabepflichtigen Titel vorgemerkt |
| ausgeliehen | Exemplar ist ausgegeben |
| zurück | abgeschlossen |
| abgelehnt | Team hat abgelehnt (mit Begründung) |
| zurückgezogen | von der Lehrkraft zurückgezogen oder storniert |
| verfallen | nicht abgeholt (Regeln in Abschnitt 6 und 7) |

Übergänge:

```
Freigabepflichtig:  angefragt ──genehmigen──▶ genehmigt ──Übergabe-Scan──▶ ausgeliehen ──▶ zurück
                        │                        │
                        ├──ablehnen──▶ abgelehnt └──nicht abgeholt──▶ verfallen
                        └──zurückziehen──▶ zurückgezogen

Reservierung:       reserviert ──Abholung (Scan)──▶ ausgeliehen ──▶ zurück
                        ├──stornieren──▶ zurückgezogen
                        └──Ende des Zeitraums──▶ verfallen

Direkt:             ausgeliehen ──▶ zurück
```

Feste Regeln:

- Je Exemplar höchstens **eine** Ausleihe mit Status „ausgeliehen“.
- Ein reservierter Zeitraum endet immer nach seinem Beginn.

### Stammdaten

| Objekt | Felder |
| --- | --- |
| Kategorie | Name (eindeutig), Standard-Ausleihfrist in Tagen (Vorgabe 28), Präfix für Inventarnummern (optional) |
| Förderschwerpunkt | Name (eindeutig) |
| Standort | Raum, Regal/Fach, Hinweis; Raum + Regal eindeutig |
| Team | Name (eindeutig), Mitglieder (beliebig viele Personen) |

Was noch verwendet wird, lässt sich nicht löschen. Vorgeschlagene Fristen: Tests und Technik 14 Tage, Bücher und Material 28 Tage.

### Person (Benutzerkonto)

E-Mail-Adresse (Anmeldename, eindeutig, ohne Rücksicht auf Groß-/Kleinschreibung), Vorname, Nachname, Rolle, aktiv, „abwesend bis einschließlich“ (Datum), angelegt am.

### Verbrauchsmaterial

| Feld | Hinweis |
| --- | --- |
| Bezeichnung | z. B. „Protokollbögen WISC-V“ |
| Kennung | eindeutig, z. B. `NB-0001`; steht im QR-Code der Nachbestellkarte |
| gehört zu | Verweis auf einen Titel (optional) |
| Standort, Einheit, Notiz | |
| Bestand zählen | Ja/Nein; ohne Zählen genügt die Nachbestellkarte |
| Bestand, Mindestmenge | nur beim Zählen |
| Bestellhinweis | Lieferant, Artikelnummer, Packungsgröße |

### Nachbestellhinweis

Material, Status (offen → bestellt → geliefert, oder verworfen), Anlass (Karte gescannt, Mindestmenge erreicht, von Hand), gemeldet am/von, bestellt am, geliefert am, gelieferte Menge, bearbeitet von. Je Material höchstens ein offener Hinweis (offen oder bestellt).

### Schuleinstellungen

Eine Zeile mit allen Einstellungen, die die Schule ohne Technikwissen ändern kann:

| Bereich | Einstellungen (Vorgabe) |
| --- | --- |
| Allgemein | Name der Schule |
| Nummernschema | Präfix (`FS-`), Stellenzahl (4), nächste Nummer |
| Katalog | veraltete Tests ab … Jahren nach Normjahr (10), ISBN-Abruf an/aus (an) |
| Erinnerungen | an/aus (an); … Tage vor Ablauf (1); überfällig nach … Tagen (3); an Verwaltung nach … Tagen (14) |
| Anfragen | Team erinnern nach … Tagen ohne Bearbeitung (3); genehmigte Anfragen ohne Zeitraum verfallen nach … Tagen ohne Abholung (14) |
| Schuljahr und Reservierung | Schuljahresbeginn (01.08.), Beginn 2. Halbjahr (01.02.), Stundenraster (8 Stunden à 45 Min. ab 8:00, eine Zeile je Stunde wie `08:00-08:45`), Reservierungserinnerungen an/aus (an) |
| Verbrauchsmaterial | E-Mail-Adresse für Nachbestellhinweise |
| Datenschutz | Sichtbarkeit der Namen (Team), Ausleihen ohne Namen (aus), Namen entfernen nach … Tagen (365), „wer hat geändert“ entfernen nach … Tagen (365) |
| Sicherung | aus / täglich / wöchentlich / monatlich (täglich), Anzahl aufbewahren (14) |
| Anmeldung mit Schulkonto | neue Konten automatisch anlegen (aus), nur für E-Mail-Domains …, Passwort-Anmeldung für alle oder nur Administratoren (alle) |
| Etiketten | Druckversatz rechts/unten in mm |

## 4. Teams und Vertretung

- Ein Team (z. B. „Diagnostik-Team“) hat eine bis beliebig viele Personen. Eine einzelne zuständige Person ist ein Team aus einer Person.
- Am Titel wird das zuständige Team gewählt. Alle Mitglieder haben dieselben Rechte und vertreten sich gegenseitig.
- Wer „abwesend bis …“ einträgt, bekommt in der Zeit keine Anfragen.
- Sind alle Mitglieder abwesend oder hat ein freigabepflichtiger Titel kein Team, gehen Anfragen an die Verwaltung. Die Übersicht der Verwaltung listet freigabepflichtige Titel ohne Team.

## 5. Ausleihen, Zurückgeben, Verlängern

**Scannen:** Der QR-Code enthält nur die Inventarnummer. Scannen (Handykamera im Browser, USB-Handscanner oder Eintippen) öffnet sofort das Exemplar mit der passenden Aktion: ausleihen, zurückgeben, verlängern, anfragen, übergeben oder abholen. Beim Eintippen schlägt das Feld passende Exemplare und Verbrauchsmaterial vor. Eine exakt eingegebene Inventarnummer springt direkt zum Exemplar. Eine Nachbestellkarte öffnet das Verbrauchsmaterial.

**Ausleihen:**

- Nur ausleihbare, nicht freigabepflichtige Titel. Das Exemplar darf nicht schon ausgeliehen sein.
- Rückgabedatum vorausgefüllt: heute + Frist der Kategorie, änderbar, nicht in der Vergangenheit.
- Lehrkräfte leihen nur für sich. Verwaltung und Mitglieder des zuständigen Teams können für andere ausleihen, auch freigabepflichtige Titel (spontane Übergabe ohne Anfrage).
- **Rücksicht auf Reservierungen:** Ist der Titel ab einem Datum ausgebucht, begrenzt Fundus das Rückgabedatum auf den Tag davor und sagt das. Ist heute schon alles reserviert, geht Ausleihen nur noch über eine eigene Reservierung.
- Hat die Person für heute eine Reservierung dieses Titels, wird beim Ausleihen diese Reservierung abgeholt (Abschnitt 7).

**Zurückgeben:**

- Jede angemeldete Person kann zurückbuchen, etwa wenn ein Exemplar im Lehrerzimmer liegen geblieben ist. Freigabepflichtige Titel bucht nur das zuständige Team oder die Verwaltung zurück.
- Hat der Titel eine Inhaltsliste, fragt Fundus „vollständig?“ ab. Fehlende Teile werden angehakt, das Exemplar wird als unvollständig markiert, die Teile stehen in der Notiz.

**Verlängern:**

- Nur die ausleihende Person, beliebig oft.
- Nicht möglich, solange für den Titel eine Anfrage „so bald wie möglich“ offen ist.
- Neues Datum: heute + Frist, mindestens aber altes Datum + Frist. Steht eine Reservierung bevor, höchstens bis zum Tag davor. Geht auch das nicht, ist Verlängern nicht möglich.
- Verlängern setzt die Erinnerungen zurück.

**Rückgabekiste (Verwaltung):** Viele Exemplare nacheinander scannen, jedes wird sofort zurückgebucht. Testkoffer fragen vorher den Inhalt ab.

**Übersichten:**

- Startseite jeder Person: „Meine Ausleihen“ mit Verlängern, eigene Anfragen, eigene Reservierungen. Für Teammitglieder zusätzlich offene Anfragen ihres Teams.
- Verwaltung: offene, überfällige und alle Vorgänge, Filter nach Lehrkraft, unvollständige Exemplare, freigabepflichtige Titel ohne Team.

## 6. Anfragen für freigabepflichtige Titel

1. **Anfragen:** Die Lehrkraft fragt auf der Titel- oder Exemplarseite an, mit optionaler Nachricht:
   - **„So bald wie möglich“:** ohne Zeitraum, oder
   - **„Für einen bestimmten Zeitraum“:** ganze Tage oder Stunden, mit Kalender wie bei der Reservierung. Fundus prüft, ob im Zeitraum ein Exemplar frei ist. Der Zeitraum ist schon während der Prüfung **vorgemerkt**, damit niemand dazwischenbucht.
   - Eine Person kann je Titel nur eine offene Anfrage ohne Zeitraum haben.
2. **Benachrichtigen:** Alle anwesenden Teammitglieder bekommen eine E-Mail und sehen die Anfrage auf ihrer Startseite.
3. **Entscheiden:** Wer zuerst genehmigt oder ablehnt (mit Begründung), erledigt sie für alle. Die Lehrkraft bekommt eine E-Mail. Mit **„Anderer Zeitraum“** genehmigt das Team für andere Tage, etwa wenn der gewünschte Zeitraum nicht passt oder schon vorbei ist. Ist der Zeitraum vorbei, geht Genehmigen nur mit neuem Zeitraum.
4. **Übergabe:** Die Lehrkraft holt das Material beim Team ab. Ein Teammitglied scannt ein **freies Exemplar**. Die Exemplarseite zeigt die genehmigten Anfragen zu diesem Titel, ein Tipp auf „An … übergeben“ bucht aus. Erst jetzt gilt das Exemplar als ausgeliehen. „Übergeben von“ wird gespeichert. Rückgabedatum: Ende des Zeitraums, sonst Frist der Kategorie, jeweils begrenzt durch spätere Reservierungen.
5. **Zurückziehen:** Die Lehrkraft kann offene Anfragen zurückziehen.

**Fristen:**

- Unbearbeitete Anfragen **verfallen nie von selbst**. Das Team wird nach 3 Tagen erinnert, bei Anfragen mit Zeitraum zusätzlich am Vortag des Beginns. Ist der Zeitraum vorbei, steht die Anfrage als „Zeitraum vorbei“ beim Team, bis es entscheidet.
- **Genehmigte**, aber nicht abgeholte Anfragen verfallen: ohne Zeitraum nach 14 Tagen, mit Zeitraum an dessen Ende. Lehrkraft und Team bekommen dann eine E-Mail.

## 7. Reservierung

Für ausleihbare Titel, die nicht freigabepflichtig sind. Bei freigabepflichtigen Titeln ersetzt die Anfrage mit Zeitraum die Reservierung.

**Kalender:** Auf der Titelseite führt „Reservieren“ zu einem Wochenkalender. Er zeigt je Tag und je Unterrichtsstunde, wie viele Exemplare frei sind, mit „‹ früher“ und „später ›“ zum Blättern. Ein Tipp auf einen freien Tag oder eine freie Stunde trägt sie ins Formular ein. Das Wochenende erscheint nur, wenn dort eine Reservierung oder Anfrage liegt. Namen erscheinen nach der Sichtbarkeitseinstellung.

**Zeitraum:**

- **Ganze Tage** (von–bis): vom Beginn des ersten bis zum Beginn des Tages nach dem letzten Tag.
- **Stunden an einem Tag** (z. B. 3.–4. Stunde): Beginn der ersten bis Ende der letzten Stunde laut Stundenraster. Gespeichert werden die Uhrzeiten, ein geändertes Raster verschiebt also keine bestehenden Reservierungen.
- Nicht in der Vergangenheit.
- **Anzahl:** Bei Titeln mit mehreren Exemplaren auch mehrere auf einmal. Fundus legt je Exemplar einen Eintrag mit gemeinsamer Gruppenkennung an, Stornieren gilt für die ganze Gruppe.

**Belegungsprüfung:** Die Kapazität eines Titels ist die Zahl seiner Exemplare. Belegt ist ein Titel zu jedem Zeitpunkt durch:

- laufende Ausleihen, bis zum Ende ihres Rückgabetags und mindestens bis heute (für Stunden abgeholte Ausleihen bis zum Ende der letzten Stunde),
- Reservierungen,
- Anfragen mit Zeitraum, solange sie angefragt oder genehmigt sind.

Frei ist, was zur **höchsten gleichzeitigen Belegung** im gewünschten Zeitraum fehlt. Ein bloßes Zählen der Überschneidungen reicht nicht, denn zwei Reservierungen am Vormittag und am Nachmittag belegen gemeinsam nur ein Exemplar. Reicht es nicht, nennt Fundus den frühesten Beginn, zu dem ein gleich langer Zeitraum frei ist.

Prüfen und Anlegen müssen in einem Schritt geschehen, damit zwei gleichzeitige Buchungen nicht beide durchgehen. Fundus sperrt dafür den Titel während der Buchung.

**Abholen:** Ab dem ersten Tag das Exemplar scannen und „Ausleihen“ antippen. Die Reservierung wird zur Ausleihe, Rückgabedatum ist das Ende des Zeitraums. Im Modus ohne Namen kann abholen, wer dieselbe Klasse oder denselben Raum einträgt.

**Hinweis an die aktuelle Ausleihe:** Klappt eine neue Reservierung oder Anfrage mit Zeitraum nur, wenn ein ausgeliehenes Exemplar pünktlich zurückkommt, bekommt die Person, die es gerade hat, eine freundliche E-Mail („Bitte pünktlich zurückgeben“). Die Mail geht einmal je Ausleihe und nennt nicht, wer reserviert hat.

**Stornieren:** Eigene Reservierungen auf der Startseite. Die Verwaltung kann jede Reservierung stornieren.

**Verfall und Erinnerung:**

- Nicht abgeholte Reservierungen bleiben bis zum Ende ihres Zeitraums bestehen und verfallen erst dann.
- Am Vortag kommt eine Erinnerung. Am Morgen nach dem ersten Tag kommt ein Hinweis, falls noch nicht abgeholt. Beides ist abschaltbar und entfällt im Modus ohne Namen.

## 8. Verbrauchsmaterial und Nachbestellung

- **Bestand zählen ist freiwillig** je Material. Mit Zählen werden Entnahmen gebucht. Wird die Mindestmenge erreicht oder unterschritten, entsteht automatisch ein Nachbestellhinweis.
- **Nachbestellkarte:** A6-Karte mit QR-Code (Kennung), Bezeichnung und Bestellhinweis, vier je A4-Blatt. Sie liegt im Stapel an der Stelle, ab der nachbestellt werden soll. Wer sie erreicht, scannt sie und tippt „Nachbestellen“.
- **Empfänger:** alle mit der Rolle Sekretariat (Liste und E-Mail) und die Adresse aus den Einstellungen. Fehlen beide, bekommt die Verwaltung die Hinweise, und die Einstellungen zeigen eine Warnung.
- **Abhaken:** bestellt → geliefert (mit Menge, füllt den Bestand auf) oder verwerfen. Solange ein Hinweis offen ist, entsteht kein zweiter.
- Der zugehörige Titel zeigt sein Verbrauchsmaterial.

## 9. Katalog pflegen und erfassen

- **Titel und Exemplare** von Hand anlegen. Beim Anlegen gleich mehrere Exemplare erzeugen: nur Anzahl (Nummern aus dem Nummernschema), als Liste oder als Folge (Präfix, Startnummer, Anzahl).
- **Nummernschema:** allgemeines Präfix und Stellenzahl, optional ein eigenes Präfix je Kategorie (`B-`, `T-`, `IT-`), jede Folge zählt für sich. Fundus setzt immer nach der höchsten vorhandenen Nummer mit diesem Präfix fort, auch nach einem Import. Vergebene Nummern ändern sich nie.
- **ISBN-Abruf:** ISBN eintippen oder scannen, Fundus fragt nacheinander Deutsche Nationalbibliothek (SRU), Open Library und, mit eigenem Schlüssel, Google Books. Gefüllt werden nur leere Felder, gespeichert wird erst nach Bestätigung. Cover kommen von Open Library und werden lokal gespeichert. Die Abfrage läuft vom Server aus, Ergebnisse werden 30 Tage zwischengespeichert, abschaltbar, und ohne Internet funktioniert alles andere weiter.
- **Massenerfassung:** ISBNs nacheinander scannen oder als Datei hochladen. Eine Vorschau lädt jede Zeile einzeln. Vorhandene Titel bekommen nur neue Exemplare, mehrfach gescannte ISBNs ergeben mehrere Exemplare. Kategorie, Standort und „ausleihbar“ gelten für alle. Nicht gefundene ISBNs bleiben als Liste zum Nacharbeiten.
- **Import aus CSV oder Excel** (z. B. Export einer Microsoft List): Spalten zuordnen (bekannte Namen automatisch, Zuordnung als Vorlage speicherbar), Pflicht sind Inventarnummer und Titel. Die Vorschau markiert fehlerhafte Zeilen. Der Import gelingt ganz oder gar nicht, danach gibt es einen Bericht. Zeilen mit gleicher ISBN oder gleichem Titel + Autor werden zu einem Titel mit mehreren Exemplaren zusammengefasst, auch mit vorhandenen Titeln. Vorhandene Inventarnummern werden übernommen.
- **Suche:** ein Suchfeld mit Ergebnissen beim Tippen über Titel, Autor, ISBN, Inventarnummer und Beschreibung. Groß-/Kleinschreibung und Umlaute sind egal („mueller“ findet „Müller“). Filter: Kategorie, Förderschwerpunkt, Standort, Verfügbarkeit. Filter stehen in der Adresse, damit Links teilbar sind.
- **Veraltete Tests:** Ist das Normjahr älter als die eingestellte Schwelle, erscheint „Normierung veraltet“.
- **Änderungsprotokoll:** Jede Änderung an Titeln, Exemplaren, Stammdaten, Teams, Verbrauchsmaterial, Konten und Ausleihen wird mit Zeitpunkt und Person gespeichert. Bei Titeln, Exemplaren, Stammdaten, Teams und Verbrauchsmaterial sieht die Verwaltung vorher/nachher und kann alte Stände wiederherstellen, auch Gelöschtes.

## 10. Etiketten und Drucksachen

- **Etiketten als PDF:** QR-Code mit nur der Inventarnummer, darunter Inventarnummer und Kurztitel. So bleiben Etiketten auch nach einem Systemwechsel gültig.
- Bögen Avery Zweckform 4732, 6021, 4780, 3651, 3474.
- Auswahl: noch nicht gedruckt, nach Kategorie, Standort, Titel, einzelne oder alle. Startposition für angebrochene Bögen, Testseite und Druckversatz zum Ausrichten. Nach dem Druck „als gedruckt markieren“.
- **Plakat** (A4) mit QR-Code zur Adresse von Fundus und kurzer Anleitung fürs Lehrerzimmer.
- **Nachbestellkarten** (Abschnitt 8).

## 11. E-Mails

| Anlass | Empfänger | Wann |
| --- | --- | --- |
| Einladung mit Link zum Passwort setzen | neue Person | beim Anlegen; Link gilt 14 Tage und nur einmal |
| Passwort vergessen | Person | auf Anforderung |
| Rückgabe morgen | ausleihende Person | 1 Tag vor dem Rückgabedatum |
| Überfällig | ausleihende Person | 3 Tage nach dem Rückgabedatum |
| Überfällige Ausleihen (Sammelmail) | Verwaltung und Administratoren | 14 Tage nach dem Rückgabedatum |
| Bitte pünktlich zurückgeben | ausleihende Person | sobald eine spätere Reservierung oder Anfrage darauf angewiesen ist |
| Neue Anfrage | anwesende Teammitglieder (sonst Verwaltung) | sofort |
| Anfrage wartet noch | Team | nach 3 Tagen ohne Bearbeitung |
| Anfrage beginnt morgen | Team | am Vortag des Zeitraums, wenn noch unbearbeitet |
| Anfrage genehmigt / abgelehnt | anfragende Person | sofort, mit Zeitraum bzw. Begründung |
| Anfrage verfallen | anfragende Person und Team | genehmigt, aber nicht abgeholt |
| Reservierung morgen | reservierende Person | am Vortag |
| Reservierung nicht abgeholt | reservierende Person | am Morgen nach dem ersten Tag |
| Nachbestellhinweis | Sekretariat und eingestellte Adresse | Karte gescannt oder Mindestmenge erreicht |

Jede Erinnerung geht je Vorgang nur einmal raus. Dafür speichert die Ausleihe je Art einen Versandzeitpunkt. Nach dem Verlängern beginnen die Erinnerungen neu. Im Modus ohne Namen gibt es keine Erinnerungen an Lehrkräfte.

## 12. Tägliche Aufgaben

Ein Dienst erledigt einmal täglich ab 7 Uhr:

1. Erinnerungen und Überfällig-Hinweise zu Ausleihen (Abschnitt 11),
2. Erinnerungen an Teams zu offenen Anfragen, Verfall genehmigter Anfragen,
3. Erinnerungen und Hinweise zu Reservierungen, Verfall abgelaufener Reservierungen,
4. Datenschutz-Bereinigung (Abschnitt 13),
5. automatische Sicherung nach Zeitplan.

Fällt ein Lauf aus, holt der nächste alles nach.

## 13. Datenschutz

- **Keine Schülerdaten.** Ausgeliehen wird an Lehrkräfte oder, im Modus ohne Namen, an eine Klasse oder einen Raum.
- **Löschfrist:** Abgeschlossene Vorgänge (zurück, abgelehnt, zurückgezogen, verfallen) verlieren nach 365 Tagen alle Personenangaben: Lehrkraft, Klasse/Raum, genehmigt von, übergeben von, Nachricht, Ablehnungsgrund. Das gilt **auch in den Einträgen des Änderungsprotokolls**. Titel, Exemplar und Daten bleiben für die Statistik. Die Einstellungen zeigen, wie viele Vorgänge der nächste Lauf betrifft, mit Knopf „jetzt anonymisieren“. Erledigte Nachbestellhinweise verlieren ihre Namen nach derselben Frist, abgelaufene Abwesenheiten werden gelöscht.
- **Änderungsprotokoll:** „Wer hat geändert“ wird nach 365 Tagen entfernt, „was“ bleibt.
- **Modus ohne Namen** (z. B. bis zur Zustimmung des Personalrats): Beim Ausleihen und Reservieren wird statt der Person Klasse oder Raum eingetragen, mit Vorschlägen aus früheren Einträgen. Dann gibt es keine „Meine Ausleihen“ und keine Erinnerungen, Überfälliges sieht die Verwaltung. Anfragen laufen weiter mit Namen und E-Mail. Bei der Übergabe trägt das Team Klasse oder Raum ein, und Name, Nachricht und „genehmigt von“ werden sofort gelöscht, auch im Protokoll. Umschalten wirkt nur auf neue Vorgänge.
- **Konto löschen:** möglich, sobald die Person nichts mehr ausgeliehen hat. Ihre Vorgänge werden sofort anonymisiert, offene Anfragen und Reservierungen zurückgezogen, ihr Name verschwindet aus Teams und Protokoll. Für vorübergehend Abwesende gibt es stattdessen „deaktivieren“.
- **Auskunft (Art. 15 DSGVO):** Jede Person lädt unter „Konto → Meine Daten herunterladen“ alles über sich als ZIP mit CSV-Dateien herunter.
- **Verarbeitungsbeschreibung:** Fundus erzeugt aus den aktuellen Einstellungen eine Word-Datei für Datenschutzbeauftragte und Personalrat: Daten, Zweck, Rechtsgrundlage als Vorschlag, Zugriffe, Fristen, Empfänger, Sicherungen, technische Maßnahmen. Gelb markierte Stellen ergänzt die Schule. Nach Änderung einer datenschutzrelevanten Einstellung erinnert Fundus daran, sie neu herunterzuladen.
- **Statistik ohne Personen:** Es gibt bewusst keine Auswertung nach Personen (Leistungs- und Verhaltenskontrolle).
- **Keine externen Ressourcen im Browser,** kein Tracking, Cookies nur für die Anmeldung.

## 14. Statistik

Für Verwaltung und Administration, Zeitraum wählbar: aktuelles Schuljahr, 1. oder 2. Halbjahr, letztes Schuljahr oder frei. Schuljahres- und Halbjahresbeginn kommen aus den Einstellungen, da sie je Bundesland verschieden sind.

- Ausleihen gesamt, Zahl verschiedener Titel, durchschnittliche Ausleihdauer in Tagen
- je Titel: Anzahl, durchschnittliche Dauer, zuletzt ausgeliehen
- je Kategorie und je Förderschwerpunkt
- ausleihbare Titel, die im Zeitraum nicht ausgeliehen wurden
- Anfragen: gesamt, übergeben, offen, abgelehnt, zurückgezogen, verfallen

Gezählt werden auch anonymisierte Vorgänge. Download als Excel-Datei mit einem Blatt je Tabelle.

## 15. Anmeldung und Konten

- **Lokale Konten:** Anmeldung mit E-Mail-Adresse und Passwort, Einladung per E-Mail, „Passwort vergessen“. Massenanlage des Kollegiums per CSV (Vorname, Nachname, E-Mail) mit Vorschau. Ausgeschiedene Personen werden deaktiviert statt gelöscht.
- **Anmeldeschutz:** Nach 5 falschen Passwörtern ist die Anmeldung für diese E-Mail-Adresse 15 Minuten gesperrt (je Gerät beim Vierfachen). „Passwort vergessen“ geht trotzdem.
- **Angemeldet bleiben:** 30 Tage.
- **Anmeldung mit Schulkonto:**
  - per **OIDC** (Microsoft Entra, Google, Keycloak) mit dem Knopf „Mit Schulkonto anmelden“, oder
  - per **LDAP** (paedML, IServ, UCS@school, Active Directory) im normalen Formular, nur verschlüsselt.
  - Zugeordnet wird über die **E-Mail-Adresse**. Rollen und Teams vergibt weiter Fundus.
  - Neue Konten werden standardmäßig nicht angelegt („Bitte an die Verwaltung wenden“). Wahlweise legt Fundus sie automatisch als Lehrkraft an, optional nur für bestimmte E-Mail-Domains.
  - Die Passwort-Anmeldung lässt sich auf Administratoren beschränken, die sie als Notzugang behalten.

## 16. Export und Sicherung

- **Export** (Administration): ZIP mit `katalog.csv` (eine Zeile je Exemplar, wieder importierbar), einer CSV-Datei je Tabelle einschließlich Änderungsprotokoll, allem als JSON und den Coverbildern. Passwörter sind nie enthalten.
- **Automatische Sicherung** nach Zeitplan (Standard täglich, 14 aufbewahren) mit vollständiger Datenbank, Bildern und lesbarem Export. Die Einstellungen zeigen die letzte Sicherung und warnen bei Fehlern. „Jetzt sichern“ legt sofort eine an. Die Wiederherstellung läuft über die Kommandozeile in eine leere Datenbank.

## 17. Bewusst nicht enthalten oder für später

- Ausleihe an Schülerinnen und Schüler
- Auswertungen nach Personen
- SAML (die üblichen Anmeldedienste können OIDC)
- Webhooks für Teams oder Matrix (später, ohne Namen)
- Mehrere Schulen in einer Installation (im Datenmodell vorbereitet, nicht umgesetzt)

## 18. Hinweise für einen Nachbau auf anderer Plattform

Diese Punkte sind in Fundus fachlich wichtig und bei einem Nachbau, etwa mit SharePoint-Listen, leicht zu übersehen:

1. **Status ableiten, nicht speichern.** „Ausgeliehen“ ergibt sich aus einer Ausleihe mit Status „ausgeliehen“. Ein zusätzliches Statusfeld am Exemplar läuft früher oder später auseinander.
2. **Titel und Exemplar trennen.** Anfragen und Reservierungen gelten dem Titel, das Exemplar steht erst bei der Ausgabe fest. Sonst blockiert eine Reservierung ein bestimmtes Stück, obwohl ein anderes frei wäre.
3. **Höchstens eine laufende Ausleihe je Exemplar** und **keine Überbuchung** müssen auch bei gleichzeitigen Zugriffen halten. Listen ohne Transaktionen brauchen dafür eine Prüfung direkt vor dem Speichern und einen Plan für den Fall, dass zwei Buchungen gleichzeitig kommen.
4. **Belegung als höchste gleichzeitige Belegung rechnen**, nicht als Zahl der Überschneidungen (Abschnitt 7).
5. **Zeiträume mit ausschließlichem Ende speichern:** Ganze Tage enden um 0 Uhr des Folgetags. Stunden speichern Uhrzeiten, nicht die Stundennummer.
6. **Jede Mail nur einmal:** je Erinnerungsart einen Versandzeitpunkt am Vorgang speichern und beim Verlängern zurücksetzen.
7. **Anonymisierung muss auch die Versionsgeschichte erfassen.** In SharePoint behält der Versionsverlauf alte Werte und „Geändert von“. Ohne Bereinigung dort stehen Namen nach der Löschfrist weiter im System.
8. **Wo die Daten liegen:** Fundus läuft auf einem Server der Schule. Bei Microsoft 365 liegen alle Namen, Nachrichten und Ausleihdaten in der Microsoft-Cloud. Das muss von der Schule (Datenschutz, Personalrat) freigegeben sein.
