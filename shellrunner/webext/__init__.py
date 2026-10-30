"""Estensione C del web process: compilata al primo avvio nella cache del profilo.

Così funziona anche quando il pacchetto è installato in una cartella di
sola lettura, e viene ricompilata da sola quando cambia il sorgente.
Senza gcc o senza gli header di GLib il browser parte lo stesso, solo
senza Sec-GPC nell'header e senza Referer ridotto.
"""

import os
import shutil
import subprocess

from .. import utils
from ..i18n import _
from ..log import logger

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES = [os.path.join(SOURCE_DIR, name) for name in ("privacy_ext.c", "build.sh")]
LIB_NAME = "libsrprivacy.so"

# Ultimo esito, mostrato in sr://about
status = _("non ancora controllata")
status_ok = False


def build_dir():
    return os.path.join(utils.cache_dir(), "webext")


def _up_to_date(lib):
    try:
        built = os.path.getmtime(lib)
    except OSError:
        return False
    return all(os.path.getmtime(src) <= built for src in SOURCES)


def ensure_built():
    """Cartella con la libreria pronta, oppure None se non si può compilare."""
    global status, status_ok
    out = build_dir()
    lib = os.path.join(out, LIB_NAME)
    if _up_to_date(lib):
        status, status_ok = _("attiva ({path})").format(path=lib), True
        return out
    missing = [tool for tool in ("gcc", "pkg-config") if shutil.which(tool) is None]
    if missing:
        status = _("non compilata: manca {tools}").format(tools=", ".join(missing))
        logger.warning("estensione privacy %s: Sec-GPC e Referer ridotto non sono attivi", status)
        return None
    try:
        subprocess.run(["sh", SOURCES[1], out], check=True, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        output = getattr(e, "stderr", "") or str(e)
        status = _("compilazione non riuscita (vedi il log)")
        logger.warning("estensione privacy non compilata, Sec-GPC e Referer ridotto non attivi:\n%s",
                       output.strip())
        return None
    status, status_ok = _("attiva, appena compilata ({path})").format(path=lib), True
    logger.info("estensione privacy compilata in %s", out)
    return out
