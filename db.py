"""SQLite helpers. The database is a single file, eshop.db, next to this script."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = ROOT / "eshop.db"
Error = sqlite3.Error


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = lambda cur, row: {c[0]: v for c, v in zip(cur.description, row)}
    con.execute("PRAGMA foreign_keys = ON")
    return con


@contextmanager
def cursor(commit: bool = False):
    """Yield a cursor whose rows are dicts; commit on success if asked, always close."""
    con = connect()
    cur = con.cursor()
    try:
        yield cur
        if commit:
            con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def query(sql: str, params: tuple = ()) -> list[dict]:
    with cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def execute(sql: str, params: tuple = ()) -> int:
    """Run a write statement; return the affected row count."""
    with cursor(commit=True) as cur:
        cur.execute(sql, params)
        return cur.rowcount


def init_db() -> None:
    """(Re)create all tables and load the seed data."""
    con = sqlite3.connect(DB_PATH)
    for name in ("schema.sql", "seed.sql"):
        con.executescript((ROOT / "sql" / name).read_text())
    con.commit()
    con.close()


if __name__ == "__main__":
    init_db()
    print(f"Created {DB_PATH.name}")
