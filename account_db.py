import sqlite3
from typing import Any, Dict, Optional

DB_FILE = "accounts.db"


def _get_connection(db_path: str = DB_FILE) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_account_db(db_path: str = DB_FILE) -> None:
    with _get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS openai_register_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                registered_at TEXT NOT NULL,
                token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expired TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_openai_register_accounts_updated_at
            AFTER UPDATE ON openai_register_accounts
            FOR EACH ROW
            BEGIN
                UPDATE openai_register_accounts
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = OLD.id;
            END;
            """
        )
        conn.commit()


def upsert_account_record(
    *,
    email: str,
    password: str,
    registered_at: str,
    token: str,
    refresh_token: str,
    expired: str,
    db_path: str = DB_FILE,
) -> None:
    with _get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO openai_register_accounts (
                email,
                password,
                registered_at,
                token,
                refresh_token,
                expired
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                password = excluded.password,
                registered_at = excluded.registered_at,
                token = excluded.token,
                refresh_token = excluded.refresh_token,
                expired = excluded.expired,
                updated_at = CURRENT_TIMESTAMP
            """,
            (email, password, registered_at, token, refresh_token, expired),
        )
        conn.commit()


def delete_account_by_email(email: str, db_path: str = DB_FILE) -> int:
    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM openai_register_accounts WHERE email = ?",
            (email,),
        )
        conn.commit()
        return int(cursor.rowcount or 0)


def get_account_by_email(email: str, db_path: str = DB_FILE) -> Optional[Dict[str, Any]]:
    with _get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM openai_register_accounts WHERE email = ?",
            (email,),
        ).fetchone()
    return dict(row) if row else None
