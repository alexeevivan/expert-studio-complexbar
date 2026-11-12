import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from database import (
    get_support_thread_by_admin_topic,
    get_support_thread_by_user,
    initialize_database,
    save_support_message,
    save_support_thread,
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID_VALUE = os.getenv("ADMIN_CHAT_ID")
ADMIN_IDS_VALUE = os.getenv("ADMIN_IDS")
SUPPORT_CHAT_ID_VALUE = os.getenv("SUPPORT_CHAT_ID")
DATABASE_PATH = os.getenv("DATABASE_PATH", "complexbar.db")
SUPPORT_WELCOME_IMAGE = (
    Path(__file__).resolve().parent / "content" / "es-cb-support.jpg"
)
ADMIN_CHAT_ID: int | None = None
SUPPORT_CHAT_ID: int | None = None
ADMIN_IDS: set[int] = set()

SELECTING_POST_TOPIC, WAITING_POST_CONTENT, WAITING_POST_CONFIRMATION = range(3)

TOPIC_CONFIG = {
    "journal": ("Journal", "TOPIC_JOURNAL"),
    "library": ("Library", "TOPIC_LIBRARY"),
    "vacancies": ("Vacancies", "TOPIC_JOBOFFERS"),
    "contact": ("Contact us", "TOPIC_CONTACT"),
    "rules": ("Manifesto", "TOPIC_MANIFESTO"),
}
TOPICS: dict[str, int | None] = {}


def load_topics() -> dict[str, int | None]:
    topics: dict[str, int | None] = {"events": None}
    for key, (_, environment_name) in TOPIC_CONFIG.items():
        value = os.getenv(environment_name)
        if not value:
            raise RuntimeError(f"{environment_name} not found in .env")
        try:
            topics[key] = int(value)
        except ValueError as error:
            raise RuntimeError(
                f"{environment_name} must be an integer"
            ) from error
    return topics


def topic_label(topic_key: str) -> str:
    if topic_key == "events":
        return "Events"
    return TOPIC_CONFIG[topic_key][0]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0] == "support":
        support_text = (
            "Вы открыли чат поддержки ComplexBar.\n\n"
            "Напишите Ваш вопрос или отправьте фотографию. "
            "Ответ администратора придёт сюда."
        )
        if SUPPORT_WELCOME_IMAGE.is_file():
            await update.message.reply_photo(
                photo=SUPPORT_WELCOME_IMAGE,
                caption=support_text,
            )
        else:
            await update.message.reply_text(support_text)
        return

    await update.message.reply_text(
        "Добро пожаловать в ComplexBar!\n\n"
        "Напишите Ваш вопрос, и команда ComplexBar ответит вам."
    )


async def setup_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Place a private-support button in the current public topic."""
    message = update.effective_message
    user = update.effective_user

    if message is None or user is None:
        return

    if message.chat_id != ADMIN_CHAT_ID or user.id not in ADMIN_IDS:
        await reject_post_privately(
            context,
            message,
            user,
            "У вас нет доступа к настройке Contact us.",
        )
        return

    bot_user = await context.bot.get_me()
    support_url = f"https://t.me/{bot_user.username}?start=support"
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("💬 Написать в поддержку", url=support_url)]]
    )

    contact_message = await context.bot.send_message(
        chat_id=message.chat_id,
        message_thread_id=message.message_thread_id,
        text=(
            "Нужна помощь или хотите задать вопрос?\n\n"
            "Нажмите кнопку ниже. Общение с командой ComplexBar "
            "будет проходить в личном чате."
        ),
        reply_markup=keyboard,
    )
    await context.bot.pin_chat_message(
        chat_id=message.chat_id,
        message_id=contact_message.message_id,
        disable_notification=True,
    )
    await delete_messages_safely(
        context,
        message.chat_id,
        message.message_id,
    )


async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Chat ID: {update.effective_chat.id}"
    )


async def delete_messages_safely(context, chat_id: int, *message_ids) -> None:
    """Delete messages when permitted, without affecting the post workflow."""
    for message_id in message_ids:
        if message_id is None:
            continue
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=message_id,
            )
        except (BadRequest, Forbidden):
            pass


async def reject_post_privately(context, message, user, text: str) -> None:
    """Remove a rejected command and notify its author outside the group."""
    await delete_messages_safely(
        context,
        message.chat_id,
        message.message_id,
    )

    try:
        await context.bot.send_message(
            chat_id=user.id,
            text=text,
        )
    except (BadRequest, Forbidden):
        # Bots cannot initiate a private chat. If the user has never opened
        # the bot, keep the rejection silent instead of exposing it publicly.
        pass


async def start_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start composing an HTML post in a private chat."""
    message = update.effective_message
    user = update.effective_user

    if message is None or user is None:
        return ConversationHandler.END

    if user.id not in ADMIN_IDS:
        await message.reply_text(
            "У вас нет доступа к публикации сообщений."
        )
        return ConversationHandler.END

    member = await context.bot.get_chat_member(ADMIN_CHAT_ID, user.id)
    if member.status not in {"administrator", "creator"}:
        await message.reply_text(
            "Публиковать сообщения могут только администраторы группы."
        )
        return ConversationHandler.END

    previous_draft = context.user_data.pop("post_draft", None)
    if previous_draft:
        await delete_messages_safely(
            context,
            user.id,
            previous_draft.get("preview_message_id"),
            previous_draft.get("prompt_message_id"),
            previous_draft.get("selector_message_id"),
        )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    topic_label(topic_key),
                    callback_data=f"post_topic:{topic_key}",
                )
            ]
            for topic_key in TOPICS
        ]
    )
    selector = await message.reply_text(
        "В какой топик опубликовать сообщение?",
        reply_markup=keyboard,
    )
    context.user_data["post_draft"] = {
        "selector_message_id": selector.message_id,
    }
    return SELECTING_POST_TOPIC


async def select_post_topic(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query
    post_draft = context.user_data.get("post_draft")
    if query is None or post_draft is None:
        return ConversationHandler.END

    topic_key = query.data.split(":", maxsplit=1)[1]
    if topic_key not in TOPICS:
        await query.answer("Неизвестный топик", show_alert=True)
        return SELECTING_POST_TOPIC

    post_draft["target_chat_id"] = ADMIN_CHAT_ID
    post_draft["target_thread_id"] = TOPICS[topic_key]
    post_draft["topic_key"] = topic_key
    post_draft["prompt_message_id"] = query.message.message_id

    await query.answer()
    await query.edit_message_text(
        text=(
            f"Выбран топик: {topic_label(topic_key)}\n\n"
            "Пришлите текст с HTML-разметкой или одну фотографию "
            "с подписью.\n\nДля выхода используйте /cancel."
        )
    )
    return WAITING_POST_CONTENT

async def topic_id(update: Update, context: ContextTypes.DEFAULT_TYPE):

    message = update.effective_message
    await message.reply_text(
        f"📍 <b>Информация о топике</b>\n\n"
        f"Chat ID: <code>{update.effective_chat.id}</code>\n"
        f"Topic ID: <code>{message.message_thread_id}</code>",
        parse_mode="HTML"
    )

async def receive_post_content(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Render an HTML preview and ask the author for confirmation."""
    message = update.effective_message
    user = update.effective_user
    post_draft = context.user_data.get("post_draft")

    if message is None or user is None or post_draft is None:
        return ConversationHandler.END

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Опубликовать",
                    callback_data=f"post_publish:{user.id}",
                ),
                InlineKeyboardButton(
                    "❌ Отменить",
                    callback_data=f"post_cancel:{user.id}",
                ),
            ]
        ]
    )

    try:
        if message.photo:
            preview = await context.bot.send_photo(
                chat_id=message.chat_id,
                photo=message.photo[-1].file_id,
                caption=message.caption or None,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        else:
            preview = await context.bot.send_message(
                chat_id=message.chat_id,
                text=message.text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
    except BadRequest as error:
        await message.reply_text(
            "Не удалось создать предпросмотр. Проверьте HTML-разметку "
            f"и длину текста.\n\nОшибка Telegram: {error}"
        )
        return WAITING_POST_CONTENT

    post_draft["preview_message_id"] = preview.message_id
    post_draft["content_type"] = "photo" if message.photo else "text"
    post_draft["text"] = message.caption if message.photo else message.text
    post_draft["file_id"] = (
        message.photo[-1].file_id if message.photo else None
    )

    # После создания предпросмотра исходный текст с HTML больше не нужен.
    await delete_messages_safely(
        context,
        message.chat_id,
        message.message_id,
        post_draft["prompt_message_id"],
    )

    return WAITING_POST_CONFIRMATION


async def confirm_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Publish the preview as-is or remove it when the author cancels."""
    query = update.callback_query
    user = update.effective_user

    if query is None or user is None:
        return ConversationHandler.END

    action, owner_id = query.data.split(":", maxsplit=1)
    if user.id != int(owner_id):
        await query.answer(
            "Подтвердить этот пост может только его автор.",
            show_alert=True,
        )
        return WAITING_POST_CONFIRMATION

    if action == "post_publish":
        post_draft = context.user_data.get("post_draft")
        if post_draft is None:
            await query.answer("Черновик больше не найден", show_alert=True)
            return ConversationHandler.END

        try:
            if post_draft["content_type"] == "photo":
                await context.bot.send_photo(
                    chat_id=post_draft["target_chat_id"],
                    message_thread_id=post_draft["target_thread_id"],
                    photo=post_draft["file_id"],
                    caption=post_draft["text"] or None,
                    parse_mode="HTML",
                )
            else:
                await context.bot.send_message(
                    chat_id=post_draft["target_chat_id"],
                    message_thread_id=post_draft["target_thread_id"],
                    text=post_draft["text"],
                    parse_mode="HTML",
                )
        except BadRequest as error:
            await query.answer(
                "Не удалось опубликовать сообщение",
                show_alert=True,
            )
            await context.bot.send_message(
                chat_id=user.id,
                text=f"Ошибка Telegram: {error}",
            )
            return WAITING_POST_CONFIRMATION

        await query.edit_message_reply_markup(reply_markup=None)
        await query.answer("Сообщение опубликовано")
    else:
        await query.answer("Публикация отменена")
        await query.delete_message()

    context.user_data.pop("post_draft", None)
    return ConversationHandler.END


async def cancel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel an active post composition."""
    message = update.effective_message
    post_draft = context.user_data.pop("post_draft", None)
    if post_draft:
        await delete_messages_safely(
            context,
            update.effective_user.id,
            post_draft.get("preview_message_id"),
            post_draft.get("prompt_message_id"),
            post_draft.get("selector_message_id"),
        )
    await update.effective_message.reply_text("Публикация отменена.")
    return ConversationHandler.END


async def unsupported_post_content(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.effective_message.reply_text(
        "Сейчас поддерживаются текст и одна фотография с подписью."
    )
    return WAITING_POST_CONTENT


async def reject_foreign_post_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """Explain why another administrator cannot approve someone else's post."""
    query = update.callback_query
    if query is None or query.data is None or update.effective_user is None:
        return

    _, owner_id = query.data.split(":", maxsplit=1)
    if update.effective_user.id != int(owner_id):
        await query.answer(
            "Подтвердить этот пост может только его автор.",
            show_alert=True,
        )


def make_support_topic_name(user) -> str:
    identity = f"@{user.username}" if user.username else f"ID {user.id}"
    return f"{user.full_name} · {identity}"[:128]


async def create_support_thread(user, client_chat_id: int, context):
    forum_topic = await context.bot.create_forum_topic(
        chat_id=SUPPORT_CHAT_ID,
        name=make_support_topic_name(user),
    )
    thread = {
        "client_user_id": user.id,
        "client_chat_id": client_chat_id,
        "admin_chat_id": SUPPORT_CHAT_ID,
        "admin_thread_id": forum_topic.message_thread_id,
        "full_name": user.full_name,
        "username": user.username,
    }
    save_support_thread(
        DATABASE_PATH,
        **thread,
    )

    username = f"@{user.username}" if user.username else "—"
    await context.bot.send_message(
        chat_id=SUPPORT_CHAT_ID,
        message_thread_id=forum_topic.message_thread_id,
        text=(
            "👤 Новый диалог с пользователем\n\n"
            f"Имя: {user.full_name}\n"
            f"Username: {username}\n"
            f"User ID: {user.id}"
        ),
    )
    return thread


async def send_client_content_to_support(message, thread, context):
    if message.photo:
        return await context.bot.send_photo(
            chat_id=SUPPORT_CHAT_ID,
            message_thread_id=thread["admin_thread_id"],
            photo=message.photo[-1].file_id,
            caption=message.caption or None,
        )

    return await context.bot.send_message(
        chat_id=SUPPORT_CHAT_ID,
        message_thread_id=thread["admin_thread_id"],
        text=message.text,
    )


async def handle_client_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    message = update.message

    thread = get_support_thread_by_user(DATABASE_PATH, user.id)
    if thread is None:
        thread = await create_support_thread(
            user,
            update.effective_chat.id,
            context,
        )

    try:
        admin_message = await send_client_content_to_support(
            message,
            thread,
            context,
        )
    except BadRequest as error:
        error_text = str(error).lower()
        if "topic" not in error_text and "thread" not in error_text:
            raise
        thread = await create_support_thread(
            user,
            update.effective_chat.id,
            context,
        )
        admin_message = await send_client_content_to_support(
            message,
            thread,
            context,
        )

    content_type = "photo" if message.photo else "text"
    text = message.caption if message.photo else message.text
    file_id = message.photo[-1].file_id if message.photo else None
    save_support_message(
        DATABASE_PATH,
        client_user_id=user.id,
        direction="client_to_admin",
        content_type=content_type,
        text=text,
        file_id=file_id,
        source_message_id=message.message_id,
        destination_message_id=admin_message.message_id,
    )

    await message.reply_text(
        "✅ Сообщение передано в поддержку ComplexBar."
    )


async def handle_admin_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.message
    if message.message_thread_id is None:
        return

    thread = get_support_thread_by_admin_topic(
        DATABASE_PATH,
        admin_chat_id=message.chat_id,
        admin_thread_id=message.message_thread_id,
    )
    if thread is None:
        return

    try:
        if message.photo:
            client_message = await context.bot.send_photo(
                chat_id=thread["client_chat_id"],
                photo=message.photo[-1].file_id,
                caption=message.caption or None,
            )
        else:
            client_message = await context.bot.send_message(
                chat_id=thread["client_chat_id"],
                text=message.text,
            )
    except Forbidden:
        await message.reply_text(
            "❌ Сообщение не доставлено: пользователь заблокировал бота."
        )
        return

    content_type = "photo" if message.photo else "text"
    text = message.caption if message.photo else message.text
    file_id = message.photo[-1].file_id if message.photo else None
    save_support_message(
        DATABASE_PATH,
        client_user_id=thread["client_user_id"],
        direction="admin_to_client",
        content_type=content_type,
        text=text,
        file_id=file_id,
        source_message_id=message.message_id,
        destination_message_id=client_message.message_id,
    )

    await message.reply_text(
        "✅ Ответ отправлен клиенту."
    )


def main():
    global ADMIN_CHAT_ID, SUPPORT_CHAT_ID, ADMIN_IDS, TOPICS

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN not found in .env")

    if not ADMIN_CHAT_ID_VALUE:
        raise RuntimeError("ADMIN_CHAT_ID not found in .env")

    if not ADMIN_IDS_VALUE:
        raise RuntimeError("ADMIN_IDS not found in .env")

    if not SUPPORT_CHAT_ID_VALUE:
        raise RuntimeError("SUPPORT_CHAT_ID not found in .env")

    try:
        ADMIN_CHAT_ID = int(ADMIN_CHAT_ID_VALUE)
    except ValueError as error:
        raise RuntimeError("ADMIN_CHAT_ID must be an integer") from error

    try:
        SUPPORT_CHAT_ID = int(SUPPORT_CHAT_ID_VALUE)
    except ValueError as error:
        raise RuntimeError("SUPPORT_CHAT_ID must be an integer") from error

    try:
        ADMIN_IDS = {
            int(user_id.strip())
            for user_id in ADMIN_IDS_VALUE.strip("{} ").split(",")
            if user_id.strip()
        }
    except ValueError as error:
        raise RuntimeError(
            "ADMIN_IDS must contain comma-separated integers"
        ) from error

    if not ADMIN_IDS:
        raise RuntimeError("ADMIN_IDS must contain at least one user ID")

    TOPICS = load_topics()

    initialize_database(DATABASE_PATH)

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("chatid", chat_id)
    )

    application.add_handler(
        CommandHandler(
            "topicid",
            topic_id,
            filters=filters.Chat(ADMIN_CHAT_ID) & filters.User(ADMIN_IDS),
        )
    )

    application.add_handler(
        CommandHandler(
            "setupcontact",
            setup_contact,
            filters=filters.Chat(ADMIN_CHAT_ID),
        )
    )

    application.add_handler(
        ConversationHandler(
            entry_points=[
                CommandHandler(
                    "post",
                    start_post,
                    filters=filters.ChatType.PRIVATE,
                )
            ],
            states={
                SELECTING_POST_TOPIC: [
                    CallbackQueryHandler(
                        select_post_topic,
                        pattern=r"^post_topic:[a-z_]+$",
                    )
                ],
                WAITING_POST_CONTENT: [
                    MessageHandler(
                        filters.ChatType.PRIVATE
                        & ((filters.TEXT & ~filters.COMMAND) | filters.PHOTO),
                        receive_post_content,
                    ),
                    MessageHandler(
                        filters.ChatType.PRIVATE & ~filters.COMMAND,
                        unsupported_post_content,
                    ),
                ],
                WAITING_POST_CONFIRMATION: [
                    CallbackQueryHandler(
                        confirm_post,
                        pattern=r"^post_(publish|cancel):\d+$",
                    )
                ],
            },
            fallbacks=[
                CommandHandler(
                    "cancel",
                    cancel_post,
                    filters=filters.ChatType.PRIVATE,
                )
            ],
            allow_reentry=True,
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            reject_foreign_post_confirmation,
            pattern=r"^post_(publish|cancel):\d+$",
        ),
        group=1,
    )

    # Сообщения клиентов боту.
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & (filters.TEXT | filters.PHOTO)
            & ~filters.COMMAND,
            handle_client_message,
        )
    )

    # Ответы администраторов.
    application.add_handler(
        MessageHandler(
            filters.Chat(SUPPORT_CHAT_ID)
            & (filters.TEXT | filters.PHOTO)
            & ~filters.COMMAND,
            handle_admin_reply,
        )
    )

    print("ComplexBar Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
