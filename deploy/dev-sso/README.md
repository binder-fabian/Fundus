# Anmeldung mit Schulkonto ausprobieren (nur Entwicklung)

Startet Keycloak als OIDC-Anmeldedienst und OpenLDAP als „Schulserver“
(StartTLS mit einer eigenen Test-CA):

    deploy/dev-sso/make-certs.sh
    podman compose -f deploy/dev-sso/docker-compose.sso.yml up -d

Fundus dann lokal (nicht im Container) starten, damit Browser und Fundus
denselben Keycloak unter `localhost:8080` erreichen:

    OIDC_ISSUER=http://localhost:8080/realms/schule \
    OIDC_CLIENT_ID=fundus OIDC_CLIENT_SECRET=fundus-dev-secret \
    LDAP_SERVER_URI=ldap://localhost:3389 LDAP_START_TLS=true \
    LDAP_CA_FILE=deploy/dev-sso/certs/ca.crt \
    LDAP_BIND_DN=cn=admin,dc=schule,dc=test LDAP_BIND_PASSWORD=admin-dev \
    LDAP_USER_SEARCH_BASE=ou=people,dc=schule,dc=test \
    DEBUG=true uv run python manage.py runserver 8001

Testkonten – nur für diese Testumgebung:

| Dienst | Anmeldung | Passwort | E-Mail |
| --- | --- | --- | --- |
| Keycloak | anna | anna-dev-1234 | anna@schule.test |
| Keycloak | neu | neu-dev-1234 | neu@schule.test (ohne Konto in Fundus) |
| OpenLDAP | mmuster | max-dev-1234 | m.muster@schule.test |
| Keycloak-Verwaltung | admin | admin-dev | – |

In Fundus vorher Konten für `anna@schule.test` und `m.muster@schule.test` anlegen.
