import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

DB_FILE = "accounts.db"
BEIJING_TZ = timezone(timedelta(hours=8))


def _beijing_now_str() -> str:
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")


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
                mail_address TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(openai_register_accounts)").fetchall()
        }
        if "mail_address" not in columns:
            conn.execute(
                "ALTER TABLE openai_register_accounts ADD COLUMN mail_address TEXT NOT NULL DEFAULT ''"
            )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_openai_register_accounts_updated_at
            AFTER UPDATE ON openai_register_accounts
            FOR EACH ROW
            BEGIN
                UPDATE openai_register_accounts
                SET updated_at = datetime('now', '+8 hours')
                WHERE id = OLD.id;
            END;
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS disabled_email_suffixes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_type TEXT NOT NULL,
                email_suffix TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        disabled_email_suffix_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(disabled_email_suffixes)").fetchall()
        }
        if "subscription_type" not in disabled_email_suffix_columns:
            conn.execute(
                "ALTER TABLE disabled_email_suffixes ADD COLUMN subscription_type TEXT NOT NULL DEFAULT ''"
            )
        if "email_suffix" not in disabled_email_suffix_columns:
            conn.execute(
                "ALTER TABLE disabled_email_suffixes ADD COLUMN email_suffix TEXT NOT NULL DEFAULT ''"
            )
        if "enabled" not in disabled_email_suffix_columns:
            conn.execute(
                "ALTER TABLE disabled_email_suffixes ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1"
            )
        if "created_at" not in disabled_email_suffix_columns:
            conn.execute(
                "ALTER TABLE disabled_email_suffixes ADD COLUMN created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )
        if "updated_at" not in disabled_email_suffix_columns:
            conn.execute(
                "ALTER TABLE disabled_email_suffixes ADD COLUMN updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_disabled_email_suffixes_subscription_suffix
            ON disabled_email_suffixes (subscription_type, email_suffix)
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_disabled_email_suffixes_updated_at
            AFTER UPDATE ON disabled_email_suffixes
            FOR EACH ROW
            BEGIN
                UPDATE disabled_email_suffixes
                SET updated_at = datetime('now', '+8 hours')
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
    mail_address: str = "",
    db_path: str = DB_FILE,
) -> None:
    now_str = _beijing_now_str()
    with _get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO openai_register_accounts (
                email,
                password,
                registered_at,
                token,
                refresh_token,
                expired,
                mail_address,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                password = excluded.password,
                registered_at = excluded.registered_at,
                token = excluded.token,
                refresh_token = excluded.refresh_token,
                expired = excluded.expired,
                mail_address = excluded.mail_address,
                updated_at = excluded.updated_at
            """,
            (
                email,
                password,
                registered_at,
                token,
                refresh_token,
                expired,
                mail_address,
                now_str,
                now_str,
            ),
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



def extract_email_suffix(email: str) -> str:
    email_text = str(email or "").strip().lower()
    if "@" not in email_text:
        return ""
    return "@" + email_text.rsplit("@", 1)[1]



def is_email_suffix_disabled(
    subscription_type: str,
    email_suffix: str,
    db_path: str = DB_FILE,
) -> bool:
    normalized_subscription_type = str(subscription_type or "").strip()
    normalized_suffix = extract_email_suffix(email_suffix)
    if not normalized_subscription_type or not normalized_suffix:
        return False

    row = get_disabled_email_suffix(
        normalized_subscription_type,
        normalized_suffix,
        db_path=db_path,
    )
    return bool(row and int(row.get("enabled") or 0) == 1)



def upsert_disabled_email_suffix(
    *,
    subscription_type: str,
    email_suffix: str,
    enabled: bool = True,
    db_path: str = DB_FILE,
) -> None:
    now_str = _beijing_now_str()
    with _get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO disabled_email_suffixes (
                subscription_type,
                email_suffix,
                enabled,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(subscription_type, email_suffix) DO UPDATE SET
                enabled = excluded.enabled,
                updated_at = excluded.updated_at
            """,
            (
                subscription_type.strip(),
                email_suffix.strip(),
                1 if enabled else 0,
                now_str,
                now_str,
            ),
        )
        conn.commit()


def delete_disabled_email_suffix(
    subscription_type: str,
    email_suffix: str,
    db_path: str = DB_FILE,
) -> int:
    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            DELETE FROM disabled_email_suffixes
            WHERE subscription_type = ? AND email_suffix = ?
            """,
            (subscription_type.strip(), email_suffix.strip()),
        )
        conn.commit()
        return int(cursor.rowcount or 0)


def get_disabled_email_suffix(
    subscription_type: str,
    email_suffix: str,
    db_path: str = DB_FILE,
) -> Optional[Dict[str, Any]]:
    with _get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM disabled_email_suffixes
            WHERE subscription_type = ? AND email_suffix = ?
            """,
            (subscription_type.strip(), email_suffix.strip()),
        ).fetchone()
    return dict(row) if row else None


def list_disabled_email_suffixes(
    subscription_type: Optional[str] = None,
    enabled: Optional[bool] = None,
    db_path: str = DB_FILE,
) -> List[Dict[str, Any]]:
    query = "SELECT * FROM disabled_email_suffixes"
    clauses = []
    params = []

    if subscription_type is not None:
        clauses.append("subscription_type = ?")
        params.append(subscription_type.strip())
    if enabled is not None:
        clauses.append("enabled = ?")
        params.append(1 if enabled else 0)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY subscription_type ASC, email_suffix ASC"

    with _get_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def set_disabled_email_suffix_enabled(
    subscription_type: str,
    email_suffix: str,
    enabled: bool,
    db_path: str = DB_FILE,
) -> int:
    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE disabled_email_suffixes
            SET enabled = ?
            WHERE subscription_type = ? AND email_suffix = ?
            """,
            (1 if enabled else 0, subscription_type.strip(), email_suffix.strip()),
        )
        conn.commit()
        return int(cursor.rowcount or 0)
