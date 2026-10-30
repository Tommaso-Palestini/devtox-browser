"""Log su file nel profilo, così chi apre una segnalazione può allegarlo.

~/.local/state/shellrunner/shellrunner.log, ruotato a 1 MB. Anche le
eccezioni non gestite nei callback GTK finiscono qui con il traceback.
"""

import logging
import logging.handlers
import os
import sys

from . import utils

MAX_BYTES = 1024 * 1024
BACKUPS = 2

logger = logging.getLogger(utils.APP_ID)


def log_path():
    return os.path.join(utils.state_dir(), "shellrunner.log")


def setup(debug=False):
    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)
    logger.propagate = False

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("[%(module)s] %(message)s"))
    console.setLevel(level if debug else logging.WARNING)
    logger.addHandler(console)

    try:
        os.makedirs(utils.state_dir(), exist_ok=True)
        to_file = logging.handlers.RotatingFileHandler(
            log_path(), maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8"
        )
    except OSError as e:
        logger.warning("log su file non disponibile: %s", e)
    else:
        to_file.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(module)s] %(message)s"))
        logger.addHandler(to_file)

    def excepthook(kind, value, tb):
        if issubclass(kind, KeyboardInterrupt):
            sys.__excepthook__(kind, value, tb)
            return
        logger.error("eccezione non gestita", exc_info=(kind, value, tb))

    # PyGObject passa da sys.excepthook per gli errori nei callback
    sys.excepthook = excepthook
