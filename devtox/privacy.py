"""Privacy: profilo, header (estensione C), cookie, blocklist, HTTPS e permessi."""

import html
import json
import os
import re
import secrets
import urllib.parse

from gi.repository import Gio, GLib, WebKit2

from . import navigation, utils, webext
from .i18n import _
from .log import logger

_CACHE_MODELS = {
    "web_browser": WebKit2.CacheModel.WEB_BROWSER,
    "document_browser": WebKit2.CacheModel.DOCUMENT_BROWSER,
    "document_viewer": WebKit2.CacheModel.DOCUMENT_VIEWER,
}

# Gira prima degli script della pagina, in tutti i frame
_GPC_SCRIPT = (
    "Object.defineProperty(Navigator.prototype, 'globalPrivacyControl',"
    " {get: () => true, configurable: true});"
)

# URL http che non vanno mai forzati in HTTPS (le regole WebKit non supportano "|")
_LOCAL_HTTP_PATTERNS = [
    r"^http://localhost[:/]",
    r"^http://[^/]*\.localhost[:/]",
    r"^http://[^/]*\.local[:/]",
    r"^http://127\.",
    r"^http://\[::1\]",
    r"^http://10\.",
    r"^http://192\.168\.",
    r"^http://172\.1[6-9]\.",
    r"^http://172\.2[0-9]\.",
    r"^http://172\.3[01]\.",
]

DEFAULT_BLOCKLIST_HEADER = _("""\
# Blocklist locale di Devtox: un dominio per riga.
# Vengono bloccati anche tutti i sottodomini. Le righe con # sono commenti.
# Nessuna lista viene scaricata: questo file lo gestisci solo tu.
# Dopo una modifica: menu > Ricarica blocklist.
""")
DEFAULT_BLOCKLIST_DOMAINS = """\
doubleclick.net
google-analytics.com
googletagmanager.com
googleadservices.com
googlesyndication.com
connect.facebook.net
hotjar.com
scorecardresearch.com
quantserve.com
criteo.com
taboola.com
outbrain.com
"""


# --- Profilo -------------------------------------------------------------


def create_web_context(config, private=False):
    """WebContext con profilo dedicato e regole privacy dalla configurazione.

    private=True: profilo usa-e-getta per le tab private, niente su disco.
    """
    if config["persistent_data"] and not private:
        manager = WebKit2.WebsiteDataManager(
            base_data_directory=utils.data_dir(),
            base_cache_directory=utils.cache_dir(),
        )
    else:
        manager = WebKit2.WebsiteDataManager.new_ephemeral()
    manager.set_itp_enabled(True)  # Intelligent Tracking Prevention
    manager.set_tls_errors_policy(WebKit2.TLSErrorsPolicy.FAIL)

    properties = {"website_data_manager": manager}
    limit = config["web_process_memory_limit_mb"]
    if limit > 0:
        pressure = WebKit2.MemoryPressureSettings.new()
        pressure.set_memory_limit(limit)
        properties["memory_pressure_settings"] = pressure
    context = WebKit2.WebContext(**properties)

    if config["disk_cache"]:
        context.set_cache_model(
            _CACHE_MODELS.get(config["cache_model"], WebKit2.CacheModel.DOCUMENT_BROWSER)
        )
    else:
        # DOCUMENT_VIEWER azzera la cache; quella vecchia su disco viene cancellata
        context.set_cache_model(WebKit2.CacheModel.DOCUMENT_VIEWER)
        manager.clear(WebKit2.WebsiteDataTypes.DISK_CACHE, 0, None, None)

    cookie_policy = (
        WebKit2.CookieAcceptPolicy.NO_THIRD_PARTY
        if config["block_third_party_cookies"]
        else WebKit2.CookieAcceptPolicy.ALWAYS
    )
    context.get_cookie_manager().set_accept_policy(cookie_policy)

    _load_web_extension(context, config)
    return context


def _load_web_extension(context, config):
    """Sec-GPC e Referer si possono toccare solo dentro il web process."""
    if not (config["send_gpc"] or config["trim_referer"]):
        return
    directory = webext.ensure_built()
    if directory is None:
        return
    context.set_web_extensions_directory(directory)
    context.set_web_extensions_initialization_user_data(
        GLib.Variant("(bb)", (config["send_gpc"], config["trim_referer"]))
    )


def create_content_manager():
    """UserContentManager condiviso da tutte le tab (script e filtri)."""
    return WebKit2.UserContentManager()


class ContentScripts:
    """Script iniettati nelle pagine: GPC, anti-fingerprinting, visualizzatore JSON.

    Vivono nello UserContentManager condiviso da tutte le tab; rebuild() li
    rigenera quando cambiano le impostazioni per sito.
    """

    def __init__(self, config, content_manager):
        self.config = config
        self.content_manager = content_manager
        # Nuovo a ogni avvio: l'impronta "sporcata" cambia da una sessione all'altra
        self.seed = secrets.token_hex(16)

    def rebuild(self):
        manager = self.content_manager
        manager.remove_all_scripts()
        if self.config["send_gpc"]:
            manager.add_script(_page_script(_GPC_SCRIPT))
        if self.config["fingerprint_protection"]:
            source = utils.render_template(
                "fingerprint.js",
                seed=self.seed,
                off_hosts=json.dumps(self.config["fingerprint_off_hosts"]),
            )
            manager.add_script(_page_script(source))
        # Il visualizzatore JSON gira in un mondo isolato: la pagina non lo vede
        manager.add_script(
            WebKit2.UserScript.new_for_world(
                utils.read_resource("json_viewer.js"),
                WebKit2.UserContentInjectedFrames.TOP_FRAME,
                WebKit2.UserScriptInjectionTime.END,
                "devtox-json",
                None,
                None,
            )
        )


def _page_script(source):
    """Script nel mondo della pagina, prima dei suoi script, in tutti i frame."""
    return WebKit2.UserScript(
        source,
        WebKit2.UserContentInjectedFrames.ALL_FRAMES,
        WebKit2.UserScriptInjectionTime.START,
        None,
        None,
    )


def create_settings():
    """Impostazioni di un WebView (una copia per tab: il JS si spegne per sito)."""
    settings = WebKit2.Settings()
    settings.set_enable_developer_extras(True)
    settings.set_enable_webrtc(False)  # WebRTC può rivelare l'IP locale
    settings.set_enable_media_stream(False)
    settings.set_enable_page_cache(False)  # niente pagine "congelate" in RAM
    return settings


def create_website_policies():
    # Niente autoplay di audio/video: meno CPU e meno sorprese
    return WebKit2.WebsitePolicies(autoplay=WebKit2.AutoplayPolicy.DENY)


def deny_permission_request(_webview, request):
    """Geolocalizzazione, notifiche, microfono, ...: sempre negati."""
    request.deny()
    return True


# --- Blocklist e HTTPS ---------------------------------------------------


def blocklist_path():
    return os.path.join(utils.config_dir(), "blocklist.txt")


def load_blocklist(path):
    """Legge i domini dalla blocklist; la crea con qualche esempio se manca."""
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_BLOCKLIST_HEADER + DEFAULT_BLOCKLIST_DOMAINS)

    domains = []
    with open(path, encoding="utf-8") as f:
        for number, line in enumerate(f, 1):
            domain = line.split("#", 1)[0].strip().lower().lstrip("*.")
            if not domain:
                continue
            if navigation.DOMAIN_RE.match(domain):
                domains.append(domain)
            else:
                logger.warning("blocklist: riga %d ignorata: %r", number, line.strip())
    return sorted(set(domains))


_IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def _rule_host_ok(host):
    """Host utilizzabili in una regola: domini o IPv4 (solo lettere, cifre, "-" e ".")."""
    return host == "localhost" or bool(host) and bool(navigation.DOMAIN_RE.match(host) or _IPV4_RE.match(host))


def _host_pattern(prefix, host):
    return prefix + r"([^/]*\.)?" + host.replace(".", r"\.") + "[:/]"


def build_rules(blocked_domains, https_only, https_exceptions, shields_down_hosts=()):
    """Regole in formato WebKit content blocker (stesso formato di Safari).

    L'ordine conta: "ignore-previous-rules" annulla solo le regole precedenti.
    """
    rules = []
    # Prima l'HTTPS: le sue eccezioni usano "ignore-previous-rules", che annullerebbe
    # anche i blocchi se questi venissero prima
    if https_only:
        rules.append({"trigger": {"url-filter": "^http://"}, "action": {"type": "make-https"}})
        exceptions = [h for h in https_exceptions if _rule_host_ok(h)]
        patterns = _LOCAL_HTTP_PATTERNS + [_host_pattern("^http://", h) for h in exceptions]
        for pattern in patterns:
            rules.append({"trigger": {"url-filter": pattern}, "action": {"type": "ignore-previous-rules"}})

    # Scudi abbassati: i blocchi non valgono sulle pagine di questi siti (l'HTTPS sì)
    down = ["*" + h for h in shields_down_hosts if _rule_host_ok(h)]

    def blocking(trigger):
        if down:
            trigger["unless-domain"] = down
        return {"trigger": trigger, "action": {"type": "block"}}

    for domain in blocked_domains:
        rules.append(blocking({"url-filter": _host_pattern("^[a-z][a-z0-9.+-]*://", domain)}))
    # <a ping="..."> e navigator.sendBeacon dei link: tracciamento puro
    rules.append(blocking({"url-filter": ".*", "resource-type": ["ping"]}))
    return rules


class ContentFilter:
    """Compila blocklist e regole HTTPS e le applica a tutte le tab."""

    def __init__(self, config, content_manager):
        self.config = config
        self.content_manager = content_manager
        self.store = WebKit2.UserContentFilterStore.new(os.path.join(utils.cache_dir(), "filters"))
        self.blocked_domains = []
        # Eccezioni HTTP accettate nelle tab private: valgono fino alla chiusura, mai su disco
        self.session_https_exceptions = set()

    def reload(self, on_done=None):
        """Ricompila in modo asincrono; on_done() viene chiamato comunque."""
        self.blocked_domains = load_blocklist(blocklist_path())
        rules = build_rules(
            self.blocked_domains,
            self.config["https_only"],
            sorted(set(self.config["https_exceptions"]) | self.session_https_exceptions),
            self.config["shields_down_hosts"],
        )
        source = GLib.Bytes.new(json.dumps(rules).encode())
        self.store.save("devtox", source, None, self._on_saved, on_done)

    def _on_saved(self, store, result, on_done):
        try:
            content_filter = store.save_finish(result)
        except GLib.Error as e:
            logger.error("regole non compilate, filtri NON attivi: %s", e.message)
        else:
            self.content_manager.remove_all_filters()
            self.content_manager.add_filter(content_filter)
        if on_done is not None:
            on_done()


class HttpsGuard:
    """Se un sito forzato in HTTPS non risponde, propone l'HTTP solo su richiesta."""

    def __init__(self, config, content_filter, is_private):
        self.config = config
        self.content_filter = content_filter
        self._is_private = is_private  # is_private(webview): le tab private non scrivono su disco
        self._upgraded_hosts = set()  # host richiesti in http e portati in https
        # (WebView, URL http) proposti nella pagina d'errore -> host. Il consenso vale solo
        # nella stessa tab e con un gesto dell'utente: una pagina che naviga da sola
        # a quell'URL (anche da un'altra tab) non abbassa la protezione
        self._offered = {}

    def on_decide_policy(self, webview, decision, decision_type):
        if decision_type != WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            return False
        uri = decision.get_navigation_action().get_request().get_uri()

        action = decision.get_navigation_action()
        host = self._offered.get((webview, uri))
        if host is not None and action.is_user_gesture():
            del self._offered[(webview, uri)]
            # L'utente ha cliccato "continua in HTTP" nella nostra pagina d'errore
            decision.ignore()
            if self._is_private(webview):
                self.content_filter.session_https_exceptions.add(host)
            else:
                exceptions = sorted(set(self.config["https_exceptions"]) | {host})
                self.config.set("https_exceptions", exceptions)
            self.content_filter.reload(on_done=lambda: webview.load_uri(uri))
            return True

        if self.config["https_only"] and uri.startswith("http://"):
            host = navigation.http_host(uri)
            if host and not navigation.is_local_host(host):
                if len(self._upgraded_hosts) > 1000:
                    self._upgraded_hosts.clear()
                self._upgraded_hosts.add(host)
        return False

    def on_load_failed(self, webview, _event, failing_uri, error):
        # Blocklist (WebKitPolicyError) e annullamenti non sono problemi di HTTPS
        if error.domain == "WebKitPolicyError":
            return False
        if error.matches(WebKit2.NetworkError.quark(), WebKit2.NetworkError.CANCELLED) or \
                error.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
            return False
        return self._offer_http(webview, failing_uri, error.message)

    def on_tls_error(self, webview, failing_uri, _certificate, _errors):
        return self._offer_http(webview, failing_uri, _("certificato TLS non valido"))

    def _offer_http(self, webview, failing_uri, reason):
        parts = urllib.parse.urlsplit(failing_uri)
        host = parts.hostname
        if parts.scheme != "https" or host not in self._upgraded_hosts or not _rule_host_ok(host):
            return False
        http_uri = urllib.parse.urlunsplit(("http",) + tuple(parts[1:]))
        if len(self._offered) > 100:
            self._offered.clear()
        self._offered[(webview, http_uri)] = host
        page = utils.render_template(
            "https_error.html",
            host=html.escape(host),
            note=html.escape(
                _("Tab privata: l'eccezione vale solo fino alla chiusura del browser.")
                if self._is_private(webview)
                else _("L'eccezione resta salvata in config.json, alla voce https_exceptions.")
            ),
            reason=html.escape(reason),
            http_uri=html.escape(http_uri, quote=True),
        )
        webview.load_alternate_html(page, failing_uri, None)
        return True
