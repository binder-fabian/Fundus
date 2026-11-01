"""Textnormalisierung für die Suche (ohne Modell-Importe, auch in Migrationen nutzbar)."""

TRANSLITERATION = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})

SEARCH_FIELDS = (
    "title",
    "subtitle",
    "author",
    "publisher",
    "isbn",
    "edition",
    "description",
    "contents",
)


def normalize(text):
    """Klein geschrieben, Umlaute ausgeschrieben: „Müller“ → „mueller“."""
    return (text or "").casefold().translate(TRANSLITERATION)


def title_search_text(title):
    return normalize(" ".join(v for f in SEARCH_FIELDS if (v := getattr(title, f, ""))))
