import tempfile
import unittest
from pathlib import Path

from database import (
    get_support_thread_by_admin_topic,
    get_support_thread_by_user,
    initialize_database,
    save_support_message,
    save_support_thread,
)


class SupportDatabaseTests(unittest.TestCase):
    def test_support_thread_and_message_are_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = str(Path(directory) / "support.db")
            initialize_database(database_path)

            save_support_thread(
                database_path,
                client_user_id=10,
                client_chat_id=10,
                admin_chat_id=-1001,
                admin_thread_id=77,
                full_name="Test User",
                username="testuser",
            )

            by_user = get_support_thread_by_user(database_path, 10)
            by_topic = get_support_thread_by_admin_topic(
                database_path,
                admin_chat_id=-1001,
                admin_thread_id=77,
            )
            self.assertEqual(by_user["admin_thread_id"], 77)
            self.assertEqual(by_topic["client_chat_id"], 10)

            save_support_message(
                database_path,
                client_user_id=10,
                direction="client_to_admin",
                content_type="text",
                text="Hello",
                file_id=None,
                source_message_id=1,
                destination_message_id=2,
            )


if __name__ == "__main__":
    unittest.main()
