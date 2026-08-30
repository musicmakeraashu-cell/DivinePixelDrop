import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "wallpapers.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wallpapers (
            filename TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            category TEXT,
            tags TEXT,
            featured INTEGER DEFAULT 0
        )
    """)

    existing_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(wallpapers)").fetchall()
    ]

    if "upload_date" not in existing_columns:
        conn.execute(
            "ALTER TABLE wallpapers ADD COLUMN upload_date TEXT"
        )

    if "downloads" not in existing_columns:
        conn.execute(
            "ALTER TABLE wallpapers ADD COLUMN downloads INTEGER DEFAULT 0"
        )

    conn.commit()
    conn.close()


def get_metadata(filename):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM wallpapers WHERE filename = ?",
        (filename,)
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "filename": filename,
        "title": filename,
        "description": "",
        "category": "Uncategorized",
        "tags": "",
        "featured": 0,
        "upload_date": None,
        "downloads": 0
    }


def get_all_metadata():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM wallpapers").fetchall()
    conn.close()
    return {row["filename"]: dict(row) for row in rows}


def save_metadata(filename, title, description, category, tags, featured):
    conn = get_connection()

    existing = conn.execute(
        "SELECT upload_date FROM wallpapers WHERE filename = ?",
        (filename,)
    ).fetchone()

    if existing and existing["upload_date"]:
        upload_date = existing["upload_date"]
    else:
        upload_date = datetime.datetime.now().isoformat()

    conn.execute("""
        INSERT INTO wallpapers (filename, title, description, category, tags, featured, upload_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(filename) DO UPDATE SET
            title=excluded.title,
            description=excluded.description,
            category=excluded.category,
            tags=excluded.tags,
            featured=excluded.featured,
            upload_date=excluded.upload_date
    """, (filename, title, description, category, tags, featured, upload_date))
    conn.commit()
    conn.close()


def increment_downloads(filename):
    conn = get_connection()
    conn.execute("""
        UPDATE wallpapers
        SET downloads = COALESCE(downloads, 0) + 1
        WHERE filename = ?
    """, (filename,))
    conn.commit()
    conn.close()


def delete_metadata(filename):
    conn = get_connection()
    conn.execute("DELETE FROM wallpapers WHERE filename = ?", (filename,))
    conn.commit()
    conn.close()