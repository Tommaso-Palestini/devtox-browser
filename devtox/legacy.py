"""Passaggio dal nome vecchio (Shellrunner) a Devtox.

Al primo avvio le cartelle del profilo ~/.config/shellrunner, ~/.local/share/shellrunner,
~/.cache/shellrunner e ~/.local/state/shellrunner diventano .../devtox: cronologia,
preferiti, cookie, sessione e impostazioni restano. Gira prima della scelta della lingua
(che legge config.json), quindi usa solo os e le variabili XDG, senza GLib.
Un profilo devtox già esistente non viene mai toccato.
"""

import os

OLD, NEW = "shellrunner", "devtox"
OLD_SCHEME, NEW_SCHEME = "sr://", "devtox://"
XDG_DEFAULTS = {
    "XDG_CONFIG_HOME": ".config",
    "XDG_DATA_HOME": ".local/share",
    "XDG_CACHE_HOME": ".cache",
    "XDG_STATE_HOME": ".local/state",
}
# File che portano il nome nell'interno della cartella
_RENAMES = {"shellrunner.sqlite": "devtox.sqlite", "shellrunner.log": "devtox.log"}
_STALE = [os.path.join("webext", "libsrprivacy.so")]  # WebKit carica ogni .so della cartella


def _base(var, env):
    return env.get(var) or os.path.join(os.path.expanduser("~"), XDG_DEFAULTS[var])


def migrate(env=None):
    """Sposta le cartelle vecchie; restituisce [(vecchia, nuova)] di quelle spostate."""
    env = os.environ if env is None else env
    moved = []
    for var in XDG_DEFAULTS:
        base = _base(var, env)
        old, new = os.path.join(base, OLD), os.path.join(base, NEW)
        if not os.path.isdir(old) or os.path.exists(new):
            continue
        try:
            os.rename(old, new)
        except OSError:
            continue  # il browser parte comunque, con un profilo nuovo
        for before, after in _RENAMES.items():
            source = os.path.join(new, before)
            if os.path.exists(source) and not os.path.exists(os.path.join(new, after)):
                os.rename(source, os.path.join(new, after))
        for stale in _STALE:
            try:
                os.remove(os.path.join(new, stale))
            except OSError:
                pass
        moved.append((old, new))
    return moved


def session_uri(uri):
    """Le tab salvate da Shellrunner puntano a sr://: diventano devtox://."""
    return NEW_SCHEME + uri[len(OLD_SCHEME):] if uri.startswith(OLD_SCHEME) else uri
