"""Configurazione iniziale (sr://setup): lingua, ricerca, privacy, sviluppo, browser predefinito.

Si apre al primo avvio e dal menu "Personalizza". Il modulo è una normale
pagina sr:// con un form GET verso sé stessa; il salvataggio richiede un
token casuale per processo, così nessun'altra pagina può cambiare la
configurazione con un link (le pagine web non possono comunque aprire sr://).
"""

import html
import json
import os
import secrets
import shutil
import subprocess

from gi.repository import GLib

from . import i18n, navigation, utils
from .i18n import _
from .log import logger

DESKTOP_FILE = "shellrunner.desktop"
MAX_DEV_PORTS = 20

# Interruttori della privacy: (chiave del form, voci di config.json, titolo, spiegazione)
PRIVACY_SWITCHES = [
    ("https_only", ("https_only",), _("HTTPS ovunque"),
     _("I siti vengono aperti in modo cifrato; per localhost e rete locale resta l'HTTP.")),
    ("third_party_cookies", ("block_third_party_cookies",), _("Blocca i cookie di terze parti"),
     _("I cookie dei siti incorporati non ti seguono da una pagina all'altra.")),
    ("fingerprint", ("fingerprint_protection",), _("Anti-fingerprinting"),
     _("Canvas, WebGL e numero di core restituiscono valori alterati per ogni sito.")),
    ("gpc", ("send_gpc", "trim_referer"), _("Global Privacy Control e Referer ridotto"),
     _("Chiedi ai siti di non vendere i tuoi dati e non rivelare da quale pagina arrivi.")),
    ("history", ("history_enabled",), _("Cronologia"),
     _("Ricorda le pagine visitate per i suggerimenti della barra degli indirizzi.")),
    ("restore_session", ("restore_session",), _("Riapri le tab all'avvio"),
     _("Le tab tornano come le hai lasciate, caricate solo quando le selezioni.")),
    ("persistent_data", ("persistent_data",), _("Resta connesso ai siti"),
     _("Cookie e dati dei siti restano tra un avvio e l'altro. Spento: ogni avvio parte da zero.")),
]
# Le preimpostazioni accendono o spengono gli interruttori qui sopra (lato pagina, con JS)
PRESETS = {
    "balanced": {"https_only", "third_party_cookies", "fingerprint", "gpc", "history", "restore_session",
                 "persistent_data"},
    "strict": {"https_only", "third_party_cookies", "fingerprint", "gpc"},
}
# Queste voci vengono lette quando nasce il profilo: cambiano solo dopo un riavvio
RESTART_KEYS = {"language", "persistent_data", "send_gpc", "trim_referer", "block_third_party_cookies"}

SEARCH_NOTES = {
    "duckduckgo": _("Non profila le ricerche. Predefinito."),
    "startpage": _("Risultati di Google senza tracciamento."),
    "brave": _("Indice proprio, senza profilazione."),
    "mojeek": _("Indice proprio, piccolo e indipendente."),
    "ecosia": _("Usa i ricavi per piantare alberi."),
    "google": _("I risultati migliori per molti, ma le ricerche vengono profilate."),
}


class Setup:
    """Stato della pagina: config, token e i collegamenti verso il browser in esecuzione."""

    def __init__(self, config, apply_live, restart):
        self.config = config
        self.token = secrets.token_urlsafe(18)
        self._apply_live = apply_live  # ricarica filtri e script dopo il salvataggio
        self._restart = restart

    def render(self, params):
        if not secrets.compare_digest(params.get("token", ""), self.token):
            return self._form()
        if params.get("restart") == "1":
            GLib.idle_add(self._restart)
            return _page(_("Riavvio…"), f"<h1>{html.escape(_('Riavvio…'))}</h1>")
        if params.get("skip") == "1":
            self.config.set("setup_done", True)
            return _redirect(navigation.WELCOME_URL)
        if params.get("save") == "1":
            return self._save(params)
        return self._form()

    # --- Salvataggio ----------------------------------------------------

    def _save(self, params):
        changes = {"setup_done": True}
        language = params.get("language", "")
        if language in i18n.LANGUAGES:
            changes["language"] = language
        engine = params.get("search_engine", "")
        if engine in navigation.SEARCH_ENGINES:
            changes["search_engine"] = engine
        for field, keys, _title, _hint in PRIVACY_SWITCHES:
            for key in keys:
                changes[key] = params.get(field) == "on"
        changes["ai_enabled"] = params.get("ai_enabled") == "on"
        ports = parse_ports(params.get("dev_ports", ""))
        if ports is not None:
            changes["dev_ports"] = ports

        restart_needed = (
            changes.get("language", i18n.language) != i18n.language
            or any(self.config[k] != v for k, v in changes.items() if k in RESTART_KEYS and k != "language")
            or changes["ai_enabled"] != self.config["ai_enabled"]
        )
        for key, value in changes.items():
            self.config.set(key, value)
        navigation.set_search_engine(self.config["search_engine"])
        self._apply_live()

        notes = []
        if params.get("default_browser") == "on":
            ok, message = set_default_browser()
            notes.append((ok, message))
        if not restart_needed and all(ok for ok, _message in notes):
            return _redirect(navigation.WELCOME_URL)
        return self._done(restart_needed, notes)

    def _done(self, restart_needed, notes):
        body = [f"<h1>{html.escape(_('Impostazioni salvate'))}</h1>"]
        for ok, message in notes:
            css = "" if ok else ' class="warn"'
            body.append(f"<p{css}>{html.escape(message)}</p>")
        actions = []
        if restart_needed:
            body.append(f'<p class="lead">{html.escape(_("Lingua e alcune protezioni cambiano dopo un riavvio. Le tab aperte vengono ripristinate."))}</p>')
            actions.append(f'<a class="button" href="{navigation.SETUP_URL}?token={self.token}&amp;restart=1">'
                           f'{html.escape(_("Riavvia ora"))}</a>')
        actions.append(f'<a class="button ghost" href="{navigation.WELCOME_URL}">{html.escape(_("Continua"))}</a>')
        body.append(f'<p class="actions">{" ".join(actions)}</p>')
        return _page(_("Impostazioni salvate"), "\n".join(body))

    # --- Form -----------------------------------------------------------

    def _form(self):
        config = self.config
        e = html.escape

        def radio(name, value, label, note, checked):
            return (f'<label class="choice"><input type="radio" name="{name}" value="{e(value)}"'
                    f'{" checked" if checked else ""}><span><strong>{e(label)}</strong>'
                    f'<small>{e(note)}</small></span></label>')

        def switch(name, label, note, checked):
            return (f'<label class="switch"><input type="checkbox" name="{name}"'
                    f'{" checked" if checked else ""}><span><strong>{e(label)}</strong>'
                    f'<small>{e(note)}</small></span></label>')

        current_language = config["language"] or i18n.language
        languages = "".join(
            radio("language", code, name, "", code == current_language) for code, name in i18n.LANGUAGES.items()
        )
        engines = "".join(
            radio("search_engine", key, name, SEARCH_NOTES.get(key, ""), key == config["search_engine"])
            for key, (name, _url) in navigation.SEARCH_ENGINES.items()
        )
        privacy = "".join(
            switch(field, title, hint, all(config[k] for k in keys))
            for field, keys, title, hint in PRIVACY_SWITCHES
        )
        ports = ", ".join(str(p) for p in config["dev_ports"])
        desktop = desktop_file_installed()
        default_browser = (
            switch("default_browser", _("Imposta Shellrunner come browser predefinito"),
                   _("I link aperti da altre applicazioni arrivano qui."), False)
            if desktop else
            f'<p class="hint">{e(_("Per impostarlo come browser predefinito installalo con install.sh."))}</p>'
        )
        presets = "".join(
            f'<button type="button" class="preset" data-preset="{name}">{e(label)}</button>'
            for name, label in (("balanced", _("Bilanciata (consigliata)")), ("strict", _("Massima privacy")))
        )
        preset_data = {name: sorted(fields) for name, fields in PRESETS.items()}
        all_fields = [field for field, *_rest in PRIVACY_SWITCHES]
        placeholders = {key: _("Cerca con {engine} o scrivi un indirizzo").format(engine=name)
                        for key, (name, _url) in navigation.SEARCH_ENGINES.items()}
        summary_words = {"https_only": _("solo HTTPS"), "fingerprint": _("anti-fingerprinting"),
                         "gpc": "GPC", "third_party_cookies": _("cookie di terze parti bloccati")}
        current_placeholder = placeholders.get(config["search_engine"], "")

        def row(title, note, panel, extra=""):
            return (f'<section class="setting"><div class="about"><h2>{e(title)}</h2>'
                    f'<p>{e(note)}</p>{extra}</div><div class="panel">{panel}</div></section>')

        body = f"""
<div class="settings">
<h1>{e(_("Personalizza Shellrunner"))}</h1>
<p class="lead">{e(_("Un minuto per scegliere come deve comportarsi. Puoi cambiare tutto più tardi dal menu."))}</p>
<form action="{navigation.SETUP_URL}" method="get">
  <input type="hidden" name="token" value="{self.token}">
  <input type="hidden" name="save" value="1">
  {row(_("Lingua"), _("Menu, pagine interne e messaggi. Cambia dopo un riavvio."),
       f'<div class="choices row">{languages}</div>')}
  {row(_("Motore di ricerca"), _("Dove finisce quello che scrivi nella barra degli indirizzi quando non è un indirizzo."),
       f'<div class="choices">{engines}</div>'
       f'<p class="preview" aria-live="polite"><span class="preview-bar" id="search-preview">'
       f'{e(current_placeholder)}</span></p>')}
  {row(_("Privacy"), _("Tutto resta su questo PC. Ogni protezione si può spegnere per un solo sito dallo scudo nella barra."),
       f'<p class="presets">{presets}</p><div class="switches">{privacy}</div>',
       f'<p class="summary" id="privacy-summary" aria-live="polite"></p>')}
  {row(_("Sviluppo"), _("I server che avvii tu compaiono da soli nella pagina iniziale, con la cartella del progetto."),
       f'''<label class="field"><strong>{e(_("Porte da controllare comunque"))}</strong>
    <input name="dev_ports" value="{e(ports)}" inputmode="numeric" spellcheck="false">
    <small>{e(_("Separate da virgole. Servono per i server di Docker, di root o di altri utenti, che non si vedono da /proc."))}</small></label>
  <div class="switches">{switch("ai_enabled", _("Assistente IA locale"),
            _("Riassunti e spiegazioni con Ollama, sul tuo PC. Spento: il pannello IA sparisce."),
            config["ai_enabled"])}</div>''')}
  {row(_("Sistema"), _("Come si comporta Shellrunner con il resto del desktop."),
       f'<div class="switches">{default_browser}</div>')}
  <p class="actions sticky">
    <button class="button" type="submit">{e(_("Salva e inizia"))}</button>
    <a class="button ghost" href="{navigation.SETUP_URL}?token={self.token}&amp;skip=1">{e(_("Salta"))}</a>
  </p>
</form>
</div>
<script>
  const presets = {_json(preset_data)};
  const fields = {_json(all_fields)};
  const placeholders = {_json(placeholders)};
  const words = {_json(summary_words)};
  const box = (name) => document.querySelector(`input[name="${{name}}"]`);
  // La riga di riepilogo è la stessa della pagina iniziale: si vede subito cosa cambia
  function summarize() {{
    const on = Object.keys(words).filter((name) => box(name) && box(name).checked).map((name) => words[name]);
    document.getElementById("privacy-summary").textContent = on.length ? on.join(" · ") : {_json(_("Nessuna protezione accesa"))};
  }}
  for (const button of document.querySelectorAll(".preset")) {{
    button.addEventListener("click", () => {{
      const on = presets[button.dataset.preset];
      for (const name of fields) box(name).checked = on.includes(name);
      summarize();
    }});
  }}
  for (const name of fields) box(name).addEventListener("change", summarize);
  for (const radio of document.querySelectorAll('input[name="search_engine"]')) {{
    radio.addEventListener("change", () => {{
      document.getElementById("search-preview").textContent = placeholders[radio.value];
    }});
  }}
  summarize();
</script>
"""
        return _page(_("Personalizza Shellrunner"), body)


def parse_ports(text):
    """'5173, 3000' -> [5173, 3000]; None se il testo non è valido (si tiene il valore vecchio)."""
    ports = []
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit() or not 0 < int(part) < 65536:
            return None
        if int(part) not in ports:
            ports.append(int(part))
    return ports[:MAX_DEV_PORTS]


def desktop_file_installed():
    for directory in [GLib.get_user_data_dir(), *GLib.get_system_data_dirs()]:
        if os.path.exists(os.path.join(directory, "applications", DESKTOP_FILE)):
            return True
    return False


def set_default_browser():
    """(riuscito, messaggio) dopo xdg-settings; niente sudo, vale solo per l'utente."""
    if shutil.which("xdg-settings") is None:
        return False, _("xdg-settings non trovato: imposta il browser predefinito dalle impostazioni di sistema.")
    try:
        subprocess.run(["xdg-settings", "set", "default-web-browser", DESKTOP_FILE],
                       check=True, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("xdg-settings non riuscito: %s", e)
        return False, _("Non sono riuscito a impostarlo come browser predefinito: fallo dalle impostazioni di sistema.")
    return True, _("Shellrunner è ora il browser predefinito.")


def _json(value):
    return json.dumps(value).replace("<", "\\u003c")


def _page(title, body):
    return utils.render_template("info.html", title=html.escape(title), body=body)


def _redirect(url):
    return f'<!doctype html><meta charset="utf-8"><script>location.replace({_json(url)});</script>'
