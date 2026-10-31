"""Gestore password: le password stanno nel portachiavi del sistema (libsecret), mai in file di Devtox.

Ogni voce è legata a un'origine esatta (schema, host e porta): si compila solo lì,
mai su un sottodominio o sulla versione http. Sono ammesse solo origini https, più
http su localhost e rete locale, dove girano i server di sviluppo.
Il portachiavi (GNOME Keyring, KWallet) cifra le voci e le sblocca con il login.
"""

import csv
import urllib.parse

from . import navigation

SCHEMA_NAME = "io.github.Tommaso_Palestini.devtox-browser.Password"

# Colonne dei CSV esportati dagli altri browser e gestori (in minuscolo)
_URL_COLUMNS = ("url", "login_uri", "website", "origin_url")
_USER_COLUMNS = ("username", "login_username", "user", "email", "username_value")
_PASSWORD_COLUMNS = ("password", "login_password", "password_value")


def origin_of(uri):
    """'https://github.com/login' -> 'https://github.com'; None se lì una password non va usata."""
    try:
        parts = urllib.parse.urlsplit(uri or "")
        port = parts.port
    except ValueError:
        return None
    host = parts.hostname
    if not host or parts.scheme not in ("http", "https"):
        return None
    if parts.scheme == "http" and not navigation.is_local_host(host):
        return None  # in chiaro su Internet: chiunque sulla rete la leggerebbe
    netloc = f"[{host}]" if ":" in host else host
    if port is not None and port != {"http": 80, "https": 443}[parts.scheme]:
        netloc += f":{port}"
    return f"{parts.scheme}://{netloc}"


class MemoryBackend:
    """Archivio in memoria per i test: stessa interfaccia di SecretBackend."""

    def __init__(self):
        self.items = {}

    def store(self, origin, username, password):
        self.items[(origin, username)] = password

    def lookup(self, origin, username):
        return self.items.get((origin, username))

    def search(self, origin=None):
        return [key for key in self.items if origin is None or key[0] == origin]

    def clear(self, origin, username):
        self.items.pop((origin, username), None)


class SecretBackend:
    """Il portachiavi vero, via libsecret (Secret Service: GNOME Keyring, KWallet)."""

    def __init__(self):
        import gi
        gi.require_version("Secret", "1")
        from gi.repository import Secret
        self.Secret = Secret
        self.schema = Secret.Schema.new(
            SCHEMA_NAME, Secret.SchemaFlags.NONE,
            {"origin": Secret.SchemaAttributeType.STRING, "username": Secret.SchemaAttributeType.STRING},
        )

    def store(self, origin, username, password):
        host = urllib.parse.urlsplit(origin).hostname or origin
        label = f"Devtox: {username} @ {host}" if username else f"Devtox: {host}"
        self.Secret.password_store_sync(self.schema, {"origin": origin, "username": username},
                                        self.Secret.COLLECTION_DEFAULT, label, password, None)

    def lookup(self, origin, username):
        return self.Secret.password_lookup_sync(self.schema, {"origin": origin, "username": username}, None)

    def search(self, origin=None):
        attributes = {"origin": origin} if origin else {}
        flags = self.Secret.SearchFlags.ALL | self.Secret.SearchFlags.UNLOCK
        items = self.Secret.password_search_sync(self.schema, attributes, flags, None)
        found = []
        for item in items:
            attrs = item.get_attributes()
            if "origin" in attrs:
                found.append((attrs["origin"], attrs.get("username", "")))
        return found

    def clear(self, origin, username):
        self.Secret.password_clear_sync(self.schema, {"origin": origin, "username": username}, None)


def available():
    """True se il portachiavi del sistema risponde (Secret Service su D-Bus)."""
    try:
        import gi
        gi.require_version("Secret", "1")
        from gi.repository import Secret
        return Secret.Service.get_sync(Secret.ServiceFlags.NONE, None) is not None
    except (ImportError, ValueError, Exception):  # noqa: BLE001  niente portachiavi: niente password
        return False


class Vault:
    def __init__(self, backend):
        self.backend = backend

    def usernames(self, origin):
        return sorted({user for found_origin, user in self.backend.search(origin) if found_origin == origin})

    def password(self, origin, username):
        return self.backend.lookup(origin, username)

    def save(self, origin, username, password):
        """'new', 'updated' o 'same' (niente da fare)."""
        current = self.backend.lookup(origin, username)
        if current == password:
            return "same"
        self.backend.store(origin, username, password)
        return "new" if current is None else "updated"

    def delete(self, origin, username):
        self.backend.clear(origin, username)

    def entries(self):
        return sorted(set(self.backend.search()))


def _pick(row, names):
    for name in names:
        value = row.get(name)
        if value:
            return value
    return ""


def read_csv(path):
    """([(origin, utente, password)], scartate) da un CSV di Chrome, Opera, Brave, Edge, Firefox o Bitwarden.

    Si scartano le voci senza password, le app (android://) e i siti in http su Internet.
    ValueError se il file non ha colonne di URL e password.
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        columns = {(name or "").strip().lower() for name in reader.fieldnames or []}
        if not columns & set(_URL_COLUMNS) or not columns & set(_PASSWORD_COLUMNS):
            raise ValueError("not a password export")
        rows, skipped = [], 0
        for raw in reader:
            row = {(k or "").strip().lower(): (v or "") for k, v in raw.items()}
            origin = origin_of(_pick(row, _URL_COLUMNS).strip())
            password = _pick(row, _PASSWORD_COLUMNS)
            if row.get("type") and row["type"] != "login":  # Bitwarden: note, carte, identità
                continue
            if origin is None or not password:
                skipped += 1
                continue
            rows.append((origin, _pick(row, _USER_COLUMNS).strip(), password))
    return rows, skipped
