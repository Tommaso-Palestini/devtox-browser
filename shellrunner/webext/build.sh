#!/bin/sh
# Compila l'estensione privacy del web process.
# Uso: sh shellrunner/webext/build.sh [cartella di destinazione]
# Senza argomenti la libreria finisce in shellrunner/webext/build/.
# Se sono installati gli header di WebKitGTK 4.1 (libwebkit2gtk-4.1-dev)
# li usa al posto dei prototipi dichiarati a mano in privacy_ext.c.
set -eu
src="$(cd "$(dirname "$0")" && pwd)"
out="${1:-$src/build}"
mkdir -p "$out"
modules="glib-2.0 gobject-2.0 gmodule-2.0"
defines=""
if pkg-config --exists webkit2gtk-web-extension-4.1; then
    modules="$modules webkit2gtk-web-extension-4.1"
    defines="-DSR_WEBKIT_HEADERS"
fi
gcc -shared -fPIC -O2 -Wall -Wextra -Werror $defines \
    $(pkg-config --cflags $modules) \
    -o "$out/libsrprivacy.so.tmp" "$src/privacy_ext.c" \
    $(pkg-config --libs $modules)
mv "$out/libsrprivacy.so.tmp" "$out/libsrprivacy.so"
echo "OK: $out/libsrprivacy.so"
