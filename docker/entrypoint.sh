#!/bin/sh
# Startskript im Container: Datenbank migrieren, dann den eigentlichen Befehl ausführen.
set -e

if [ "${MIGRATE_ON_START:-1}" = "1" ]; then
    python manage.py migrate --noinput
fi

exec "$@"
