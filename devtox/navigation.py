"""Navigazione: interpretazione della barra indirizzi e pagine interne devtox://."""

import ipaddress
import json
import re
import urllib.parse

from gi.repository import Gio, GLib

from .i18n import _
from .log import logger

INTERNAL_SCHEME = "devtox"
START_URL = "devtox://start"
WELCOME_URL = "devtox://welcome"
ABOUT_URL = "devtox://about"
SETUP_URL = "devtox://setup"

# Motori di ricerca proposti nella configurazione iniziale: nome, URL con {} per la ricerca
SEARCH_ENGINES = {
    "duckduckgo": ("DuckDuckGo", "https://duckduckgo.com/?q={}"),
    "startpage": ("Startpage", "https://www.startpage.com/do/search?query={}"),
    "brave": ("Brave Search", "https://search.brave.com/search?q={}"),
    "mojeek": ("Mojeek", "https://www.mojeek.com/search?q={}"),
    "ecosia": ("Ecosia", "https://www.ecosia.org/search?q={}"),
    "google": ("Google", "https://www.google.com/search?q={}"),
}
DEFAULT_SEARCH_ENGINE = "duckduckgo"
_search_engine = DEFAULT_SEARCH_ENGINE

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")
DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z][a-z0-9-]*[a-z0-9]$")


def set_search_engine(name):
    global _search_engine
    _search_engine = name if name in SEARCH_ENGINES else DEFAULT_SEARCH_ENGINE


def search_engine_name():
    return SEARCH_ENGINES[_search_engine][0]


def search_url(query):
    return SEARCH_ENGINES[_search_engine][1].format(urllib.parse.quote_plus(query))


def is_search_url(url):
    """True se l'URL è una ricerca del motore attuale (non un indirizzo vero)."""
    return url.startswith(SEARCH_ENGINES[_search_engine][1].split("{}")[0])


def is_one_shot(uri):
    """Pagine interne con un token monouso (salvataggio o riavvio della configurazione):
    non hanno senso dopo un riavvio, quindi non entrano nella sessione."""
    return uri.startswith(SETUP_URL + "?")


def is_local_host(host):
    """True per localhost e indirizzi IP locali/privati (server di sviluppo)."""
    host = host.lower().strip("[]")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return True
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False


def http_host(uri):
    """Host di un URL http(s), altrimenti None."""
    if not uri:
        return None
    parts = urllib.parse.urlsplit(uri)
    if parts.scheme not in ("http", "https"):
        return None
    return parts.hostname


def _is_ip(host):
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def resolve_input(text):
    """Trasforma il testo della barra indirizzi in un URL da caricare.

    Restituisce None se il testo è vuoto. Se il testo non sembra un
    indirizzo, restituisce l'URL di ricerca del motore scelto.
    """
    text = text.strip()
    if not text:
        return None
    if _SCHEME_RE.match(text) or text.lower().startswith("about:"):
        return text
    if any(ch.isspace() for ch in text):
        return search_url(text)

    try:
        parts = urllib.parse.urlsplit("//" + text)
        host = parts.hostname
        parts.port  # solleva ValueError se la porta non è valida
    except ValueError:
        return search_url(text)
    if not host:
        return search_url(text)

    if is_local_host(host):
        return "http://" + text
    if _is_ip(host) or DOMAIN_RE.match(host):
        return "https://" + text
    return search_url(text)


def display_uri(uri):
    """Testo da mostrare nella barra: vuota sulla pagina iniziale."""
    if not uri or uri == START_URL:
        return ""
    return uri


def register_internal_scheme(context, pages):
    """Registra devtox:// sul WebContext. Va fatto prima di creare i WebView.

    pages: {"nome": funzione(parametri) -> html} per devtox://nome?parametri.
    devtox://go?q=... è interna: risolve il testo come la barra indirizzi.
    """
    pages = dict(pages, go=_render_go)
    context.register_uri_scheme(
        INTERNAL_SCHEME, lambda request: _handle_internal_request(request, pages)
    )
    security = context.get_security_manager()
    # "local": le pagine web normali non possono aprire né incorporare devtox://
    security.register_uri_scheme_as_local(INTERNAL_SCHEME)
    security.register_uri_scheme_as_secure(INTERNAL_SCHEME)


def _render_go(params):
    """Pagina-ponte del campo di ricerca della pagina iniziale.

    location.replace() non lascia devtox://go nella cronologia: il tasto
    Indietro torna alla pagina iniziale invece di rimbalzare qui.
    """
    query = params.get("q", "")
    url = resolve_input(query) or START_URL
    # Solo schemi di navigazione: "javascript:" & co. diventano una ricerca
    if urllib.parse.urlsplit(url).scheme not in ("http", "https", "devtox", "about"):
        url = search_url(query)
    target = json.dumps(url).replace("<", "\\u003c")
    return f'<!doctype html><meta charset="utf-8"><script>location.replace({target});</script>'


def _handle_internal_request(request, pages):
    parts = urllib.parse.urlsplit(request.get_uri())
    render = pages.get(parts.netloc)
    if render is None:
        error = GLib.Error.new_literal(
            Gio.io_error_quark(),
            _("Pagina interna sconosciuta: {name}").format(name=parts.netloc),
            Gio.IOErrorEnum.NOT_FOUND,
        )
        request.finish_error(error)
        return

    params = dict(urllib.parse.parse_qsl(parts.query))
    try:
        data = render(params).encode("utf-8")
    except Exception as e:  # noqa: BLE001  una pagina rotta non deve lasciare la tab appesa
        logger.exception("pagina interna %s non generata", parts.netloc)
        request.finish_error(GLib.Error.new_literal(Gio.io_error_quark(), str(e), Gio.IOErrorEnum.FAILED))
        return
    stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(data))
    request.finish(stream, len(data), "text/html")
