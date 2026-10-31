#!/bin/sh
# Installa Shellrunner per l'utente corrente, senza sudo e senza rete.
#
#   sh install.sh              installa (o aggiorna) in ~/.local
#   sh install.sh --uninstall  rimuove programma e lanciatori (il profilo resta)
#
# Le librerie di sistema (GTK, WebKitGTK, VTE) vanno installate prima:
# se mancano, l'installazione si ferma e dice quali pacchetti servono.
set -eu

src="$(cd "$(dirname "$0")" && pwd)"

# Messaggi in italiano o in inglese, come l'interfaccia: say "italiano" "english"
case "${LANGUAGE:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}" in
    it*) say() { echo "$1"; } ;;
    *) say() { echo "$2"; } ;;
esac
prefix="${PREFIX:-$HOME/.local}"
app="$prefix/share/shellrunner/app"
bin="$prefix/bin"
apps="$prefix/share/applications"
icons="$prefix/share/icons/hicolor/scalable/apps"
metainfo="$prefix/share/metainfo"

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$prefix/share/shellrunner/app"
    rm -f "$bin/shellrunner" "$bin/sr" "$apps/shellrunner.desktop" "$icons/shellrunner.svg" \
        "$metainfo/io.github.shellrunner.Shellrunner.metainfo.xml"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" || true
    say "Shellrunner rimosso. Il profilo resta in ~/.config, ~/.local/share e ~/.cache (cartelle shellrunner)." \
        "Shellrunner removed. Your profile is kept in ~/.config, ~/.local/share and ~/.cache (shellrunner folders)."
    exit 0
fi

python="$(command -v python3 || true)"
if [ -z "$python" ]; then
    say "Serve python3." "python3 is required." >&2
    exit 1
fi

# Controllo delle dipendenze con il Python di sistema, lo stesso che userà il lanciatore
if ! (cd "$src" && "$python" -c "from shellrunner import deps; deps.require()"); then
    exit 1
fi

mkdir -p "$app" "$bin" "$apps" "$icons" "$metainfo"
rm -rf "${app:?}/shellrunner"
cp -r "$src/shellrunner" "$app/shellrunner"
find "$app/shellrunner" -name __pycache__ -prune -exec rm -rf {} +
rm -rf "$app/shellrunner/webext/build"
# bin/ accanto al pacchetto: i terminali integrati trovano sr anche fuori dal PATH
rm -rf "${app:?}/bin"
cp -r "$src/bin" "$app/bin"

cat > "$bin/shellrunner" <<LAUNCHER
#!/bin/sh
PYTHONPATH="$app\${PYTHONPATH:+:\$PYTHONPATH}" exec "$python" -m shellrunner "\$@"
LAUNCHER
chmod +x "$bin/shellrunner"
# sr è autonomo: niente GTK, parte in pochi millisecondi
rm -f "$bin/sr"
cp "$src/bin/sr" "$bin/sr"
chmod +x "$bin/sr"

sed "s|^Exec=shellrunner|Exec=$bin/shellrunner|" "$src/data/shellrunner.desktop" > "$apps/shellrunner.desktop"
cp "$src/shellrunner/resources/shellrunner.svg" "$icons/shellrunner.svg"
cp "$src/data/io.github.shellrunner.Shellrunner.metainfo.xml" "$metainfo/"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" || true

# Compila subito l'estensione privacy, così il primo avvio è già completo
PYTHONPATH="$app" "$python" -m shellrunner --check || true

echo
say "Installato. Avvia con: shellrunner   (oppure dal menu delle applicazioni)" \
    "Installed. Start it with: shellrunner   (or from the applications menu)"
case ":$PATH:" in
    *":$bin:"*) ;;
    *) say "Attenzione: $bin non è nel PATH." "Warning: $bin is not in your PATH." ;;
esac
say "Per renderlo il browser predefinito: xdg-settings set default-web-browser shellrunner.desktop" \
    "To make it the default browser: xdg-settings set default-web-browser shellrunner.desktop"
