import sqlite3
from pathlib import Path


def initialize_database(database_path: str) -> None:
    """Create the database and its tables if they do not exist yet."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS client_messages (
                admin_chat_id INTEGER NOT NULL,
                admin_message_id INTEGER NOT NULL,
                admin_thread_id INTEGER,
                client_chat_id INTEGER NOT NULL,
                client_user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (admin_chat_id, admin_message_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS support_threads (
                client_user_id INTEGER PRIMARY KEY,
                client_chat_id INTEGER NOT NULL,
                admin_chat_id INTEGER NOT NULL,
                admin_thread_id INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                username TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (admin_chat_id, admin_thread_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_user_id INTEGER NOT NULL,
                direction TEXT NOT NULL
                    CHECK (direction IN ('client_to_admin', 'admin_to_client')),
                content_type TEXT NOT NULL
                    CHECK (content_type IN ('text', 'photo')),
                text TEXT,
                file_id TEXT,
                source_message_id INTEGER NOT NULL,
                destination_message_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_user_id)
                    REFERENCES support_threads (client_user_id)
            )
            """
        )


def save_client_message(
    database_path: str,
    *,
    admin_chat_id: int,
    admin_message_id: int,
    admin_thread_id: int | None,
    client_chat_id: int,
    client_user_id: int,
) -> None:
    """Save a link between an admin message and the client who sent it."""
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO client_messages (
                admin_chat_id,
                admin_message_id,
                admin_thread_id,
                client_chat_id,
                client_user_id
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                admin_chat_id,
                admin_message_id,
                admin_thread_id,
                client_chat_id,
                client_user_id,
            ),
        )


def find_client_chat_id(
    database_path: str,
    *,
    admin_chat_id: int,
    admin_message_id: int,
) -> int | None:
    """Return the client chat linked to an admin message."""
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT client_chat_id
            FROM client_messages
            WHERE admin_chat_id = ? AND admin_message_id = ?
            """,
            (admin_chat_id, admin_message_id),
        ).fetchone()

    return row[0] if row else None


def save_support_thread(
    database_path: str,
    *,
    client_user_id: int,
    client_chat_id: int,
    admin_chat_id: int,
    admin_thread_id: int,
    full_name: str,
    username: str | None,
) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO support_threads (
                client_user_id,
                client_chat_id,
                admin_chat_id,
                admin_thread_id,
                full_name,
                username
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(client_user_id) DO UPDATE SET
                client_chat_id = excluded.client_chat_id,
                admin_chat_id = excluded.admin_chat_id,
                admin_thread_id = excluded.admin_thread_id,
                full_name = excluded.full_name,
                username = excluded.username,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                client_user_id,
                client_chat_id,
                admin_chat_id,
                admin_thread_id,
                full_name,
                username,
            ),
        )


def get_support_thread_by_user(
    database_path: str,
    client_user_id: int,
) -> dict | None:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT *
            FROM support_threads
            WHERE client_user_id = ?
            """,
            (client_user_id,),
        ).fetchone()

    return dict(row) if row else None


def get_support_thread_by_admin_topic(
    database_path: str,
    *,
    admin_chat_id: int,
    admin_thread_id: int,
) -> dict | None:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT *
            FROM support_threads
            WHERE admin_chat_id = ? AND admin_thread_id = ?
            """,
            (admin_chat_id, admin_thread_id),
        ).fetchone()

    return dict(row) if row else None


def delete_support_thread(database_path: str, client_user_id: int) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            DELETE FROM support_threads
            WHERE client_user_id = ?
            """,
            (client_user_id,),
        )


def save_support_message(
    database_path: str,
    *,
    client_user_id: int,
    direction: str,
    content_type: str,
    text: str | None,
    file_id: str | None,
    source_message_id: int,
    destination_message_id: int,
) -> None:
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO support_messages (
                client_user_id,
                direction,
                content_type,
                text,
                file_id,
                source_message_id,
                destination_message_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                client_user_id,
                direction,
                content_type,
                text,
                file_id,
                source_message_id,
                destination_message_id,
            ),
        )
