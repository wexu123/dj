# -*- coding: utf-8 -*-
"""SQLite 曲库主表：全流水线只围绕这张表读写（schema 见实现计划 03 节）。"""
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id              TEXT PRIMARY KEY,
    file_path       TEXT NOT NULL,
    duration        REAL,
    bpm             REAL,
    bpm_conf        REAL,
    key             TEXT,
    camelot         TEXT,
    energy          REAL,
    genre_tags      TEXT,
    genre_tags_final TEXT,
    genre_source    TEXT,
    mood_tags       TEXT,
    arousal         REAL,
    valence         REAL,
    mood_tags_final TEXT,
    structure       TEXT,
    cue_points      TEXT,
    audio_emb       TEXT
);
"""

MODULES_SCHEMA = """
CREATE TABLE IF NOT EXISTS modules (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS module_tracks (
    module_id   TEXT NOT NULL,
    track_id    TEXT NOT NULL,
    pos         INTEGER,
    PRIMARY KEY (module_id, track_id)
);
"""

_COLS = ["id", "file_path", "duration", "bpm", "bpm_conf", "key", "camelot",
         "energy", "genre_tags", "genre_tags_final", "genre_source", "mood_tags",
         "arousal", "valence",
         "mood_tags_final", "structure", "cue_points", "audio_emb"]

_JSON_COLS = {"genre_tags", "genre_tags_final", "mood_tags", "mood_tags_final",
              "structure", "cue_points", "audio_emb"}


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.executescript(MODULES_SCHEMA)
    # 旧库迁移：补齐新增列
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(tracks)")}
    for col in _COLS:
        if col not in existing:
            conn.execute("ALTER TABLE tracks ADD COLUMN {} TEXT".format(col))
    conn.commit()
    return conn


def upsert(conn, rec):
    row = {}
    for c in _COLS:
        v = rec.get(c)
        if c in _JSON_COLS and isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        row[c] = v
    conn.execute(
        "INSERT INTO tracks ({cols}) VALUES ({ph}) "
        "ON CONFLICT(id) DO UPDATE SET {upd}".format(
            cols=",".join(_COLS),
            ph=",".join(":" + c for c in _COLS),
            upd=",".join("{0}=excluded.{0}".format(c) for c in _COLS if c != "id"),
        ),
        row,
    )
    conn.commit()


def _row_to_dict(r):
    d = dict(r)
    for c in _JSON_COLS:
        if isinstance(d.get(c), str):
            try:
                d[c] = json.loads(d[c])
            except (ValueError, TypeError):
                pass
    return d


def fetch_all(conn):
    return [_row_to_dict(r) for r in conn.execute("SELECT * FROM tracks ORDER BY id")]


def fetch_one(conn, track_id):
    r = conn.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
    return _row_to_dict(r) if r else None


# ---- 歌曲模块（可复用的排歌素材分组）----

def create_module(conn, name):
    import time
    import uuid
    mid = "mod_" + uuid.uuid4().hex[:8]
    conn.execute("INSERT INTO modules (id, name, created_at) VALUES (?,?,?)",
                 (mid, name, time.strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    return mid


def list_modules(conn):
    out = []
    for m in conn.execute("SELECT * FROM modules ORDER BY created_at"):
        ids = [r[0] for r in conn.execute(
            "SELECT track_id FROM module_tracks WHERE module_id=? ORDER BY pos",
            (m["id"],))]
        out.append({"id": m["id"], "name": m["name"], "track_ids": ids})
    return out


def delete_module(conn, mid):
    conn.execute("DELETE FROM module_tracks WHERE module_id=?", (mid,))
    conn.execute("DELETE FROM modules WHERE id=?", (mid,))
    conn.commit()


def module_add_track(conn, mid, tid):
    pos = conn.execute(
        "SELECT COUNT(*) FROM module_tracks WHERE module_id=?", (mid,)
    ).fetchone()[0]
    conn.execute(
        "INSERT OR IGNORE INTO module_tracks (module_id, track_id, pos) "
        "VALUES (?,?,?)", (mid, tid, pos))
    conn.commit()


def module_remove_track(conn, mid, tid):
    conn.execute("DELETE FROM module_tracks WHERE module_id=? AND track_id=?",
                 (mid, tid))
    conn.commit()
