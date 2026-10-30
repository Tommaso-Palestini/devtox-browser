"""Shellrunner: browser leggero per sviluppatori basato su GTK 3 e WebKit2."""

from . import deps, i18n

__version__ = "0.1.0"

# La lingua prima di tutto: i moduli traducono le loro stringhe quando vengono importati
i18n.setup()
# Le versioni vanno fissate prima di qualsiasi import da gi.repository
deps.require()
