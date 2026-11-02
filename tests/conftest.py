import pytest


@pytest.fixture(autouse=True)
def no_internet(monkeypatch):
    """Tests dürfen nie echte Anfragen ins Internet schicken."""

    def blocked(*args, **kwargs):
        raise OSError("Internetzugriff ist in Tests gesperrt")

    monkeypatch.setattr("fundus.catalog.isbn_lookup._get", blocked)


@pytest.fixture(autouse=True)
def backup_dir(settings, tmp_path):
    """Sicherungen aus Tests landen nie im echten Datenverzeichnis."""
    settings.BACKUP_DIR = tmp_path / "sicherungen"
    return settings.BACKUP_DIR
