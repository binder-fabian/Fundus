"""Buchdaten zu einer ISBN aus dem Internet abrufen.

Quellen in dieser Reihenfolge: Deutsche Nationalbibliothek (SRU, MARC21),
Open Library, Google Books (nur mit API-Schlüssel). Für jedes Feld gewinnt
die erste Quelle, die einen Wert liefert. Alle Abrufe laufen auf dem Server;
übermittelt wird nur die ISBN. Ergebnisse werden 30 Tage zwischengespeichert.
"""

import datetime
import json
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from defusedxml import ElementTree
from django.conf import settings
from django.utils import timezone

from fundus.catalog.isbn import normalize_isbn

logger = logging.getLogger(__name__)

TIMEOUT = 6
CACHE_DAYS = 30
FIELDS = ("title", "subtitle", "author", "publisher", "edition", "year")
MARC = "{http://www.loc.gov/MARC21/slim}"
# DNB markiert Artikel, die beim Sortieren übergangen werden, mit Steuerzeichen.
NON_SORTING = re.compile("[\u0098\u009c]")


@dataclass
class LookupResult:
    isbn: str
    data: dict = field(default_factory=dict)
    sources: list = field(default_factory=list)
    cover_url: str = ""
    failed: list = field(default_factory=list)

    @property
    def found(self):
        return bool(self.data.get("title"))

    def as_dict(self):
        return {
            "data": self.data,
            "sources": self.sources,
            "cover_url": self.cover_url,
        }


def _get(url, accept="application/json"):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": f"Fundus/1.0 (+{settings.SITE_URL})", "Accept": accept},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
        return response.read()


def _clean(text):
    text = NON_SORTING.sub("", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip(" /:;,=").strip()


# Deutsche Nationalbibliothek


def parse_dnb(xml_bytes):
    root = ElementTree.fromstring(xml_bytes)
    record = root.find(f".//{MARC}record")
    if record is None:
        return {}

    def subfields(tag):
        for datafield in record.findall(f"{MARC}datafield[@tag='{tag}']"):
            yield {sf.get("code"): sf.text or "" for sf in datafield.findall(f"{MARC}subfield")}

    def first(tag, code):
        for sf in subfields(tag):
            if sf.get(code):
                return _clean(sf[code])
        return ""

    data = {
        "title": first("245", "a"),
        "subtitle": first("245", "b"),
        "edition": first("250", "a"),
        "publisher": first("264", "b") or first("260", "b"),
        "year": re.sub(r"\D", "", first("264", "c") or first("260", "c"))[:4],
    }
    authors = [_clean(sf["a"]) for sf in subfields("100") if sf.get("a")]
    contributors = [sf for sf in subfields("700") if sf.get("a") and not sf.get("t")]
    authors += [_clean(sf["a"]) for sf in contributors if sf.get("4") == "aut"]
    if not authors:
        editors = [_clean(sf["a"]) for sf in contributors if sf.get("4") == "edt"]
        if editors:
            authors = [f"{', '.join(editors)} (Hrsg.)"]
    data["author"] = "; ".join(authors)
    return {k: v for k, v in data.items() if v}


def fetch_dnb(isbn):
    query = urllib.parse.urlencode(
        {
            "version": "1.1",
            "operation": "searchRetrieve",
            "query": f"isbn={isbn}",
            "recordSchema": "MARC21-xml",
            "maximumRecords": "1",
        }
    )
    return parse_dnb(_get(f"https://services.dnb.de/sru/dnb?{query}", "application/xml")), ""


# Open Library


def parse_openlibrary(payload, isbn):
    book = json.loads(payload).get(f"ISBN:{isbn}")
    if not book:
        return {}, ""
    data = {
        "title": book.get("title", ""),
        "subtitle": book.get("subtitle", ""),
        "author": "; ".join(a.get("name", "") for a in book.get("authors", [])),
        "publisher": ", ".join(p.get("name", "") for p in book.get("publishers", [])),
        "year": (re.search(r"\d{4}", book.get("publish_date", "")) or [""])[0],
    }
    cover = ""
    if book.get("cover"):
        cover = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg?default=false"
    return {k: _clean(v) for k, v in data.items() if v}, cover


def fetch_openlibrary(isbn):
    query = urllib.parse.urlencode({"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"})
    return parse_openlibrary(_get(f"https://openlibrary.org/api/books?{query}"), isbn)


# Google Books (nur mit Schlüssel – ohne Schlüssel ist das Kontingent erschöpft)


def parse_google(payload):
    items = json.loads(payload).get("items") or []
    if not items:
        return {}
    info = items[0].get("volumeInfo", {})
    data = {
        "title": info.get("title", ""),
        "subtitle": info.get("subtitle", ""),
        "author": "; ".join(info.get("authors", [])),
        "publisher": info.get("publisher", ""),
        "year": info.get("publishedDate", "")[:4],
    }
    return {k: _clean(v) for k, v in data.items() if v}


def fetch_google(isbn):
    key = settings.GOOGLE_BOOKS_API_KEY
    query = urllib.parse.urlencode({"q": f"isbn:{isbn}", "key": key})
    return parse_google(_get(f"https://www.googleapis.com/books/v1/volumes?{query}")), ""


def sources():
    result = [("DNB", fetch_dnb), ("Open Library", fetch_openlibrary)]
    if settings.GOOGLE_BOOKS_API_KEY:
        result.append(("Google Books", fetch_google))
    return result


def lookup(isbn, use_cache=True):
    """Fragt alle Quellen ab und führt die Ergebnisse zusammen."""
    from fundus.catalog.models import IsbnLookupCache

    isbn = normalize_isbn(isbn)
    if use_cache:
        cached = IsbnLookupCache.objects.filter(
            isbn=isbn, fetched_at__gte=timezone.now() - datetime.timedelta(days=CACHE_DAYS)
        ).first()
        if cached:
            return LookupResult(isbn, **cached.result)

    result = LookupResult(isbn)
    for name, fetch in sources():
        try:
            data, cover = fetch(isbn)
        except Exception:  # Netzwerk, Zeitüberschreitung, kaputte Antwort
            logger.warning("ISBN-Abruf bei %s für %s fehlgeschlagen", name, isbn, exc_info=True)
            result.failed.append(name)
            continue
        if data:
            result.sources.append(name)
            for key in FIELDS:
                if data.get(key) and not result.data.get(key):
                    result.data[key] = data[key]
        if cover and not result.cover_url:
            result.cover_url = cover

    # Nur speichern, wenn keine Quelle ausgefallen ist – sonst später neu versuchen.
    if not result.failed:
        IsbnLookupCache.objects.update_or_create(
            isbn=isbn, defaults={"result": result.as_dict(), "fetched_at": timezone.now()}
        )
    return result


def download_cover(url):
    """Lädt ein Cover von Open Library; None, wenn es keins gibt."""
    if not url.startswith("https://covers.openlibrary.org/"):
        return None
    try:
        data = _get(url, "image/*")
    except Exception:
        logger.info("Kein Cover unter %s", url)
        return None
    return data if len(data) > 1000 else None
