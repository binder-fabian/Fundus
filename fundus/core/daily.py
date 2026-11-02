"""Alles, was einmal täglich läuft: Erinnerungen, Anfragen, Datenschutz."""

from fundus.core import backup, privacy
from fundus.loans import reservations
from fundus.loans.reminders import send_reminders


def run_daily(today=None):
    counts = send_reminders(today)
    counts.update(reservations.daily_tasks(today))
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
        "reservierung_erinnert": "an Reservierungen erinnert",
        "reservierung_nicht_abgeholt": "Hinweise „nicht abgeholt“",
        "reservierung_verfallen": "Reservierungen verfallen",
        "ausleihen_anonymisiert": "Ausleihen anonymisiert",
        "protokoll_namen_entfernt": "Namen im Änderungsprotokoll entfernt",
        "nachbestellungen_bereinigt": "Nachbestellhinweise bereinigt",
        "abwesenheiten_geloescht": "abgelaufene Abwesenheiten gelöscht",
        "sicherung": "Sicherungen angelegt",
        "sicherung_fehlgeschlagen": "Sicherung FEHLGESCHLAGEN",
    }
    return "; ".join(f"{labels.get(k, k)}: {v}" for k, v in counts.items())
