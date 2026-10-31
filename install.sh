#!/bin/sh
# Installa Devtox per l'utente corrente, senza sudo e senza rete.
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
app="$prefix/share/devtox/app"
bin="$prefix/bin"
apps="$prefix/share/applications"
icons="$prefix/share/icons/hicolor/scalable/apps"
metainfo="$prefix/share/metainfo"
id="io.github.Tommaso_Palestini.devtox-browser"

# Prima di Devtox il browser si chiamava Shellrunner: via i suoi file installati
# (il profilo no: lo sposta Devtox stesso al primo avvio)
remove_shellrunner() {
    rm -rf "$prefix/share/shellrunner/app"
    rmdir "$prefix/share/shellrunner" 2>/dev/null || true
    rm -f "$bin/shellrunner" "$bin/sr" "$apps/shellrunner.desktop" "$icons/shellrunner.svg" \
        "$metainfo/io.github.shellrunner.Shellrunner.metainfo.xml"
}

if [ "${1:-}" = "--uninstall" ]; then
    rm -rf "$prefix/share/devtox/app"
    rm -f "$bin/devtox" "$bin/dx" "$apps/$id.desktop" "$icons/$id.svg" "$metainfo/$id.metainfo.xml"
    remove_shellrunner
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" || true
    say "Devtox rimosso. Il profilo resta in ~/.config, ~/.local/share e ~/.cache (cartelle devtox)." \
        "Devtox removed. Your profile is kept in ~/.config, ~/.local/share and ~/.cache (devtox folders)."
    exit 0
fi

python="$(command -v python3 || true)"
if [ -z "$python" ]; then
    say "Serve python3." "python3 is required." >&2
    exit 1
fi

# Controllo delle dipendenze con il Python di sistema, lo stesso che userà il lanciatore
if ! (cd "$src" && "$python" -c "from devtox import deps; deps.require()"); then
    exit 1
fi

mkdir -p "$app" "$bin" "$apps" "$icons" "$metainfo"
rm -rf "${app:?}/devtox"
cp -r "$src/devtox" "$app/devtox"
find "$app/devtox" -name __pycache__ -prune -exec rm -rf {} +
rm -rf "$app/devtox/webext/build"
# bin/ accanto al pacchetto: i terminali integrati trovano dx anche fuori dal PATH
rm -rf "${app:?}/bin"
cp -r "$src/bin" "$app/bin"

cat > "$bin/devtox" <<LAUNCHER
#!/bin/sh
PYTHONPATH="$app\${PYTHONPATH:+:\$PYTHONPATH}" exec "$python" -m devtox "\$@"
LAUNCHER
chmod +x "$bin/devtox"
# dx è autonomo: niente GTK, parte in pochi millisecondi
rm -f "$bin/dx"
cp "$src/bin/dx" "$bin/dx"
chmod +x "$bin/dx"

was_default=""
if command -v xdg-settings >/dev/null 2>&1 && \
        [ "$(xdg-settings get default-web-browser 2>/dev/null || true)" = "shellrunner.desktop" ]; then
    was_default=1
fi
remove_shellrunner

sed "s|^Exec=devtox|Exec=$bin/devtox|" "$src/data/$id.desktop" > "$apps/$id.desktop"
cp "$src/devtox/resources/devtox.svg" "$icons/$id.svg"
cp "$src/data/$id.metainfo.xml" "$metainfo/"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" || true
if [ -n "$was_default" ]; then
    xdg-settings set default-web-browser "$id.desktop" || true
fi

# Compila subito l'estensione privacy, così il primo avvio è già completo
PYTHONPATH="$app" "$python" -m devtox --check || true

echo
say "Installato. Avvia con: devtox   (oppure dal menu delle applicazioni)" \
    "Installed. Start it with: devtox   (or from the applications menu)"
case ":$PATH:" in
    *":$bin:"*) ;;
    *) say "Attenzione: $bin non è nel PATH." "Warning: $bin is not in your PATH." ;;
esac
say "Per renderlo il browser predefinito: xdg-settings set default-web-browser $id.desktop" \
    "To make it the default browser: xdg-settings set default-web-browser $id.desktop"
