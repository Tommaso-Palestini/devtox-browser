"""Pagine interne informative: sr://about (versioni, percorsi, licenza, privacy) e sr://welcome."""

import html
import platform

from gi.repository import Gtk, Vte, WebKit2

from . import __version__, log, navigation, utils, webext
from .i18n import _

COPYRIGHT = "Copyright © 2026 XENON1354"
LICENSE_URL = "https://www.gnu.org/licenses/gpl-3.0.html"


def _page(title, body):
    return utils.render_template("info.html", title=html.escape(title), body=body)


def versions():
    """Versioni dei componenti, le stesse da allegare a una segnalazione."""
    return [
        ("Shellrunner", __version__),
        ("WebKitGTK", f"{WebKit2.get_major_version()}.{WebKit2.get_minor_version()}."
                      f"{WebKit2.get_micro_version()}"),
        ("GTK", f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"),
        ("VTE", f"{Vte.get_major_version()}.{Vte.get_minor_version()}.{Vte.get_micro_version()}"),
        ("Python", platform.python_version()),
        (_("Sistema"), platform.platform()),
    ]


def render_about_page(config_path):
    e = html.escape

    def rows(pairs):
        return "".join(f"<tr><th>{e(k)}</th><td>{v}</td></tr>" for k, v in pairs)

    version_rows = rows((k, f"<code>{e(v)}</code>") for k, v in versions())
    ext_class = "" if webext.status_ok else ' class="warn"'
    path_rows = rows([
        (_("Configurazione"), f"<code>{e(config_path)}</code>"),
        (_("Dati del profilo"), f"<code>{e(utils.data_dir())}</code>"),
        (_("Cache"), f"<code>{e(utils.cache_dir())}</code>"),
        (_("Log"), f"<code>{e(log.log_path())}</code>"),
        (_("Socket per sr"), f"<code>{e(utils.socket_path())}</code>"),
        (_("Estensione privacy"), f"<span{ext_class}>{e(webext.status)}</span>"),
    ])
    body = f"""
<h1>Shellrunner</h1>
<p class="lead">{e(_("Browser leggero per sviluppatori, con terminale integrato."))}</p>
<h2>{e(_("Versioni"))}</h2>
<table>{version_rows}</table>
<h2>{e(_("Percorsi"))}</h2>
<table>{path_rows}</table>
<p>{e(_("Se apri una segnalazione, copia la tabella delle versioni e allega il log."))}</p>

<h2>{e(_("Privacy"))}</h2>
<p>{e(_("Shellrunner non raccoglie dati e non ha telemetria: non controlla aggiornamenti, non invia "
        "statistiche né segnalazioni di errore. Cronologia, preferiti, cookie e log restano in questo PC, "
        "nelle cartelle elencate qui sopra."))}</p>
<p>{e(_("Le uniche connessioni sono quelle che chiedi tu: i siti che apri e il motore di ricerca "
        "({engine}) quando scrivi una ricerca. L'assistente IA parla solo con Ollama su 127.0.0.1.").format(
            engine=navigation.search_engine_name()))}</p>

<h2>{e(_("Licenza"))}</h2>
<p>{e(COPYRIGHT)}</p>
<p>{e(_("Shellrunner è software libero: puoi redistribuirlo e/o modificarlo secondo i termini della "
        "GNU General Public License pubblicata dalla Free Software Foundation, versione 3 o (a tua scelta) "
        "successiva."))}</p>
<p>{e(_("Shellrunner è distribuito nella speranza che sia utile, ma SENZA ALCUNA GARANZIA; senza "
        "nemmeno la garanzia implicita di COMMERCIABILITÀ o IDONEITÀ PER UNO SCOPO PARTICOLARE."))}</p>
<p><a href="{LICENSE_URL}">{e(_("Testo completo della licenza GPL-3.0"))}</a></p>
<p class="hint">{e(_("Usa WebKitGTK, GTK, VTE e PyGObject (licenze LGPL), forniti dal sistema operativo."))}</p>
"""
    return _page(_("Informazioni su Shellrunner"), body)


def render_welcome_page(_params=None):
    e = html.escape
    body = f"""
<h1>{e(_("Benvenuto in Shellrunner"))}</h1>
<p class="lead">{e(_("Trenta secondi per le quattro cose che lo rendono diverso."))}</p>
<ol class="steps">
  <li><strong><kbd>Ctrl+K</kbd> &nbsp;{e(_("Palette dei comandi"))}</strong>
      {e(_("Tutte le azioni, le tab aperte, i preferiti e la cronologia in un solo campo."))}</li>
  <li class="shell"><strong><kbd>Ctrl+`</kbd> &nbsp;{e(_("Terminale"))}</strong>
      {_("Sale dal basso, nella stessa finestra. <kbd>Ctrl+Shift+`</kbd> ne apre un altro.")}</li>
  <li class="shell"><strong><code>sr open localhost:5173</code> &nbsp;{e(_("Il browser dal terminale"))}</strong>
      {_("<code>sr open</code> apre una tab, <code>sr tabs</code> le elenca, <code>sr mem</code> mostra la memoria.")}</li>
  <li><strong><kbd>Ctrl+Shift+L</kbd> &nbsp;{e(_("Server locali"))}</strong>
      {e(_("Le porte di sviluppo attive compaiono anche nella pagina iniziale."))}</li>
</ol>
<h2>{e(_("Privacy di serie"))}</h2>
<p>{e(_("HTTPS forzato (tranne localhost e rete locale), cookie di terze parti bloccati, blocklist locale, "
        "anti-fingerprinting e Global Privacy Control. Tutto si regola per sito dallo scudo nella barra "
        "degli indirizzi. Nessuna telemetria."))}</p>
<h2>{e(_("Poi"))}</h2>
<p>{_('Le altre scorciatoie sono nella pagina iniziale. Puoi cambiare le scelte in '
      '<a href="sr://setup">sr://setup</a>; versioni, percorsi e licenza sono in '
      '<a href="sr://about">sr://about</a>.')}</p>
<p class="actions"><a class="button" href="sr://start">{e(_("Inizia a navigare"))}</a></p>
"""
    return _page(_("Benvenuto"), body)
