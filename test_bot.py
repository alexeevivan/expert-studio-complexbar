import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram.ext import ConversationHandler

import bot


class PostAccessTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_post_command_shows_topic_selector(self):
        chat_id = -1001234567890
        user_id = 111111111
        original_chat_id = bot.ADMIN_CHAT_ID
        original_admin_ids = bot.ADMIN_IDS
        original_topics = bot.TOPICS
        bot.ADMIN_CHAT_ID = chat_id
        bot.ADMIN_IDS = {user_id}
        bot.TOPICS = {"events": None, "journal": 55}

        message = SimpleNamespace(
            reply_text=AsyncMock(
                return_value=SimpleNamespace(message_id=20)
            ),
        )
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=user_id),
        )
        context = SimpleNamespace(
            user_data={},
            bot=SimpleNamespace(
                get_chat_member=AsyncMock(
                    return_value=SimpleNamespace(status="administrator")
                ),
                delete_message=AsyncMock(),
            ),
        )

        try:
            result = await bot.start_post(update, context)
        finally:
            bot.ADMIN_CHAT_ID = original_chat_id
            bot.ADMIN_IDS = original_admin_ids
            bot.TOPICS = original_topics

        self.assertEqual(result, bot.SELECTING_POST_TOPIC)
        message.reply_text.assert_awaited_once()
        self.assertEqual(
            context.user_data["post_draft"]["selector_message_id"],
            20,
        )

    async def test_topic_selection_targets_configured_thread(self):
        original_chat_id = bot.ADMIN_CHAT_ID
        original_topics = bot.TOPICS
        bot.ADMIN_CHAT_ID = -1001234567890
        bot.TOPICS = {"events": None, "journal": 55}

        query = SimpleNamespace(
            data="post_topic:journal",
            message=SimpleNamespace(message_id=20),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(callback_query=query)
        context = SimpleNamespace(
            user_data={"post_draft": {"selector_message_id": 20}}
        )

        try:
            result = await bot.select_post_topic(update, context)
        finally:
            bot.ADMIN_CHAT_ID = original_chat_id
            bot.TOPICS = original_topics

        self.assertEqual(result, bot.WAITING_POST_CONTENT)
        self.assertEqual(
            context.user_data["post_draft"]["target_thread_id"],
            55,
        )
        query.edit_message_text.assert_awaited_once()

    async def test_confirm_publishes_private_preview_to_target_topic(self):
        user_id = 111111111
        target_chat_id = -1001234567890
        query = SimpleNamespace(
            data=f"post_publish:{user_id}",
            answer=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            delete_message=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=user_id),
        )
        context = SimpleNamespace(
            user_data={
                "post_draft": {
                    "target_chat_id": target_chat_id,
                    "target_thread_id": 55,
                    "content_type": "text",
                    "text": "<b>Правила</b>",
                    "file_id": None,
                }
            },
            bot=SimpleNamespace(send_message=AsyncMock()),
        )

        result = await bot.confirm_post(update, context)

        self.assertEqual(result, ConversationHandler.END)
        context.bot.send_message.assert_awaited_once_with(
            chat_id=target_chat_id,
            message_thread_id=55,
            text="<b>Правила</b>",
            parse_mode="HTML",
        )
        query.edit_message_reply_markup.assert_awaited_once_with(
            reply_markup=None
        )

    async def test_support_start_sends_welcome_image(self):
        message = SimpleNamespace(
            reply_photo=AsyncMock(),
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(message=message)
        context = SimpleNamespace(args=["support"])

        await bot.start(update, context)

        message.reply_photo.assert_awaited_once()
        self.assertEqual(
            message.reply_photo.await_args.kwargs["photo"],
            bot.SUPPORT_WELCOME_IMAGE,
        )
        message.reply_text.assert_not_awaited()

    async def test_setup_contact_pins_support_button(self):
        chat_id = -1001234567890
        user_id = 111111111
        original_chat_id = bot.ADMIN_CHAT_ID
        original_admin_ids = bot.ADMIN_IDS
        bot.ADMIN_CHAT_ID = chat_id
        bot.ADMIN_IDS = {user_id}

        message = SimpleNamespace(
            chat_id=chat_id,
            message_thread_id=55,
            message_id=10,
        )
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=user_id),
        )
        context = SimpleNamespace(
            bot=SimpleNamespace(
                get_me=AsyncMock(
                    return_value=SimpleNamespace(username="complexbar_bot")
                ),
                send_message=AsyncMock(
                    return_value=SimpleNamespace(message_id=20)
                ),
                pin_chat_message=AsyncMock(),
                delete_message=AsyncMock(),
            )
        )

        try:
            await bot.setup_contact(update, context)
        finally:
            bot.ADMIN_CHAT_ID = original_chat_id
            bot.ADMIN_IDS = original_admin_ids

        context.bot.pin_chat_message.assert_awaited_once_with(
            chat_id=chat_id,
            message_id=20,
            disable_notification=True,
        )

    async def test_unlisted_user_is_denied_in_private_chat(self):
        chat_id = -1001234567890
        user_id = 222222222
        original_chat_id = bot.ADMIN_CHAT_ID
        original_admin_ids = bot.ADMIN_IDS
        bot.ADMIN_CHAT_ID = chat_id
        bot.ADMIN_IDS = {111111111}

        message = SimpleNamespace(
            reply_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_message=message,
            effective_user=SimpleNamespace(id=user_id),
        )
        context = SimpleNamespace()

        try:
            result = await bot.start_post(update, context)
        finally:
            bot.ADMIN_CHAT_ID = original_chat_id
            bot.ADMIN_IDS = original_admin_ids

        self.assertEqual(result, ConversationHandler.END)
        message.reply_text.assert_awaited_once_with(
            "У вас нет доступа к публикации сообщений."
        )


if __name__ == "__main__":
    unittest.main()
