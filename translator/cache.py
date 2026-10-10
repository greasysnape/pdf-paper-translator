"""SQLite-backed translation cache."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path


def default_cache_dir() -> Path:
    env = os.environ.get("PDFTRANS_CACHE_DIR")
    if env:
        return Path(env)
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "pdf-paper-translator"


class TranslationCache:
    def __init__(self, path: str | Path | None = None, enabled: bool = True) -> None:
        self.enabled = enabled
        self.conn: sqlite3.Connection | None = None
        if not enabled:
            return
        path = Path(path) if path else default_cache_dir() / "cache.sqlite3"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS translations (
                   key TEXT PRIMARY KEY,
                   engine TEXT NOT NULL,
                   model TEXT NOT NULL,
                   src_lang TEXT NOT NULL,
                   tgt_lang TEXT NOT NULL,
                   source TEXT NOT NULL,
                   target TEXT NOT NULL,
                   created_at TEXT DEFAULT CURRENT_TIMESTAMP
               )"""
        )
        self.conn.commit()

    @staticmethod
    def make_key(engine: str, model: str, src: str, tgt: str, text: str) -> str:
        h = hashlib.sha256()
        for part in (engine, model, src, tgt, text):
            h.update(part.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()

    def get(self, key: str) -> str | None:
        if not self.conn:
            return None
        row = self.conn.execute("SELECT target FROM translations WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key: str, engine: str, model: str, src: str, tgt: str, source: str, target: str) -> None:
        if not self.conn:
            return
        self.conn.execute(
            "INSERT OR REPLACE INTO translations (key, engine, model, src_lang, tgt_lang, source, target) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key, engine, model, src, tgt, source, target),
        )
        self.conn.commit()

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None
