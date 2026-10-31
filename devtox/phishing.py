"""Protezione anti-phishing con una lista pubblica tenuta sul PC.

La lista è Phishing.Database (licenza MIT): una volta a settimana quella completa,
compressa e solo se è cambiata (ETag); ogni giorno i soli domini nuovi della giornata.
Nessun dato tuo esce: si scarica la lista, il controllo avviene qui.
In memoria c'è un indice di hash da 8 byte ordinati (circa 3 MB per 400.000 domini):
una ricerca è una bisezione, niente insiemi di stringhe da decine di MB.
"""

import array
import html
import bisect
import gzip
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import navigation
from .log import logger

_BASE = "https://raw.githubusercontent.com/mitchellkrogza/Phishing.Database/master/"
FULL_URL = _BASE + "phishing-domains-ACTIVE.txt"
NEW_URL = _BASE + "phishing-domains-NEW-today.txt"
SOURCE_NAME = "Phishing.Database"
SOURCE_PAGE = "https://github.com/mitchellkrogza/Phishing.Database"
FULL_EVERY = 7 * 86400
NEW_EVERY = 86400
TIMEOUT = 30
TOKEN = secrets.token_urlsafe(18)  # "continua comunque" passa da devtox://blocked con questo token
BLOCKED_URL = "devtox://blocked"


# Piattaforme condivise: la lista a volte segnala la piattaforma intera (sites.google.com,
# dweb.link) per colpa di una pagina. Bloccarle fermerebbe migliaia di siti legittimi, e
# per un dev anche i propri deploy: si bloccano solo i sottodomini segnalati (x.vercel.app)
SHARED_HOSTS = frozenset("""
sites.google.com docs.google.com drive.google.com forms.gle storage.googleapis.com
github.com github.io githubusercontent.com gitlab.io gitlab.com bitbucket.io codeberg.page
vercel.app netlify.app pages.dev workers.dev web.app firebaseapp.com herokuapp.com onrender.com
fly.dev railway.app azurewebsites.net azurestaticapps.net cloudfront.net amazonaws.com
s3.amazonaws.com blogspot.com wordpress.com wixsite.com weebly.com glitch.me ngrok.io
ngrok-free.app trycloudflare.com duckdns.org replit.app repl.co codesandbox.io stackblitz.io
ipfs.io dweb.link notion.site webflow.io framer.website myshopify.com typeform.com
""".split())


def _hash(domain):
    return int.from_bytes(hashlib.blake2b(domain.encode(), digest_size=8).digest(), "big")


def parse_domains(text):
    """Domini validi della lista, in minuscolo; commenti e righe rotte scartati."""
    found = []
    for line in text.splitlines():
        domain = line.split("#", 1)[0].strip().lower().rstrip(".")
        if domain and domain not in SHARED_HOSTS and navigation.DOMAIN_RE.match(domain):
            found.append(domain)
    return found


class Index:
    """Hash ordinati dei domini segnalati."""

    def __init__(self, hashes=None):
        self.hashes = hashes if hashes is not None else array.array("Q")

    @classmethod
    def build(cls, domains):
        return cls(array.array("Q", sorted({_hash(d) for d in domains})))

    @classmethod
    def load(cls, path):
        hashes = array.array("Q")
        try:
            with open(path, "rb") as f:
                hashes.frombytes(f.read())
        except (OSError, ValueError):
            pass
        return cls(hashes)

    def save(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            self.hashes.tofile(f)
        os.replace(tmp, path)

    def merge(self, domains):
        return Index(array.array("Q", sorted(set(self.hashes) | {_hash(d) for d in domains})))

    def __len__(self):
        return len(self.hashes)

    def _has(self, domain):
        value = _hash(domain)
        i = bisect.bisect_left(self.hashes, value)
        return i < len(self.hashes) and self.hashes[i] == value

    def contains(self, host):
        """Il dominio o uno dei suoi genitori è segnalato (si ferma a due etichette: mai "com")."""
        labels = host.lower().rstrip(".").split(".")
        candidates = (".".join(labels[i:]) for i in range(len(labels) - 1))
        return any(name not in SHARED_HOSTS and self._has(name) for name in candidates)


class Updater:
    """Scarica la lista quando serve; update() gira in un thread, mai nell'interfaccia."""

    def __init__(self, folder):
        self.folder = folder
        self.index_path = os.path.join(folder, "index.bin")
        self.meta_path = os.path.join(folder, "meta.json")
        self.full_path = os.path.join(folder, "active.txt.gz")

    def meta(self):
        try:
            with open(self.meta_path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_meta(self, meta):
        os.makedirs(self.folder, exist_ok=True)
        with open(self.meta_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(meta, f)
        os.replace(self.meta_path + ".tmp", self.meta_path)

    def _fetch(self, url, etag=None):
        """(testo, etag) oppure (None, etag) se la lista non è cambiata."""
        request = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", "User-Agent": "Devtox"})
        if etag:
            request.add_header("If-None-Match", etag)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                body = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return body, response.headers.get("ETag")
        except urllib.error.HTTPError as e:
            if e.code == 304:
                return None, etag
            raise

    def update(self, now=None):
        """Nuovo indice se è cambiato qualcosa, altrimenti None. Gli errori di rete tengono il vecchio."""
        now = time.time() if now is None else now
        meta = self.meta()
        need_full = now - meta.get("full", 0) >= FULL_EVERY
        need_new = need_full or now - meta.get("new", 0) >= NEW_EVERY
        if not need_new:
            return None
        try:
            changed = False
            if need_full:
                body, etag = self._fetch(FULL_URL, meta.get("etag") if os.path.exists(self.full_path) else None)
                if body is not None:
                    os.makedirs(self.folder, exist_ok=True)
                    with open(self.full_path, "wb") as f:
                        f.write(gzip.compress(body))
                    changed = True
                meta.update(full=now, etag=etag)
            new_body, _etag = self._fetch(NEW_URL)
            meta["new"] = now
        except (OSError, ValueError, urllib.error.URLError) as e:
            logger.warning("lista anti-phishing non aggiornata: %s", e)
            return None
        try:
            with open(self.full_path, "rb") as f:
                full = gzip.decompress(f.read()).decode("utf-8", errors="replace")
        except OSError:
            full = ""
        domains = parse_domains(full) + parse_domains((new_body or b"").decode("utf-8", errors="replace"))
        index = Index.build(domains)
        index.save(self.index_path)
        meta["count"] = len(index)
        self._save_meta(meta)
        logger.info("lista anti-phishing aggiornata: %d domini%s", len(index), "" if changed else " (completa invariata)")
        return index


class Guard:
    """Controlla le navigazioni della pagina principale contro l'indice locale."""

    def __init__(self, enabled):
        self._enabled = enabled          # enabled(): legge la configurazione a ogni controllo
        self.index = Index()
        self._allowed = set()            # "continua comunque": vale fino alla chiusura

    def start(self, folder, on_ready=None):
        """Carica l'indice salvato e aggiorna la lista in un thread, se è il momento."""
        updater = Updater(folder)
        self.index = Index.load(updater.index_path)

        def worker():
            index = updater.update()
            if index is not None:
                self.index = index  # assegnazione atomica: il thread di GTK legge sempre un indice intero
            if on_ready is not None:
                on_ready()
        # DEVTOX_NO_NETWORK: test e screenshot non scaricano mai niente
        if self._enabled() and not os.environ.get("DEVTOX_NO_NETWORK"):
            threading.Thread(target=worker, daemon=True).start()
        return updater

    def blocked_page(self, uri):
        """URL di devtox://blocked se l'indirizzo è segnalato, altrimenti None."""
        if not self._enabled() or not len(self.index):
            return None
        host = navigation.http_host(uri)
        if not host or navigation.is_local_host(host) or host in self._allowed:
            return None
        if not self.index.contains(host):
            return None
        return f"{BLOCKED_URL}?" + urllib.parse.urlencode({"url": uri})

    def allow(self, params):
        """devtox://blocked?continue: con il token giusto il sito vale per la sessione; restituisce l'URL."""
        url = params.get("url", "")
        host = navigation.http_host(url)
        if not host or not secrets.compare_digest(params.get("token", ""), TOKEN):
            return None
        self._allowed.add(host)
        return url

    def on_decide_policy(self, webview, decision, decision_type):
        from gi.repository import WebKit2  # solo nel browser: i test usano le funzioni qui sopra
        if decision_type != WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            return False
        action = decision.get_navigation_action()
        if action.get_frame_name():  # sotto-frame con nome: si controlla solo la pagina principale
            return False
        page = self.blocked_page(action.get_request().get_uri())
        if page is None:
            return False
        decision.ignore()
        webview.load_uri(page)
        return True


def render_blocked(params, guard):
    """devtox://blocked?url=...: avviso; con continue=1 e il token, il sito vale per la sessione."""
    from . import utils
    from .i18n import _
    if params.get("continue") == "1":
        url = guard.allow(params)
        target = json.dumps(url or navigation.START_URL).replace("<", "\\u003c")
        return f'<!doctype html><meta charset="utf-8"><script>location.replace({target});</script>'
    url = params.get("url", "")
    continue_url = f"{BLOCKED_URL}?" + urllib.parse.urlencode({"continue": "1", "token": TOKEN, "url": url})
    source = _("Fonte: la lista pubblica {name}, scaricata e controllata su questo PC. "
               "Si spegne in devtox://setup.").format(name=SOURCE_NAME)
    return utils.render_template(
        "blocked.html",
        host=html.escape(navigation.http_host(url) or url),
        continue_url=html.escape(continue_url, quote=True),
        source=html.escape(source),
    )
