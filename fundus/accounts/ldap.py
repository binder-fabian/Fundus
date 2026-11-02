"""Anmeldung über LDAP (paedML, IServ, UCS@school, Active Directory …).

Benutzername oder E-Mail-Adresse und Passwort werden gegen den LDAP-Server
geprüft; das Konto in Fundus wird über die E-Mail-Adresse zugeordnet (siehe
sso.match_account). Fundus speichert das LDAP-Passwort nicht.
"""

import logging
import ssl

from django.conf import settings

from fundus.accounts import sso

# ldap3 wird erst geladen, wenn LDAP eingerichtet ist.

logger = logging.getLogger(__name__)


def server():
    from ldap3 import NONE, Server, Tls

    uri = settings.LDAP_SERVER_URI
    tls = None
    if uri.startswith("ldaps://") or settings.LDAP_START_TLS:
        tls = Tls(
            validate=ssl.CERT_REQUIRED,
            ca_certs_file=settings.LDAP_CA_FILE or None,
        )
    return Server(uri, tls=tls, get_info=NONE, connect_timeout=settings.LDAP_TIMEOUT)


def connection(srv, user=None, password=None):
    """Eigene Funktion, damit Tests einen Mock-Server einsetzen können."""
    from ldap3 import Connection

    return Connection(srv, user=user, password=password, receive_timeout=settings.LDAP_TIMEOUT)


def encrypted():
    return (
        settings.LDAP_SERVER_URI.startswith("ldaps://")
        or settings.LDAP_START_TLS
        or settings.LDAP_ALLOW_UNENCRYPTED
    )


def _open(srv, user=None, password=None):
    conn = connection(srv, user, password)
    if settings.LDAP_START_TLS and not settings.LDAP_SERVER_URI.startswith("ldaps://"):
        conn.open()
        conn.start_tls()
    if not conn.bind():
        return None
    return conn


def _first(entry, attribute):
    value = entry["attributes"].get(attribute) if attribute else None
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "")


def find_user(username):
    """Sucht den Eintrag zum Benutzernamen: (DN, E-Mail, Vorname, Nachname) oder None."""
    from ldap3.utils.conv import escape_filter_chars

    srv = server()
    conn = _open(srv, settings.LDAP_BIND_DN or None, settings.LDAP_BIND_PASSWORD or None)
    if conn is None:
        logger.error("LDAP: Anmeldung des Dienstkontos %s fehlgeschlagen", settings.LDAP_BIND_DN)
        return None
    try:
        query = settings.LDAP_USER_FILTER.replace("{user}", escape_filter_chars(username))
        attributes = [
            a
            for a in (
                settings.LDAP_ATTR_EMAIL,
                settings.LDAP_ATTR_FIRST_NAME,
                settings.LDAP_ATTR_LAST_NAME,
            )
            if a
        ]
        conn.search(settings.LDAP_USER_SEARCH_BASE, query, attributes=attributes, size_limit=2)
        entries = [e for e in conn.response if e.get("type") == "searchResEntry"]
    finally:
        conn.unbind()
    if len(entries) != 1:
        return None
    entry = entries[0]
    return (
        entry["dn"],
        _first(entry, settings.LDAP_ATTR_EMAIL),
        _first(entry, settings.LDAP_ATTR_FIRST_NAME),
        _first(entry, settings.LDAP_ATTR_LAST_NAME),
    )


class LDAPBackend:
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not sso.ldap_enabled() or not username or not password:
            return None
        from ldap3.core.exceptions import LDAPException

        if not encrypted():
            logger.error("LDAP: unverschlüsselte Verbindung abgelehnt (LDAPS oder StartTLS nutzen)")
            return None
        try:
            found = find_user(username.strip())
            if found is None:
                return None
            dn, email, first_name, last_name = found
            conn = _open(server(), dn, password)
            if conn is None:
                return None
            conn.unbind()
        except LDAPException as error:
            logger.warning("LDAP-Anmeldung fehlgeschlagen: %s", error)
            return None
        return sso.match_account(request, email, first_name, last_name)

    def get_user(self, user_id):
        from fundus.accounts.models import User

        user = User.objects.filter(pk=user_id).first()
        return user if user and user.is_active else None
