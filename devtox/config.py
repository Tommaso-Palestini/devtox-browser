"""Configurazione utente in ~/.config/devtox/config.json."""

import copy
import json
import os

from . import utils
from .log import logger

DEFAULTS = {
    # Generali (scelti nella configurazione iniziale, devtox://setup)
    "language": "",                   # vuoto = lingua del sistema; "it" o "en"
    "search_engine": "duckduckgo",    # duckduckgo | startpage | brave | mojeek | ecosia | google
    "setup_done": False,              # False = al prossimo avvio si apre devtox://setup
    # Privacy
    "persistent_data": True,          # False = profilo effimero, niente su disco
    "disk_cache": True,               # False = nessuna cache su disco
    "block_third_party_cookies": True,
    "send_gpc": True,                 # header Sec-GPC: 1 + navigator.globalPrivacyControl
    "trim_referer": True,             # Referer ridotto a schema://host/
    "https_only": True,               # HTTPS forzato tranne localhost e rete locale
    "https_exceptions": [],           # host per cui hai accettato l'HTTP
    "fingerprint_protection": True,   # canvas/WebGL "sporcati", come Brave
    "fingerprint_off_hosts": [],      # siti con anti-fingerprinting spento
    "shields_down_hosts": [],         # siti con la blocklist spenta
    "history_enabled": True,
    "history_days": 90,               # cronologia più vecchia cancellata all'avvio
    "restore_session": True,          # riapre le tab (caricate solo quando le selezioni)
    "download_dir": "",               # vuoto = cartella Scaricati di sistema
    # Leggerezza
    "cache_model": "document_browser",  # web_browser | document_browser | document_viewer
    "javascript_disabled_hosts": [],
    "suspend_after_minutes": 15,      # 0 = mai
    "web_process_memory_limit_mb": 0,  # 0 = limite automatico di WebKit
    # Strumenti
    "dev_ports": [5173, 3000, 8000, 4321],
    # IA locale
    "ai_enabled": True,               # False = niente pannello IA e niente comandi IA
    "ollama_model": "",               # vuoto = il modello più piccolo installato
    "ollama_keep_alive": "30s",
    "ollama_num_ctx": 4096,
}


class Config:
    def __init__(self, path=None):
        self.path = path or os.path.join(utils.config_dir(), "config.json")
        self._data = copy.deepcopy(DEFAULTS)
        self.first_run = False  # True se config.json non esisteva: si mostra devtox://welcome
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                user = json.load(f)
        except FileNotFoundError:
            self.first_run = True
            self.save()  # primo avvio: scrive i valori predefiniti, da modificare a mano
            return
        except (OSError, ValueError) as e:
            logger.warning("%s non valido, uso i predefiniti: %s", self.path, e)
            return
        if not isinstance(user, dict):
            logger.warning("%s deve contenere un oggetto JSON", self.path)
            return
        for key, value in user.items():
            default = DEFAULTS.get(key)
            if key in DEFAULTS and type(value) is not type(default):
                logger.warning("'%s' ha un tipo non valido, uso %r", key, default)
                continue
            self._data[key] = value

    def __getitem__(self, key):
        return self._data[key]

    def set(self, key, value):
        self._data[key] = value
        self.save()

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, self.path)  # scrittura atomica: mai un file a metà
