import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def normalize_isbn(value):
    """Entfernt Bindestriche und Leerzeichen; ein abschließendes x wird zu X."""
    return re.sub(r"[\s-]", "", value or "").upper()


def _isbn10_valid(isbn):
    if not re.fullmatch(r"\d{9}[\dX]", isbn):
        return False
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(isbn))
    return total % 11 == 0


def _isbn13_valid(isbn):
    if not re.fullmatch(r"\d{13}", isbn):
        return False
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(isbn))
    return total % 10 == 0


def validate_isbn(value):
    isbn = normalize_isbn(value)
    if not (_isbn10_valid(isbn) or _isbn13_valid(isbn)):
        raise ValidationError(
            _("„%(value)s“ ist keine gültige ISBN-10 oder ISBN-13."),
            code="invalid_isbn",
            params={"value": value},
        )
