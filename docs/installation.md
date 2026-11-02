# Fundus installieren

Diese Anleitung richtet sich an Personen ohne IT-Ausbildung. Sie brauchen einen kleinen Server oder Mini-PC im Schulnetz (2 GB Arbeitsspeicher genügen) mit **Docker** oder **Podman**.

> Fundus wird als fertiges Container-Image bereitgestellt (`ghcr.io/binder-fabian/fundus`, für Intel/AMD und ARM). Solange das Projekt noch nicht veröffentlicht ist, ist das Image privat; bauen Sie es dann selbst (siehe Schritt 3).

## 1. Dateien auf den Server holen

```bash
git clone https://github.com/binder-fabian/Fundus.git fundus
cd fundus
```

## 2. Einstellungen anlegen

```bash
cp .env.example .env
```

Öffnen Sie `.env` mit einem Texteditor und tragen Sie mindestens ein:

| Einstellung | Bedeutung |
| --- | --- |
| `SECRET_KEY` | Langer Zufallswert. Erzeugen mit `python3 -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `POSTGRES_PASSWORD` | Passwort für die Datenbank (wird nur intern benutzt) |
| `ALLOWED_HOSTS` | Adresse von Fundus ohne `https://`, z. B. `fundus.meine-schule.de` |
| `CSRF_TRUSTED_ORIGINS` | Dieselbe Adresse mit `https://` |
| `SITE_URL` | Dieselbe Adresse mit `https://`, für Links in E-Mails |
| `EMAIL_URL` | Zugang zum Mailserver, z. B. `smtp+tls://benutzer:passwort@smtp.meine-schule.de:587` |
| `DEFAULT_FROM_EMAIL` | Absenderadresse, z. B. `fundus@meine-schule.de` |

## 3. Starten

```bash
docker compose up -d
```

Mit Podman: `podman compose up -d`. Für kleine Schulen ohne eigene Datenbank gibt es eine Variante mit SQLite: `docker compose -f docker-compose.sqlite.yml up -d`.

Das Image selbst bauen statt herunterladen (z. B. solange es noch privat ist):

```bash
docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build
```

Prüfen, ob alles läuft:

```bash
docker compose ps
```

`app` und `db` sollten `healthy` zeigen, `scheduler` (verschickt die täglichen Erinnerungen) `running`. Fundus lauscht auf Port 8000.

## 4. Ersten Administrator anlegen

```bash
docker compose exec app python manage.py createadmin --email ihre.adresse@meine-schule.de --first-name Vorname --last-name Nachname
```

Sie werden nach einem Passwort gefragt. Alternativ mit `--invite`: Dann bekommen Sie einen Einladungslink per E-Mail (und auf dem Bildschirm).

**Empfehlung:** Legen Sie danach in Fundus unter „Benutzer“ einen zweiten Administrator an, damit Fundus auch bei Abwesenheit verwaltet werden kann.

## 5. HTTPS einrichten

Für die Anmeldung und für den Kamera-Scanner auf dem Handy braucht Fundus **HTTPS** – ohne HTTPS verweigern die Browser den Zugriff auf die Kamera. Am einfachsten geht das mit [Caddy](https://caddyserver.com/), das Zertifikate automatisch besorgt. Eine Beispielkonfiguration liegt in [`deploy/Caddyfile.example`](../deploy/Caddyfile.example). Setzen Sie danach in `.env`: `BEHIND_HTTPS_PROXY=1`.

Ohne öffentliche Domain (nur im Schulnetz) kann Caddy ein eigenes Zertifikat ausstellen (`tls internal`); die Geräte müssen diesem dann einmal vertrauen.

## Ausprobieren mit Beispieldaten

```bash
docker compose exec app python manage.py loaddemo
```

Legt erfundene Titel mit Inventarnummern `DEMO-…` an.

## Aktualisieren

```bash
git pull
docker compose pull
docker compose up -d
```

Beim selbst gebauten Image stattdessen `docker compose -f docker-compose.yml -f docker-compose.build.yml up -d --build`.

Datenbankänderungen werden beim Start automatisch übernommen. Machen Sie vorher einen Export (siehe [Admin-Handbuch](admin.md)).

## Wo liegen die Daten?

Nur in zwei benannten Volumes: `fundus_fundus-db` (Datenbank) und `fundus_fundus-data` (Bilder, Exporte, bei SQLite auch die Datenbank). Alles andere lässt sich jederzeit neu bauen.
