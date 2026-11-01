# Installation ohne Container (Entwurf)

Fundus braucht keinen Container. Alle Einstellungen kommen aus Umgebungsvariablen, Daten liegen nur in der Datenbank und im Datenverzeichnis (`DATA_DIR`).

> Entwurf für Phase 1, noch nicht auf einem frischen System durchgetestet.

## Voraussetzungen

- Python 3.12 oder neuer und [uv](https://docs.astral.sh/uv/)
- PostgreSQL 15 oder neuer, oder SQLite (keine Installation nötig)
- Ein Reverse Proxy mit HTTPS (z. B. Caddy)

## Linux (z. B. Debian/Ubuntu)

```bash
sudo useradd --system --create-home --home-dir /opt/fundus fundus
sudo -u fundus git clone https://github.com/binder-fabian/Fundus.git /opt/fundus/app
cd /opt/fundus/app
sudo -u fundus uv sync --no-dev
sudo -u fundus cp .env.example .env    # bearbeiten, dazu DATABASE_URL und DATA_DIR setzen
sudo -u fundus uv run python manage.py migrate
sudo -u fundus uv run python manage.py collectstatic --noinput
sudo -u fundus uv run python manage.py createadmin --email ihre.adresse@meine-schule.de
```

Beispiel für `/etc/systemd/system/fundus.service`:

```ini
[Unit]
Description=Fundus
After=network.target postgresql.service

[Service]
User=fundus
WorkingDirectory=/opt/fundus/app
ExecStart=/opt/fundus/app/.venv/bin/gunicorn fundus.wsgi --bind 127.0.0.1:8000 --workers 2
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now fundus
```

## Windows

1. Python 3.12 von python.org installieren, dann in PowerShell: `pip install uv`
2. Fundus herunterladen und entpacken, z. B. nach `C:\Fundus`
3. In `C:\Fundus`:

```powershell
uv sync --no-dev
copy .env.example .env   # bearbeiten: DATABASE_URL=sqlite:///C:/Fundus/data/fundus.sqlite3, DATA_DIR=C:\Fundus\data
uv run python manage.py migrate
uv run python manage.py collectstatic --noinput
uv run python manage.py createadmin --email ihre.adresse@meine-schule.de
uv run waitress-serve --listen=127.0.0.1:8000 fundus.wsgi:application
```

Für den Dauerbetrieb den letzten Befehl als Windows-Dienst einrichten (z. B. mit NSSM) und einen Reverse Proxy mit HTTPS davorschalten.
