"""Controllo delle librerie di sistema: GTK, WebKit e VTE non si installano con pip.

Va eseguito prima di qualsiasi import da gi.repository. Se manca qualcosa
l'avvio si ferma con un messaggio che dice cosa installare, invece di un
traceback di PyGObject.
"""

import shutil
import sys

from .i18n import _

# (namespace, versione, cosa installare: apt, dnf, pacman)
REQUIRED = [
    ("Gtk", "3.0", ("gir1.2-gtk-3.0", "gtk3", "gtk3")),
    ("Gdk", "3.0", ("gir1.2-gtk-3.0", "gtk3", "gtk3")),
    ("WebKit2", "4.1", ("gir1.2-webkit2-4.1", "webkit2gtk4.1", "webkit2gtk-4.1")),
    ("Soup", "3.0", ("gir1.2-soup-3.0", "libsoup3", "libsoup3")),
    ("Vte", "2.91", ("gir1.2-vte-2.91", "vte291", "vte3")),
]
PYGOBJECT = ("python3-gi", "python3-gobject", "python-gobject")
PYCAIRO = ("python3-gi-cairo", "python3-cairo", "python-cairo")
MANAGERS = ("apt", "dnf", "pacman")


def missing():
    """[(descrizione, pacchetti)] di quello che manca; vuota se è tutto a posto."""
    try:
        import gi
    except ImportError:
        return [("PyGObject (modulo gi)", PYGOBJECT)]
    result = []
    try:
        import cairo  # noqa: F401  (screenshot e indicatore della RAM)
    except ImportError:
        result.append(("pycairo", PYCAIRO))
    for namespace, version, packages in REQUIRED:
        try:
            gi.require_version(namespace, version)
        except ValueError:
            result.append((f"{namespace} {version}", packages))
    return result


def install_hint(problems):
    """Comando di installazione per il gestore di pacchetti presente, o per tutti."""
    commands = {
        "apt": "sudo apt install",
        "dnf": "sudo dnf install",
        "pacman": "sudo pacman -S",
    }
    available = [m for m in MANAGERS if shutil.which(m)] or list(MANAGERS)
    lines = []
    for manager in available:
        index = MANAGERS.index(manager)
        packages = sorted({p[1][index] for p in problems})
        lines.append(f"  {commands[manager]} {' '.join(packages)}")
    return "\n".join(lines)


def require():
    problems = missing()
    if not problems:
        return
    names = ", ".join(p[0] for p in problems)
    sys.exit(
        _("Shellrunner: mancano librerie di sistema ({names}).").format(names=names) + "\n"
        + _("Installale con:") + "\n" + install_hint(problems) + "\n"
        + _("Se usi un virtualenv, crealo con --system-site-packages.")
    )
