"""Dati locali: cronologia, preferiti e sessione. Solo su questo PC, mai inviati.

Cronologia e preferiti stanno in un file SQLite nel profilo; la sessione
(le tab aperte) in un JSON. Le tab private non passano mai da qui.
"""

import json
import os
import sqlite3
import time

from . import legacy, utils

HISTORY_SUGGESTIONS = 8


class Storage:
    def __init__(self, path=None):
        path = path or os.path.join(utils.data_dir(), "devtox.sqlite")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS history (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                visits INTEGER NOT NULL DEFAULT 1,
                last_visit REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bookmarks (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                created REAL NOT NULL
            );
        """)
        self.session_path = os.path.join(os.path.dirname(path), "session.json")

    def close(self):
        self.db.close()

    # --- Cronologia -----------------------------------------------------

    def record_visit(self, url, title):
        with self.db:
            self.db.execute(
                """INSERT INTO history (url, title, visits, last_visit) VALUES (?, ?, 1, ?)
                   ON CONFLICT(url) DO UPDATE SET
                       title = CASE WHEN excluded.title != '' THEN excluded.title ELSE title END,
                       visits = visits + 1,
                       last_visit = excluded.last_visit""",
                (url, title or "", time.time()),
            )

    def update_title(self, url, title):
        if title:
            with self.db:
                self.db.execute("UPDATE history SET title = ? WHERE url = ?", (title, url))

    def search_history(self, text, limit=HISTORY_SUGGESTIONS):
        """Pagine che contengono il testo nell'URL o nel titolo, le più visitate prima."""
        pattern = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        rows = self.db.execute(
            """SELECT url, title FROM history
               WHERE url LIKE ? ESCAPE '\\' OR title LIKE ? ESCAPE '\\'
               ORDER BY visits DESC, last_visit DESC LIMIT ?""",
            (pattern, pattern, limit),
        )
        return rows.fetchall()

    def recent(self, limit=6):
        """Ultime pagine web visitate: (url, titolo, ultimo accesso), le più recenti prima."""
        rows = self.db.execute(
            """SELECT url, title, last_visit FROM history
               WHERE url LIKE 'http://%' OR url LIKE 'https://%'
               ORDER BY last_visit DESC LIMIT ?""",
            (limit,),
        )
        return rows.fetchall()

    def import_history(self, rows):
        """Unisce la cronologia di un altro browser: [(url, titolo, visite, ultimo accesso)].

        Importare due volte non raddoppia le visite: si tiene il valore più alto.
        Restituisce quante pagine erano nuove.
        """
        known = {url for (url,) in self.db.execute("SELECT url FROM history")}
        with self.db:
            self.db.executemany(
                """INSERT INTO history (url, title, visits, last_visit) VALUES (?, ?, ?, ?)
                   ON CONFLICT(url) DO UPDATE SET
                       title = CASE WHEN title = '' THEN excluded.title ELSE title END,
                       visits = MAX(visits, excluded.visits),
                       last_visit = MAX(last_visit, excluded.last_visit)""",
                [(url, title or "", max(1, int(visits)), float(seen)) for url, title, visits, seen in rows],
            )
        return sum(1 for url, *_rest in rows if url not in known)

    def expire_history(self, days):
        if days > 0:
            with self.db:
                self.db.execute("DELETE FROM history WHERE last_visit < ?", (time.time() - days * 86400,))

    def clear_history(self):
        with self.db:
            self.db.execute("DELETE FROM history")

    # --- Preferiti ------------------------------------------------------

    def is_bookmarked(self, url):
        return self.db.execute("SELECT 1 FROM bookmarks WHERE url = ?", (url,)).fetchone() is not None

    def toggle_bookmark(self, url, title):
        """Aggiunge o toglie il preferito; restituisce True se ora è salvato."""
        with self.db:
            if self.is_bookmarked(url):
                self.db.execute("DELETE FROM bookmarks WHERE url = ?", (url,))
                return False
            self.db.execute(
                "INSERT INTO bookmarks (url, title, created) VALUES (?, ?, ?)",
                (url, title or url, time.time()),
            )
            return True

    def import_bookmarks(self, rows):
        """Aggiunge i preferiti che mancano; restituisce quanti sono nuovi. L'ordine resta quello d'origine."""
        added = 0
        base = time.time()
        with self.db:
            for index, (url, title) in enumerate(rows):
                cursor = self.db.execute(
                    "INSERT OR IGNORE INTO bookmarks (url, title, created) VALUES (?, ?, ?)",
                    (url, title or url, base - index * 0.001),  # i primi restano in cima
                )
                added += cursor.rowcount
        return added

    def bookmarks(self):
        return self.db.execute("SELECT url, title FROM bookmarks ORDER BY created DESC").fetchall()

    # --- Sessione -------------------------------------------------------

    def save_session(self, tabs):
        """tabs: [{"uri", "title", "current"}] delle sole tab non private."""
        tmp = self.session_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(tabs, f, ensure_ascii=False)
        os.replace(tmp, self.session_path)

    def load_session(self):
        try:
            with open(self.session_path, encoding="utf-8") as f:
                tabs = json.load(f)
        except (OSError, ValueError):
            return []
        tabs = [t for t in tabs if isinstance(t, dict) and isinstance(t.get("uri"), str)]
        for tab in tabs:
            tab["uri"] = legacy.session_uri(tab["uri"])
        return tabs
