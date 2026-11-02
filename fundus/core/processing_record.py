"""Kurzbeschreibung der Verarbeitung als Word-Datei.

Vorlage für Datenschutzbeauftragte und Personalrat, erzeugt aus den aktuellen
Einstellungen. Stellen, die die Schule selbst ergänzen muss, sind gelb markiert.
Rechtliche Angaben sind Vorschläge und von der Schule zu prüfen.
"""

import io

from django.conf import settings
from django.utils import timezone
from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.shared import Pt

from fundus.core import backup
from fundus.core.models import SchoolSettings

# Einstellungen, nach deren Änderung die Beschreibung neu erzeugt werden sollte.
RELEVANT_FIELDS = {
    "borrower_visibility",
    "anonymous_lending",
    "anonymize_after_days",
    "history_names_days",
    "backup_interval",
    "backup_keep",
    "isbn_lookup_enabled",
    "reminders_enabled",
    "reorder_email",
}


def _days(n):
    """„nach …“: 1 Jahr, 2 Jahren, 90 Tagen."""
    if n and n % 365 == 0:
        years = n // 365
        return "1 Jahr" if years == 1 else f"{years} Jahren"
    return "1 Tag" if n == 1 else f"{n} Tagen"


def _duration(n):
    """„etwa …“: 1 Jahr, 2 Jahre, 14 Tage."""
    if n and n % 365 == 0:
        years = n // 365
        return "1 Jahr" if years == 1 else f"{years} Jahre"
    return "1 Tag" if n == 1 else f"{n} Tage"


class _Writer:
    def __init__(self):
        self.doc = Document()
        style = self.doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(11)

    def heading(self, text, level=1):
        self.doc.add_heading(text, level=level)

    def para(self, *parts):
        """Absatz aus Textteilen; ein Teil als ("Text", True) wird gelb markiert."""
        p = self.doc.add_paragraph()
        for part in parts:
            text, todo = part if isinstance(part, tuple) else (part, False)
            run = p.add_run(text)
            if todo:
                run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        return p

    def bullets(self, items):
        for item in items:
            p = self.doc.add_paragraph(style="List Bullet")
            parts = item if isinstance(item, list) else [item]
            for part in parts:
                text, todo = part if isinstance(part, tuple) else (part, False)
                run = p.add_run(text)
                if todo:
                    run.font.highlight_color = WD_COLOR_INDEX.YELLOW

    def table(self, header, rows):
        table = self.doc.add_table(rows=1, cols=len(header))
        table.style = "Light Grid Accent 1"
        for cell, text in zip(table.rows[0].cells, header, strict=True):
            cell.text = text
            for run in cell.paragraphs[0].runs:
                run.bold = True
        for row in rows:
            cells = table.add_row().cells
            for cell, text in zip(cells, row, strict=True):
                cell.text = text
        self.doc.add_paragraph()

    def bytes(self):
        buffer = io.BytesIO()
        self.doc.save(buffer)
        return buffer.getvalue()


TODO = True


def processing_record_docx(config=None, now=None):
    config = config or SchoolSettings.current()
    now = timezone.localtime(now or timezone.now())
    school = config.school.name
    anonymous = config.anonymous_lending
    everyone_sees = config.borrower_visibility == config.Visibility.ALL
    w = _Writer()

    w.doc.add_heading("Kurzbeschreibung der Verarbeitung", level=0)
    w.para(f"Ausleihsystem „Fundus“ – {school}")
    w.para(
        f"Stand: {now:%d.%m.%Y}. Erzeugt von Fundus aus den aktuellen Einstellungen. "
        "Gelb markierte Stellen ergänzt die Schule. Rechtliche Angaben sind Vorschläge "
        "und von der Schule bzw. der oder dem Datenschutzbeauftragten zu prüfen."
    )

    w.heading("1. Verantwortliche Stelle und Ansprechpersonen")
    w.bullets(
        [
            ["Verantwortlich: ", (f"{school}, Anschrift, vertreten durch die Schulleitung", TODO)],
            ["Datenschutzbeauftragte/r: ", ("Name, Kontakt", TODO)],
            ["Ansprechperson für Fundus (Administration): ", ("Name, Kontakt", TODO)],
        ]
    )

    w.heading("2. Zweck der Verarbeitung")
    w.para(
        "Fundus verwaltet den Bestand der Schule an Büchern, Diagnostiktests, Fördermaterial "
        "und Technik. Lehrkräfte sehen zentral, was es gibt, wo es steht und ob es gerade "
        "verfügbar ist. Ausleihbares Material wird per QR-Code aus- und zurückgebucht; "
        "freigabepflichtiges Material (z. B. Tests) wird über eine Anfrage an das zuständige "
        "Team vergeben. Verbrauchsmaterial wird über Nachbestellhinweise an das Sekretariat "
        "nachbestellt."
    )
    w.para(
        "Eine Auswertung des Verhaltens oder der Leistung von Beschäftigten ist nicht Zweck "
        "der Verarbeitung. Fundus bietet keine Auswertungen nach Personen an; Ausleihen "
        "werden nur je Titel und Zeitraum gezählt."
    )

    w.heading("3. Rechtsgrundlage (Vorschlag, bitte prüfen)")
    w.bullets(
        [
            [
                "Art. 6 Abs. 1 lit. e DSGVO in Verbindung mit ",
                ("dem Schulgesetz und dem Datenschutzgesetz des Landes", TODO),
                " (Erfüllung der Aufgaben der Schule, Verwaltung von Lehr- und Lernmitteln).",
            ],
            [
                "Für Daten der Beschäftigten: ",
                ("Vorschrift zum Beschäftigtendatenschutz des Landes", TODO),
                ".",
            ],
            [
                "Beteiligung des Personalrats: ",
                (
                    "Mitbestimmung bei technischen Einrichtungen nach dem "
                    "Personalvertretungsgesetz des Landes; ggf. Dienstvereinbarung",
                    TODO,
                ),
                ".",
            ],
        ]
    )

    w.heading("4. Betroffene Personen und Daten")
    w.para(
        "Es werden keine Daten von Schülerinnen und Schülern verarbeitet. Betroffen sind "
        "Beschäftigte der Schule mit einem Konto in Fundus."
    )
    loans_text = (
        "Ausleihen werden ohne Namen erfasst, nur mit Klasse oder Raum (z. B. „3b“). "
        "Nur bei Anfragen für freigabepflichtiges Material wird der Name gespeichert, bis "
        "das Team das Material übergibt; dann werden Name, Nachricht und die Namen der "
        "Bearbeitenden gelöscht."
        if anonymous
        else "Je Ausleihe: Exemplar, ausleihende Person, Datum, geplantes und tatsächliches "
        "Rückgabedatum, Status; bei Anfragen zusätzlich Wunschzeitraum, Nachricht, "
        "genehmigt/übergeben von, ggf. Ablehnungsgrund."
    )
    w.table(
        ["Datenkategorie", "Inhalt"],
        [
            [
                "Konto",
                "Vorname, Nachname, dienstliche E-Mail-Adresse, Rolle, Teamzugehörigkeit, "
                "„abwesend bis“ (freiwillig, wird nach Ablauf gelöscht), Passwort nur als "
                "Prüfwert (Hash), Zeitpunkt der letzten Anmeldung.",
            ],
            ["Ausleihen und Anfragen", loans_text],
            [
                "Änderungsprotokoll",
                "Wer hat wann einen Datensatz (z. B. Titel, Exemplar, Konto) geändert und was "
                "wurde geändert.",
            ],
            ["Nachbestellungen", "Wer hat einen Nachbestellhinweis gemeldet bzw. bearbeitet."],
            [
                "Anmeldeschutz",
                "Bei fehlgeschlagenen Anmeldungen: eingegebene E-Mail-Adresse, IP-Adresse, "
                "Zeitpunkt.",
            ],
            [
                "Sitzung",
                "Ein Sitzungs-Cookie für die Anmeldung und ein Cookie gegen Formular-"
                "Missbrauch (CSRF). Keine weiteren Cookies, kein Tracking.",
            ],
        ],
    )

    w.heading("5. Wer sieht was")
    names = (
        "alle angemeldeten Lehrkräfte"
        if everyone_sees
        else "nur die Verwaltung und das für den Titel zuständige Team"
    )
    w.table(
        ["Rolle", "Zugriff"],
        [
            [
                "Administration",
                "Alles, einschließlich Einstellungen, Benutzerkonten, Import/Export und "
                "Sicherungen.",
            ],
            [
                "Verwaltung",
                "Katalog und Exemplare pflegen, alle Ausleihen einsehen und korrigieren, "
                "Änderungsprotokoll.",
            ],
            [
                "Zuständiges Team",
                "Anfragen für seine Titel genehmigen oder ablehnen, Material übergeben und "
                "zurückbuchen.",
            ],
            ["Lehrkräfte", "Katalog lesen, ausleihen, eigene Ausleihen und Anfragen sehen."],
            ["Sekretariat", "Wie Lehrkräfte; zusätzlich Nachbestellhinweise bearbeiten."],
        ],
    )
    w.para(f"Bei wem ein Exemplar gerade ausgeliehen ist, sehen {names} (Einstellung der Schule).")

    w.heading("6. Empfänger und Übermittlungen")
    items = [
        [
            "E-Mails (Einladungen, Anfragen, Erinnerungen, Nachbestellhinweise) gehen über ",
            ("den Mailserver der Schule bzw. des Schulträgers", TODO),
            ".",
        ]
    ]
    if config.isbn_lookup_enabled:
        sources = ["die Deutsche Nationalbibliothek", "Open Library (Internet Archive, USA)"]
        if settings.GOOGLE_BOOKS_API_KEY:
            sources.append("Google Books (USA)")
        sources = ", ".join(sources[:-1]) + " und " + sources[-1]
        items.append(
            f"ISBN-Abruf beim Erfassen von Büchern: Der Server sendet nur die ISBN an {sources}. "
            "Es werden keine personenbezogenen Daten übermittelt. Der Abruf ist in den "
            "Einstellungen abschaltbar."
        )
    else:
        items.append("Der ISBN-Abruf bei externen Diensten ist abgeschaltet.")
    items.append(
        "Der Browser lädt keine Inhalte von fremden Servern (keine externen Schriften, "
        "Skripte oder Statistikdienste)."
    )
    items.append("Eine Weitergabe an sonstige Dritte findet nicht statt.")
    w.bullets(items)

    w.heading("7. Speicherdauer und Löschung")
    keep_days = config.backup_keep * backup.INTERVAL_DAYS.get(config.backup_interval, 0)
    backup_text = (
        f"{config.get_backup_interval_display().capitalize()}; die letzten "
        f"{config.backup_keep} werden aufbewahrt (etwa {_duration(keep_days)}). Bis dahin "
        "enthalten sie auch Daten, die in Fundus selbst schon anonymisiert sind."
        if keep_days
        else "Automatische Sicherung ist abgeschaltet."
    )
    w.table(
        ["Daten", "Frist"],
        [
            [
                "Namen in abgeschlossenen Ausleihen und Anfragen",
                f"Werden nach {_days(config.anonymize_after_days)} automatisch entfernt "
                "(auch im Änderungsprotokoll). Titel, Exemplar und Daten bleiben für die "
                "Statistik.",
            ],
            [
                "„Wer hat geändert“ im Änderungsprotokoll",
                f"Wird nach {_days(config.history_names_days)} entfernt; was geändert wurde, "
                "bleibt.",
            ],
            [
                "Namen in erledigten Nachbestellhinweisen",
                f"Nach {_days(config.anonymize_after_days)}.",
            ],
            ["„Abwesend bis“", "Wird nach Ablauf des Datums gelöscht."],
            ["Fehlgeschlagene Anmeldungen", "Nach einem Tag."],
            [
                "Anmeldung (Sitzung)",
                f"Endet spätestens nach {_days(settings.SESSION_COOKIE_AGE // 86400)}.",
            ],
            [
                "Konten",
                "Bis zur Löschung durch die Administration (z. B. beim Verlassen der Schule). "
                "Beim Löschen werden alle Ausleihen der Person sofort anonymisiert.",
            ],
            ["Sicherungen", backup_text],
        ],
    )
    w.para(
        "Protokolle des Webservers bzw. Reverse Proxy (IP-Adressen, aufgerufene Seiten): ",
        ("Speicherdauer laut Serverkonfiguration eintragen", TODO),
        ".",
    )

    w.heading("8. Technische und organisatorische Maßnahmen")
    w.bullets(
        [
            [
                "Betrieb auf einem Server der Schule bzw. des Schulträgers; Standort: ",
                ("eintragen", TODO),
                ". Keine Cloud-Dienste erforderlich.",
            ],
            "Zugriff nur nach Anmeldung; Verbindung verschlüsselt über HTTPS.",
            "Passwörter werden nur als Prüfwert (PBKDF2-Hash) gespeichert.",
            f"Sperre nach {settings.LOGIN_MAX_ATTEMPTS} fehlgeschlagenen Anmeldungen für "
            f"{settings.LOGIN_LOCK_MINUTES} Minuten.",
            "Rollen- und Rechtekonzept (siehe Abschnitt 5); Lehrkräfte können Stammdaten nicht "
            "ändern.",
            "Änderungsprotokoll mit Wiederherstellung früherer Stände.",
            "Automatische Datenschutz-Bereinigung einmal täglich (Fristen siehe Abschnitt 7).",
            [
                "Sicherungen (Abschnitt 7) in einem geschützten Verzeichnis; zusätzliche "
                "Aufbewahrung außerhalb des Servers: ",
                ("Ort eintragen", TODO),
                ".",
            ],
            ["Aktualisierungen von Fundus und Server: ", ("Zuständigkeit eintragen", TODO), "."],
            "Quelloffene Software (AGPL-3.0); der Programmcode ist einsehbar.",
        ]
    )

    w.heading("9. Rechte der Betroffenen")
    w.bullets(
        [
            "Auskunft: Jede Person kann unter „Konto → Meine Daten herunterladen“ alle zu ihr "
            "gespeicherten Daten selbst abrufen.",
            "Berichtigung: Name und E-Mail-Adresse ändert die Administration.",
            "Löschung: Die Administration löscht das Konto; Ausleihen werden dabei anonymisiert.",
            ["Beschwerden und Fragen: ", ("Datenschutzbeauftragte/r der Schule", TODO), "."],
        ]
    )
    return w.bytes()
