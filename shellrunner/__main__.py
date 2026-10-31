"""Avvio: python -m shellrunner [indirizzi...]"""

import argparse
import os
import sys

from gi.repository import GLib, Gtk

from . import __version__, about, devtools, log, navigation, onboarding, privacy, startpage, theme, utils, webext
from .i18n import _
from .config import Config
from .control import ControlServer, send_to_running
from .storage import Storage
from .window import BrowserWindow


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="shellrunner", description=_("Browser leggero per sviluppatori, con terminale integrato.")
    )
    parser.add_argument("urls", nargs="*", metavar=_("INDIRIZZO"),
                        help=_("indirizzi o ricerche da aprire in nuove tab"))
    parser.add_argument("--version", action="version", version=f"Shellrunner {__version__}")
    parser.add_argument("--check", action="store_true",
                        help=_("controlla dipendenze ed estensione privacy, poi esce"))
    parser.add_argument("--debug", action="store_true", help=_("log dettagliato anche sul terminale"))
    parser.add_argument("--new-instance", action="store_true",
                        help=_("non passare gli indirizzi a una finestra già aperta"))
    return parser.parse_args(argv)


def check():
    """Diagnostica per le segnalazioni: le dipendenze ci sono, altrimenti non saremmo qui."""
    for name, version in about.versions():
        print(f"{name:<12} {version}")
    webext.ensure_built()
    print(f"{_('Estensione'):<12} {webext.status}")
    print(f"{'Log':<12} {log.log_path()}")
    return 0 if webext.status_ok else 1


def main(argv=None):
    args = parse_args(argv)
    log.setup(debug=args.debug)
    if args.check:
        return check()

    # Una finestra è già aperta: le passiamo gli indirizzi invece di aprirne un'altra
    if args.urls and not args.new_instance:
        first = send_to_running({"cmd": "open", "url": args.urls[0]})
        if first is not None:
            for url in args.urls[1:]:
                send_to_running({"cmd": "open", "url": url})
            return 0

    # Nome del programma = classe della finestra: il file .desktop la riconosce
    GLib.set_prgname(utils.APP_ID)
    GLib.set_application_name(utils.APP_TITLE)
    Gtk.Window.set_default_icon_from_file(os.path.join(utils.RESOURCES_DIR, "shellrunner.svg"))

    config = Config()
    navigation.set_search_engine(config["search_engine"])
    storage = Storage()
    storage.expire_history(config["history_days"])
    theme.install()

    pages = {
        "start": lambda _params: startpage.render(config, storage),
        "source": devtools.render_source_page,
        "about": lambda _params: about.render_about_page(config.path),
        "welcome": about.render_welcome_page,
    }
    running = {}  # finestra e server, quando esistono: servono al riavvio chiesto da sr://setup

    def apply_live():
        content_scripts.rebuild()
        content_filter.reload()

    def restart():
        window, server = running["window"], running["server"]
        window.save_session()
        server.stop()
        storage.close()
        log.logger.info("riavvio chiesto da sr://setup")
        os.execv(sys.executable, [sys.executable, "-m", "shellrunner", "--new-instance"])

    setup = onboarding.Setup(config, apply_live, restart)
    pages["setup"] = setup.render
    context = privacy.create_web_context(config)
    navigation.register_internal_scheme(context, pages)
    content_manager = privacy.create_content_manager()
    content_scripts = privacy.ContentScripts(config, content_manager)
    content_scripts.rebuild()
    content_filter = privacy.ContentFilter(config, content_manager)

    def start():
        # La finestra nasce solo dopo la compilazione dei filtri:
        # nessuna pagina viene caricata senza blocklist e regole HTTPS
        window = BrowserWindow(config, context, content_manager, content_filter,
                               content_scripts, storage, pages)
        window.show()
        server = ControlServer(window)
        server.start()
        running.update(window=window, server=server)

        def on_destroy(_window):
            window.save_session()
            server.stop()
            storage.close()
            Gtk.main_quit()

        window.connect("destroy", on_destroy)
        if not config["setup_done"]:
            window.new_tab(navigation.SETUP_URL)
        for url in args.urls:
            window.open_from_cli(url)

    log.logger.info("Shellrunner %s avviato", __version__)
    content_filter.reload(on_done=start)
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
