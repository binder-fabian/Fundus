# Fundus

Katalog und Ausleihe für Schulen: Bücher, Diagnostiktests, Fördermaterial und Technik an einem Ort, mit QR-Codes zum Ausleihen per Handy. Selbst gehostet, ohne Cloud-Abhängigkeit, datensparsam.

> **Stand:** Phasen 1–6: Katalog, Suche, Benutzer, Import und Export, ISBN-Abruf, Massenerfassung, Nummernschema, Etiketten mit QR-Code, Ausleihe per Handy-Scanner, Rückgabekiste, E-Mail-Erinnerungen, Anfragen mit Übergabe-Scan, Teams, Verbrauchsmaterial mit Nachbestellkarten, Anonymisierung nach Löschfrist, Ausleihen ohne Namen, Auskunft und Löschung von Konten, automatische Sicherung, Verarbeitungsbeschreibung für Datenschutz und Personalrat, Reservierung nach Tagen und Unterrichtsstunden mit Wochenkalender, Statistik und Anmeldung mit Schulkonto (OIDC, LDAP). Für später notiert: Webhooks und Mandantenfähigkeit.

- Anforderungen: [SPEC.md](SPEC.md)
- Umsetzungsplan und Entscheidungen: [PLAN.md](PLAN.md)

## Dokumentation

- [Installation](docs/installation.md) mit Docker oder Podman, für Nicht-Experten
- [Installation ohne Container](docs/native-install.md) unter Linux und Windows (Entwurf)
- [Admin-Handbuch](docs/admin.md): Rollen, Benutzer, Katalog, Ausleihe, Reservierung, Statistik, Datenschutz, Anmeldung mit Schulkonto, Import, Export und Sicherung
- [Kurzanleitung für Lehrkräfte](docs/kurzanleitung-lehrkraefte.md) (1 Seite)
- [Funktionsumfang](docs/funktionsumfang.md): alle Funktionen und Regeln, unabhängig von der Technik beschrieben

## Schnellstart mit Docker oder Podman

```bash
cp .env.example .env   # SECRET_KEY und POSTGRES_PASSWORD eintragen
docker compose up -d   # mit Podman: podman compose up -d
```

```bash
docker compose exec app python manage.py createadmin --email ihre.adresse@schule.de
docker compose exec app python manage.py loaddemo    # optional: Beispieldaten
```

Fundus ist danach unter <http://localhost:8000> erreichbar, `/health` meldet den Zustand.
Für den Betrieb gehört ein Reverse Proxy mit HTTPS davor, siehe [deploy/Caddyfile.example](deploy/Caddyfile.example).

## Entwicklung

Voraussetzung: [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                   # Abhängigkeiten installieren
DEBUG=1 uv run python manage.py migrate   # SQLite unter ./data
DEBUG=1 uv run python manage.py runserver
uv run pytest                             # Tests (SQLite)
DATABASE_URL=postgres://… uv run pytest   # Tests gegen PostgreSQL
uv run ruff check . && uv run ruff format --check .
```

E-Mails in der Entwicklung abfangen (Postfach unter <http://localhost:8025>):

```bash
podman compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

## Lizenz

[GNU Affero General Public License v3.0](LICENSE)
