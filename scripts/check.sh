#!/bin/sh
# Tutti i test, compresa la prova d'avvio con una finestra vera dentro Xvfb.
# Uso: sh scripts/check.sh   (dalla cartella del progetto)
set -eu
cd "$(dirname "$0")/.."
python="${PYTHON:-.venv/bin/python}"
[ -x "$python" ] || python=python3
if command -v xvfb-run >/dev/null 2>&1; then
    # GDK_BACKEND e WAYLAND_DISPLAY: la finestra deve aprirsi in Xvfb, non sul desktop vero
    env -u WAYLAND_DISPLAY GDK_BACKEND=x11 DEVTOX_GUI_TESTS=1 \
        xvfb-run -a "$python" -m unittest -v "$@"
else
    echo "xvfb-run non trovato: salto la prova d'avvio (sudo apt install xvfb)" >&2
    "$python" -m unittest -v "$@"
fi
