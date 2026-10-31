"""devtox://import: preferiti e cronologia da un altro browser, con un clic per browser.

L'import parte solo con il token di questa sessione e solo da un profilo che
discover() ha trovato: un indirizzo non può far leggere a Devtox un file a caso.
"""

import html
import os
import secrets
import time

from . import importer, navigation, utils
from .i18n import _

TOKEN = secrets.token_urlsafe(18)
URL = "devtox://import"


def _e(text):
    return html.escape(str(text), quote=True)


def _page(title, body):
    return utils.render_template("info.html", title=_e(title), body=body)


def _since(config):
    return time.time() - max(1, config["history_days"]) * 86400


def render(params, config, storage, discover=importer.discover):
    sources = discover()
    if secrets.compare_digest(params.get("token", ""), TOKEN) and params.get("source"):
        source = next((s for s in sources if s.id == params["source"]), None)
        if source is not None:
            return _done(source, params, config, storage)
    return _form(sources, config)


def _form(sources, config):
    days = config["history_days"]
    history_on = config["history_enabled"]
    lead = _("Preferiti e pagine visitate negli ultimi {days} giorni (fino a {limit}). "
             "Tutto resta su questo PC.").format(days=days, limit=importer.HISTORY_LIMIT)
    title = _("Importa da un altro browser")
    parts = ["<h1>" + _e(title) + "</h1>", '<p class="lead">' + _e(lead) + "</p>"]
    if not sources:
        none = _("Nessun altro browser trovato. Si cercano Firefox, Chrome, Chromium, Brave, "
                 "Edge, Vivaldi, Opera, Zen e LibreWolf, anche come Flatpak e Snap.")
        parts.append("<p>" + _e(none) + "</p>")
    for source in sources:
        bookmarks = len(source.bookmarks())
        if history_on:
            found = len(source.history(_since(config)))
            pages = _("1 pagina") if found == 1 else _("{n} pagine").format(n=found)
            history_box = ('<label class="switch"><input type="checkbox" name="history" checked><span>'
                           f"<strong>{_e(_('Cronologia'))}</strong><small>{_e(pages)}</small></span></label>")
        else:
            off = _("Cronologia spenta in Devtox: si importano solo i preferiti.")
            history_box = '<p class="hint">' + _e(off) + "</p>"
        count = _("1 preferito") if bookmarks == 1 else _("{n} preferiti").format(n=bookmarks)
        home = os.path.expanduser("~")
        where = "~" + source.profile[len(home):] if source.profile.startswith(home + os.sep) else source.profile
        button = _("Importa da {name}").format(name=source.name)
        parts.append(f"""
<section class="setting">
  <div class="about"><h2>{_e(source.name)}</h2><p><code>{_e(where)}</code></p></div>
  <form class="panel" action="{URL}" method="get">
    <input type="hidden" name="token" value="{TOKEN}">
    <input type="hidden" name="source" value="{_e(source.id)}">
    <div class="switches">
      <label class="switch"><input type="checkbox" name="bookmarks" checked><span>
        <strong>{_e(_("Preferiti"))}</strong><small>{_e(count)}</small></span></label>
      {history_box}
    </div>
    <p class="actions compact"><button class="button" type="submit">{_e(button)}</button></p>
  </form>
</section>""")
    note = _("Password e cookie non si importano: l'altro browser li cifra con il portachiavi del sistema, "
             "e copiarli li esporrebbe. Tor Browser non viene mai proposto.")
    parts.append('<p class="hint">' + _e(note) + "</p>")
    return _page(title, '<div class="settings">' + "".join(parts) + "</div>")


def _done(source, params, config, storage):
    added_bookmarks = new_pages = 0
    if params.get("bookmarks") == "on":
        added_bookmarks = storage.import_bookmarks(source.bookmarks())
    if params.get("history") == "on" and config["history_enabled"]:
        new_pages = storage.import_history(source.history(_since(config)))
    summary = _("Da {name}: {bookmarks} preferiti nuovi e {pages} pagine nuove nella cronologia.").format(
        name=source.name, bookmarks=added_bookmarks, pages=new_pages)
    body = (
        f"<h1>{_e(_('Import completato'))}</h1>"
        + '<p class="lead">' + _e(summary) + "</p>"
        + f'<p class="actions"><a class="button" href="{navigation.START_URL}">{_e(_("Vai alla pagina iniziale"))}</a> '
        f'<a class="button ghost" href="{URL}">{_e(_("Importa da un altro browser"))}</a></p>'
    )
    return _page(_("Import completato"), body)
