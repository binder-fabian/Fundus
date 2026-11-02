"""Alles, was einmal täglich läuft: Erinnerungen, Anfragen, Datenschutz."""

from fundus.core import backup, privacy
from fundus.loans.reminders import send_reminders


def run_daily(today=None):
    counts = send_reminders(today)
    counts.update(privacy.run())
    # Zuletzt, damit die Sicherung schon bereinigt ist.
    counts.update(backup.run())
    return counts


def describe(counts):
    labels = {
        "vorher": "Erinnerungen vor Ablauf",
        "ueberfaellig": "Überfällig-Hinweise",
        "verwaltung": "an die Verwaltung gemeldet",
        "anfrage_erinnert": "Anfragen beim Team angemahnt",
        "verfallen": "Genehmigungen verfallen",
        "ausleihen_anonymisiert": "Ausleihen anonymisiert",
        "protokoll_namen_entfernt": "Namen im Änderungsprotokoll entfernt",
        "nachbestellungen_bereinigt": "Nachbestellhinweise bereinigt",
        "abwesenheiten_geloescht": "abgelaufene Abwesenheiten gelöscht",
        "sicherung": "Sicherungen angelegt",
        "sicherung_fehlgeschlagen": "Sicherung FEHLGESCHLAGEN",
    }
    return "; ".join(f"{labels.get(k, k)}: {v}" for k, v in counts.items())
