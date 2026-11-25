"""SQLite storage: users, sessions, station assignments, audit log, apply history."""
import json
import os
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL DEFAULT '',
    pw_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'editor', 'viewer', 'station')),
    disabled INTEGER NOT NULL DEFAULT 0,
    must_change_pw INTEGER NOT NULL DEFAULT 0,
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until REAL NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    last_login REAL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_seen REAL NOT NULL,
    expires_at REAL NOT NULL,
    ip TEXT,
    user_agent TEXT
);
-- station key = SId hex (stable across renumbering)
CREATE TABLE IF NOT EXISTS user_stations (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    station TEXT NOT NULL,
    PRIMARY KEY (user_id, station)
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    user_id INTEGER,
    username TEXT NOT NULL DEFAULT '',
    ip TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS applies (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    username TEXT NOT NULL DEFAULT '',
    backup TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    log TEXT NOT NULL DEFAULT '[]'
);
"""

_local = threading.local()
_path = None
_lock = threading.RLock()


def init(path):
    global _path
    _path = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = conn()
    c.executescript(SCHEMA)
    c.commit()
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def conn():
    c = getattr(_local, 'c', None)
    if c is None or getattr(_local, 'p', None) != _path:
        c = sqlite3.connect(_path, timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys = ON')
        c.execute('PRAGMA journal_mode = WAL')
        _local.c, _local.p = c, _path
    return c


def q(sql, args=()):
    return [dict(r) for r in conn().execute(sql, args).fetchall()]


def q1(sql, args=()):
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None


def x(sql, args=()):
    with _lock:
        cur = conn().execute(sql, args)
        return cur.lastrowid


def audit(user, ip, action, target='', details=None):
    x('INSERT INTO audit(ts, user_id, username, ip, action, target, details) VALUES (?,?,?,?,?,?,?)',
      (time.time(), user['user_id'] if user else None, user['username'] if user else '', ip or '', action,
       target or '', json.dumps(details or {})))


def meta_get(key, default=None):
    r = q1('SELECT value FROM meta WHERE key = ?', (key,))
    return json.loads(r['value']) if r else default


def meta_set(key, value):
    x('INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
      (key, json.dumps(value)))
