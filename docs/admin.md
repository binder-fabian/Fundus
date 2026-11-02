# Admin-Handbuch

Stand: Phase 4 (Katalog, Erfassung, Etiketten, Ausleihe mit Scanner, Freigaben, Verbrauchsmaterial). Datenschutz-Einstellungen und automatische Sicherung folgen in Phase 5.

## Rollen

| Rolle | Darf |
| --- | --- |
| Administrator | alles: Benutzer, Import und Export, dazu alles von „Verwalter“ |
| Verwalter | Katalog, Exemplare, Stammdaten pflegen; Änderungen ansehen und zurücknehmen |
| Lehrkraft | Katalog ansehen und durchsuchen |
| Sekretariat | wie Lehrkraft; bearbeitet Nachbestellhinweise |

Zuständig für einen Titel ist ein **Team** (siehe unten), keine Rolle. Jede Person hat genau eine Rolle; das Sekretariat bearbeitet zusätzlich die Nachbestellungen.

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
- **Nummernschema:** allgemeines Präfix (z. B. `FS-`), Stellenzahl (z. B. 4 → `0101`) und nächste Nummer. Fundus setzt immer nach der höchsten vorhandenen Nummer mit diesem Präfix fort, auch nach einem Import. Die nächste Nummer wird angezeigt.
- **Präfix je Kategorie:** Unter „Stammdaten → Kategorien“ kann jede Kategorie ein eigenes Präfix bekommen, z. B. `B-` für Bücher, `T-` für Tests, `IT-` für Technik. Jede Folge zählt für sich (B-0001, T-0001 …). Maßgeblich ist die Kategorie des Titels beim Anlegen der Exemplare; vergebene Nummern ändern sich später nie.
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

## Teams

Unter „Stammdaten → Teams“ legen Verwalter Teams an, z. B. „Diagnostik-Team“, mit einer bis beliebig vielen Personen: In der Liste aller Konten bekommt jedes Mitglied einen Haken, ab acht Konten hilft ein Suchfeld. Am Titel wird dann das zuständige Team gewählt. Alle Mitglieder dürfen Anfragen genehmigen, Material übergeben, zurückbuchen und für andere ausleihen; sie vertreten sich gegenseitig.

Wer abwesend ist, trägt unter „Konto“ ein „abwesend bis …“ ein und bekommt in der Zeit keine Anfragen. Sind alle im Team abwesend (oder hat ein Titel kein Team), gehen Anfragen an die Verwaltung. Die Übersicht „Ausleihen“ listet freigabepflichtige Titel ohne Team.

## Ausleihe

- **Scannen:** Auf dem Handy unten „Scannen“ antippen und den QR-Code des Etiketts vor die Kamera halten. Fundus öffnet das Exemplar mit der passenden Aktion. Am PC geht dasselbe mit dem USB-Handscanner im Feld „Inventarnummer“ auf der Startseite; beim Eintippen schlägt das Feld passende Exemplare und Verbrauchsmaterial vor (Nummer oder Titel). Die Kamera braucht HTTPS.
- **Ausleihen:** Das Rückgabedatum ist mit der Frist der Kategorie vorausgefüllt. Lehrkräfte leihen für sich selbst. Verwalter sowie die zuständige Person eines Titels können auch für andere Lehrkräfte ausbuchen.
- **Zurückgeben:** Jede angemeldete Person kann zurückbuchen, z. B. wenn ein Exemplar im Lehrerzimmer liegen geblieben ist. Freigabepflichtige Titel bucht nur die zuständige Person (oder Vertretung bzw. Verwaltung) zurück. Bei Titeln mit Inhaltsliste (Testkoffer) wird abgefragt, ob alles da ist; fehlende Teile markieren das Exemplar als unvollständig und stehen in der Notiz.
- **Verlängern:** durch die ausleihende Lehrkraft, solange keine Anfrage „so bald wie möglich“ vorliegt. Steht eine Reservierung bevor, verlängert Fundus höchstens bis zum Tag davor.
- **Wer sieht Namen?** Verwalter, Administratoren und die zuständige Person. Andere Lehrkräfte sehen nur „ausgeliehen bis …“.
- **Freigabepflichtige Titel** fragen Lehrkräfte an (siehe nächster Abschnitt).

## Reservierung

Auf der Titelseite führt **„Reservieren“** zu einem Wochenkalender: Für jeden Tag und jede Unterrichtsstunde steht dort, wie viele Exemplare frei sind. Eine freie Stunde antippen trägt sie ins Formular ein.

- **Ganze Tage** (von–bis) oder **einzelne Stunden** an einem Tag (z. B. 3.–4. Stunde). Bei Titeln mit mehreren Exemplaren auch mehrere auf einmal, z. B. „2 Tablet-Koffer“.
- Fundus prüft, ob im Zeitraum genug frei ist: laufende Ausleihen bis zu ihrem Rückgabedatum, andere Reservierungen und Anfragen mit Zeitraum. Sonst nennt es den frühesten freien Beginn.
- **Abholen:** Am ersten Tag das Exemplar scannen und „Ausleihen“ antippen. Die Reservierung wird dabei zur Ausleihe; Rückgabe ist das Ende des Zeitraums.
- **Konflikte:** Wer ein Exemplar ausleiht, obwohl der Titel ab einem Datum ausgebucht ist, bekommt das Rückgabedatum auf den Tag davor begrenzt. Ist heute schon alles reserviert, geht Ausleihen nur noch über eine eigene Reservierung (z. B. für die Stunden davor).
- **Verfall:** Nicht abgeholte Reservierungen bleiben bis zum Ende ihres Zeitraums bestehen. Am Vortag bekommt die Person eine Erinnerung, am Morgen nach dem ersten Tag einen Hinweis, falls sie noch nicht abgeholt hat (unter „Einstellungen → Reservierung“ abschaltbar).
- Eigene Reservierungen stehen auf der Startseite und lassen sich dort stornieren. Verwalter können jede Reservierung stornieren.
- Im **Modus ohne Namen** wird für Klasse oder Raum reserviert; abholen kann dann, wer beim Ausleihen dieselbe Klasse einträgt.

**Stundenraster.** Unter „Einstellungen → Reservierung“ eine Zeile je Stunde, z. B. `08:00-08:45`. Die erste Zeile ist die 1. Stunde. Reservierungen speichern die Uhrzeiten; ein neues Raster (z. B. zum Halbjahr) verschiebt also keine bestehenden.

## Anfragen für freigabepflichtige Titel

1. Die Lehrkraft fragt auf der Titel- oder Exemplarseite an: **„So bald wie möglich“** oder **„Für einen bestimmten Zeitraum“** (Tage oder Stunden, mit Kalender wie bei der Reservierung). Ein angefragter Zeitraum ist schon während der Prüfung vorgemerkt, damit niemand dazwischenbucht.
2. Alle anwesenden Mitglieder des Teams bekommen eine E-Mail und sehen die Anfrage auf ihrer Startseite. Wer zuerst **genehmigt** oder **ablehnt** (mit Begründung), erledigt sie für alle; die Lehrkraft wird per E-Mail informiert. Mit **„Anderer Zeitraum“** genehmigt das Team für andere Tage, z. B. wenn der gewünschte Zeitraum nicht passt oder schon vorbei ist.
3. **Übergabe:** Die Lehrkraft holt das Material ab. Jemand aus dem Team scannt den QR-Code eines freien Exemplars; dort steht „An … übergeben“. Erst jetzt gilt es als ausgeliehen. Das Rückgabedatum ist das Ende des Zeitraums, sonst die Frist der Kategorie.

Unbearbeitete Anfragen **verfallen nie von selbst**. Bleibt eine Anfrage 3 Tage liegen, wird das Team erinnert, bei Anfragen mit Zeitraum zusätzlich am Vortag des Beginns; ist der Zeitraum vorbei, steht sie als „Zeitraum vorbei“ beim Team, bis es entscheidet. Genehmigte, aber nicht abgeholte Anfragen verfallen: ohne Zeitraum nach 14 Tagen, mit Zeitraum an dessen Ende (Nachricht an Lehrkraft und Team). Die Tage stehen unter „Einstellungen“. Spontan geht es auch ohne Anfrage: Das Team kann direkt für jemanden ausleihen.

## Verbrauchsmaterial und Nachbestellungen

Unter „Material“ stehen Verbrauchsmaterialien wie Protokollbögen, jeweils mit Kennung (z. B. `NB-0001`), optional mit Bezug zu einem Test, Standort und Bestellhinweis (Lieferant, Artikelnummer).

- **Bestand zählen ist freiwillig:** Mit „Bestand zählen“ werden Entnahmen gebucht; wird die Mindestmenge erreicht, geht automatisch ein Nachbestellhinweis raus. Ohne Zählen genügt die Nachbestellkarte.
- **Nachbestellkarten** (Material → Nachbestellkarten) sind A6-Karten mit QR-Code, vier je A4-Blatt. Die Karte kommt in den Stapel an die Stelle, ab der nachbestellt werden soll. Wer sie erreicht, scannt sie und tippt „Nachbestellen“.
- **Hinweise** gehen an alle mit der Rolle „Sekretariat“ und zusätzlich an die Adresse unter „Einstellungen → Verbrauchsmaterial“. Fehlen beide, bekommt die Verwaltung die Hinweise, und die Einstellungen zeigen eine Warnung. Je Material gibt es höchstens einen offenen Hinweis.
- Das Sekretariat hakt unter „Material → Nachbestellungen“ ab: **bestellt**, dann **geliefert** (mit Menge, füllt den Bestand auf) oder **verwerfen**.

**Übersicht „Ausleihen“** (Verwalter): offene, überfällige und alle Vorgänge, Filter nach Lehrkraft, dazu die Liste unvollständiger Exemplare.

**Rückgabekiste:** Unter „Ausleihen → Rückgabekiste“ scannen Sie viele Exemplare nacheinander mit dem Handscanner; jedes wird sofort zurückgebucht. Mit der Kamera genügt ein Tipp zur Bestätigung. Testkoffer fragen vorher den Inhalt ab.

## Statistik

Unter „Statistik“ (Verwaltung und Administration): Ausleihen je Titel, Kategorie und Förderschwerpunkt für das aktuelle oder letzte Schuljahr, ein Halbjahr oder einen freien Zeitraum; dazu durchschnittliche Ausleihdauer, Titel, die im Zeitraum nicht ausgeliehen wurden, und was aus Anfragen wurde. Gezählt werden auch anonymisierte Ausleihen. Eine Auswertung nach Personen gibt es bewusst nicht. „Als Excel-Datei herunterladen“ liefert alle Tabellen in einer Datei.

## Erinnerungen per E-Mail

Der Dienst `scheduler` (in `docker-compose.yml` enthalten) verschickt einmal täglich ab 7 Uhr (`REMINDER_HOUR`):

- eine Erinnerung am Tag vor der Rückgabe,
- einen Hinweis, wenn die Ausleihe 3 Tage überfällig ist,
- nach 14 Tagen eine Sammelmail an alle Verwalter und Administratoren.

Jede Nachricht geht je Ausleihe nur einmal raus; nach dem Verlängern beginnt es neu. Die Tage und das Abschalten finden Sie unter „Einstellungen“. Erinnerungen zu Reservierungen und Anfragen sind oben beschrieben.

Im selben täglichen Lauf erledigt der `scheduler` auch die Datenschutz-Bereinigung und die automatische Sicherung (siehe unten). Ohne Container rufen Sie stattdessen täglich `python manage.py daily_tasks` auf (siehe [Installation ohne Container](native-install.md)); der alte Name `send_reminders` funktioniert weiter.

## Änderungsprotokoll

Jede Änderung an Titeln, Exemplaren, Stammdaten und Benutzerkonten wird mit Zeitpunkt und Person gespeichert. Über „Änderungen“ sehen Verwalter, was vorher und nachher stand, und können einen älteren Stand wiederherstellen. Auch gelöschte Stammdaten lassen sich so zurückholen. Nach einer einstellbaren Frist (Standard 1 Jahr) entfernt Fundus, **wer** geändert hat; was geändert wurde, bleibt.

## Datenschutz

Alle Einstellungen dazu stehen unter „Einstellungen → Datenschutz“. Fundus speichert keine Daten von Schülerinnen und Schülern.

**Verarbeitungsbeschreibung.** Oben auf der Einstellungsseite laden Sie eine Word-Datei für Datenschutzbeauftragte und Personalrat herunter: welche Daten, wofür, wer was sieht, Fristen, Schutzmaßnahmen. Sie folgt den aktuellen Einstellungen. Gelb markierte Stellen (z. B. Verantwortlicher, Serverstandort) ergänzt die Schule. Nach Änderung einer datenschutzrelevanten Einstellung erinnert Fundus daran, die Datei neu herunterzuladen.

**Löschfrist.** Abgeschlossene Ausleihen und Anfragen verlieren nach der eingestellten Frist (Standard 365 Tage) alle Namen: Lehrkraft, Klasse/Raum, „genehmigt von“, „übergeben von“, Nachricht und Ablehnungsgrund, auch im Änderungsprotokoll. Was wann wie lange ausgeliehen war, bleibt für die Statistik. Die Bereinigung läuft täglich; unter den Einstellungen sehen Sie, wie viele Ausleihen beim nächsten Lauf anonymisiert werden, und können sie sofort starten. Erledigte Nachbestellhinweise verlieren ihre Namen nach derselben Frist, abgelaufene Abwesenheiten werden gelöscht.

**Wer sieht, bei wem etwas ist?** Standard: nur Verwaltung und das zuständige Team. Wahlweise alle angemeldeten Lehrkräfte, damit man direkt nachfragen kann. Die Übersicht aller Ausleihen bleibt der Verwaltung vorbehalten.

**Ausleihen ohne Namen.** Solange der Personalrat noch nicht zugestimmt hat, schalten Sie „Ausleihen ohne Namen (nur Klasse oder Raum)“ ein. Dann wird beim Ausleihen statt der Person z. B. „3b“ oder „Raum 104“ eingetragen (mit Vorschlägen aus früheren Einträgen). Folgen: keine „Meine Ausleihen“, keine Erinnerungen an Lehrkräfte; Überfälliges sehen Sie in der Übersicht. Anfragen für freigabepflichtige Titel laufen weiter mit Namen und E-Mail; bei der Übergabe trägt das Team Klasse oder Raum ein, und Fundus löscht dabei Namen und Nachricht. Bestehende Ausleihen mit Namen bleiben, wie sie sind.

**Konto löschen.** Unter „Benutzer → Person → Konto löschen …“. Möglich, sobald die Person nichts mehr ausgeliehen hat. Ihre Ausleihen werden dabei sofort anonymisiert, offene Anfragen zurückgezogen, ihr Name verschwindet aus Teams und Änderungsprotokoll. Wer nur vorübergehend weg ist, wird besser deaktiviert.

**Auskunft.** Jede Person lädt unter „Konto → Meine Daten herunterladen“ alles herunter, was Fundus über sie gespeichert hat (ZIP mit CSV-Dateien).

## Anmeldung mit Schulkonto

Statt eines eigenen Passworts für Fundus können sich alle mit dem Konto anmelden, das die Schule schon hat. Fundus ordnet die Anmeldung über die **E-Mail-Adresse** einem Konto zu; Rollen und Teams vergeben Sie weiter in Fundus. Eingerichtet wird über Umgebungsvariablen in der `.env` (danach Fundus neu starten), die Regeln unter „Einstellungen → Anmeldung mit Schulkonto“:

- **Neue Konten automatisch anlegen:** Standard aus. Dann kommt nur hinein, wer schon ein Konto in Fundus hat (z. B. aus dem Lehrkräfte-Import); andere sehen „Bitte an die Verwaltung wenden“. Eingeschaltet legt Fundus neue Personen als Lehrkraft an, optional nur für bestimmte E-Mail-Domains (wichtig bei Landesdiensten, an denen viele Schulen hängen).
- **Anmeldung mit Fundus-Passwort:** für alle (Standard) oder nur für Administratoren. Administratoren behalten ihr Passwort immer als Notzugang, falls der Anmeldedienst ausfällt.

### OIDC (Microsoft Entra, Google, Keycloak und andere)

Auf der Anmeldeseite erscheint der Knopf „Mit Schulkonto anmelden“. Beim Anmeldedienst registrieren Sie Fundus als Webanwendung mit der **Weiterleitungsadresse** `https://fundus.meine-schule.de/oidc/callback/` (Ihre `SITE_URL` plus `/oidc/callback/`).

| Variable | Bedeutung |
| --- | --- |
| `OIDC_ISSUER` | Adresse des Anmeldedienstes (siehe unten); Fundus liest daraus die übrigen Adressen |
| `OIDC_CLIENT_ID` | Client- bzw. Anwendungs-ID; schaltet OIDC ein |
| `OIDC_CLIENT_SECRET` | Geheimer Schlüssel der Anwendung |
| `OIDC_BUTTON_LABEL` | Text auf dem Knopf (Standard „Mit Schulkonto anmelden“) |
| `OIDC_SCOPES` | Standard `openid email profile` |

- **Microsoft Entra ID:** App-Registrierung → Plattform „Web“ mit obiger Weiterleitungsadresse, unter „Zertifikate & Geheimnisse“ ein Geheimnis anlegen. `OIDC_ISSUER=https://login.microsoftonline.com/<Verzeichnis-ID>/v2.0`. Fehlt die E-Mail-Adresse im Token, nimmt Fundus den Anmeldenamen (UPN), sofern er wie eine E-Mail-Adresse aussieht.
- **Google Workspace:** Google Cloud Console → OAuth-Client „Webanwendung“. `OIDC_ISSUER=https://accounts.google.com`.
- **Keycloak** (auch hinter manchen Landesdiensten): Client mit „Client authentication“ an. `OIDC_ISSUER=https://keycloak.example.org/realms/<Realm>`.

Fundus holt die Adressen des Dienstes erst bei der ersten Anmeldung. Ist der Dienst nicht erreichbar, funktioniert die Anmeldung mit Passwort weiter.

### LDAP (Schulserver: paedML, IServ, UCS@school, Active Directory)

Die Anmeldung läuft über das normale Formular, mit Benutzername oder E-Mail-Adresse und dem Passwort des Schulservers. Fundus sucht die Person mit einem Dienstkonto, prüft das Passwort beim Server und liest Name und E-Mail-Adresse; das Passwort speichert Fundus nicht. Die Verbindung muss verschlüsselt sein (LDAPS oder StartTLS).

| Variable | Beispiel | Bedeutung |
| --- | --- | --- |
| `LDAP_SERVER_URI` | `ldaps://schulserver.local` | Adresse; schaltet LDAP ein |
| `LDAP_START_TLS` | `1` | Bei `ldap://` die Verbindung per StartTLS verschlüsseln |
| `LDAP_CA_FILE` | `/data/schulserver-ca.pem` | Zertifikat der Schul-CA, falls nicht öffentlich signiert |
| `LDAP_BIND_DN` / `LDAP_BIND_PASSWORD` | `cn=fundus,cn=users,dc=schule,dc=local` | Dienstkonto zum Suchen (nur Lesen) |
| `LDAP_USER_SEARCH_BASE` | `cn=users,dc=schule,dc=local` | Wo die Konten liegen |
| `LDAP_USER_FILTER` | `(sAMAccountName={user})` | Suche; Standard sucht nach `uid`, `mail`, `sAMAccountName` und `userPrincipalName` |
| `LDAP_ATTR_EMAIL` / `LDAP_ATTR_FIRST_NAME` / `LDAP_ATTR_LAST_NAME` | `mail` / `givenName` / `sn` | Attribute für E-Mail und Namen |

Ausprobieren lässt sich beides mit der Testumgebung in `deploy/dev-sso` (Keycloak und OpenLDAP).

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

legt den Export unter `/data/exporte/` im Daten-Volume ab.

### Automatische Sicherung

Der `scheduler` legt nach Zeitplan eine Sicherung an (Standard: täglich, die letzten 14 bleiben). Einstellbar unter „Einstellungen → Sicherung“; dort sehen Sie auch, wann zuletzt gesichert wurde, und bekommen eine Warnung, wenn eine Sicherung fehlgeschlagen ist oder fehlt. „Jetzt sichern“ legt sofort eine an, z. B. vor einem Update.

Eine Sicherung (`fundus-sicherung-JJJJ-MM-TT-hhmmss.zip`) enthält die komplette Datenbank (auch die Passwort-Prüfwerte, damit sich nach einer Wiederherstellung alle wieder anmelden können), die Bilder und zusätzlich den lesbaren Export. **Sie gehört deshalb in ein geschütztes Verzeichnis** und sollte zusätzlich außerhalb des Servers liegen, z. B. auf einem NAS. Ablage: `BACKUP_DIR`, im Container `/data/sicherungen`. Bis eine Sicherung gelöscht wird, enthält sie auch Namen, die in Fundus selbst schon anonymisiert sind.

Wiederherstellen siehe [Installation](installation.md#sicherung-wiederherstellen).

## Einstellungen über `.env`

| Einstellung | Standard | Bedeutung |
| --- | --- | --- |
| `SESSION_DAYS` | 30 | So lange bleiben Personen angemeldet |
| `LOGIN_MAX_ATTEMPTS` | 5 | Falsche Passwörter, bevor die Anmeldung gesperrt wird (je Gerät das Vierfache) |
| `LOGIN_LOCK_MINUTES` | 15 | Dauer der Sperre |
| `GOOGLE_BOOKS_API_KEY` | leer | Optionaler Schlüssel für Google Books als dritte ISBN-Quelle |
| `REMINDER_HOUR` | 7 | Ab dieser Stunde erledigt der `scheduler` die täglichen Aufgaben (Erinnerungen, Bereinigung, Sicherung) |
| `INVITATION_TIMEOUT_DAYS` | 14 | Gültigkeit von Einladungslinks |
| `BACKUP_DIR` | `DATA_DIR/sicherungen` | Ordner für die automatischen Sicherungen |
| `TIME_ZONE` | Europe/Berlin | Zeitzone |
| `LOG_LEVEL` | INFO | Ausführlichkeit der Protokolle |
| `OIDC_*`, `LDAP_*` | leer | Anmeldung mit Schulkonto, siehe oben |
