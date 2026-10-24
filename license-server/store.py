"""SQLite persistence for issued licenses (one file, stdlib only)."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    customer_id TEXT NOT NULL DEFAULT '',
    edition TEXT NOT NULL,
    machine_code TEXT NOT NULL,
    max_cameras INTEGER NOT NULL,
    allowed_algorithms TEXT NOT NULL DEFAULT '[]',
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    license_json TEXT NOT NULL
)
"""


class Store:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with self._conn() as conn:
            conn.execute(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def add(self, license_data, note=''):
        with self._conn() as conn:
            cur = conn.execute(
                'INSERT INTO licenses (created_at, customer_id, edition, machine_code, max_cameras,'
                ' allowed_algorithms, issued_at, expires_at, note, license_json)'
                ' VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    datetime.now().isoformat(sep=' ', timespec='seconds'),
                    license_data['customer_id'],
                    license_data['edition'],
                    license_data['machine_code'],
                    license_data['max_cameras'],
                    json.dumps(license_data['allowed_algorithms'], ensure_ascii=False),
                    license_data['issued_at'],
                    license_data['expires_at'],
                    str(note or '').strip(),
                    json.dumps(license_data, ensure_ascii=False, indent=2),
                ),
            )
            return cur.lastrowid

    def list(self):
        with self._conn() as conn:
            return [_decode(r) for r in conn.execute('SELECT * FROM licenses ORDER BY id DESC')]

    def get(self, license_id):
        with self._conn() as conn:
            row = conn.execute('SELECT * FROM licenses WHERE id = ?', (license_id,)).fetchone()
            return _decode(row) if row else None


def _decode(row):
    item = dict(row)
    item['allowed_algorithms'] = json.loads(item['allowed_algorithms'] or '[]')
    return item
