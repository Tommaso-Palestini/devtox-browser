"""Test di Shellrunner: python -m unittest (dalla cartella del progetto).

Il profilo dei test vive in una cartella temporanea: le variabili XDG vanno
impostate prima del primo import di GLib, che le legge una volta sola.
"""

import atexit
import os
import shutil
import tempfile

_ROOT = tempfile.mkdtemp(prefix="shellrunner-test-")
atexit.register(shutil.rmtree, _ROOT, True)
tempfile.tempdir = _ROOT  # anche le cartelle create dai singoli test spariscono a fine corsa
for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_RUNTIME_DIR"):
    path = os.path.join(_ROOT, name.lower())
    os.makedirs(path, mode=0o700)
    os.environ[name] = path
# Test deterministici: interfaccia in italiano (la lingua sorgente); l'inglese ha i suoi test
os.environ["LANGUAGE"] = "it"
