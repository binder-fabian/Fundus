# Fundus

Katalog und Ausleihe für Schulen: Bücher, Diagnostiktests, Fördermaterial und Technik an einem Ort, mit QR-Codes zum Ausleihen per Handy. Selbst gehostet, ohne Cloud-Abhängigkeit, datensparsam.

> **Stand:** in Entwicklung (Phase 1 – Katalog). Noch nicht für den Einsatz geeignet.

- Anforderungen: [SPEC.md](SPEC.md)
- Umsetzungsplan und Entscheidungen: [PLAN.md](PLAN.md)

## Schnellstart mit Docker oder Podman

```bash
cp .env.example .env   # SECRET_KEY und POSTGRES_PASSWORD eintragen
docker compose up -d   # mit Podman: podman compose up -d
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

## Lizenz

[GNU Affero General Public License v3.0](LICENSE)
