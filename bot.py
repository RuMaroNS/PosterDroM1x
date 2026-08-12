import os
import asyncio
import re
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest

# ================= КОНФИГУРАЦИЯ =================
ADMIN_ID = 8623982085
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Хранилище распарсенных паков в памяти
USER_PACKS = {}
ITEMS_PER_PAGE = 10


# ================= СОСТОЯНИЯ FSM =================
class BotStates(StatesGroup):
    waiting_for_pack_link = State()
    waiting_for_channel = State()
    waiting_for_post_content = State()


# ================= КЛАВИАТУРЫ =================
def main_menu_keyboard():
    """Главная клавиатура бота."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить эмодзи пак")],
            [KeyboardButton(text="📝 Сделать пост")],
        ],
        resize_keyboard=True,
    )


def build_pack_page(title: str, emojis: list, page: int, pack_name: str):
    """Формирует текст и инлайн-клавиатуру для просмотра эмодзи из пака."""
    total_pages = (len(emojis) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_items = emojis[start_idx:end_idx]

    text = f"📦 <b>Параметры пака:</b> {title}\n"
    text += f"📖 <b>Страница:</b> {page + 1} из {total_pages}\n"
    text += "💡 <i>Нажмите на кнопку ниже, чтобы быстро скопировать ID эмодзи!</i>\n"
    text += "⎯" * 20 + "\n\n"

    inline_keyboard = []
    emoji_row = []

    for item in current_items:
        emoji_id = item["id"]
        alt = item["alt"]
        is_custom = item["is_custom"]

        if is_custom and emoji_id:
            # Текст в списке
            text += f'• <tg-emoji custom_emoji_id="{emoji_id}">{alt}</tg-emoji> | <code>{alt}</code> | <code>{emoji_id}</code>\n'
            # Кнопка с премиум-эмодзи и callback c его ID
            btn_text = alt
            cb_data = f"copy:{emoji_id}"
        else:
            text += f"• 🖼 {alt} | <code>{alt}</code> | <i>(Не кастомный)</i>\n"
            btn_text = f"🖼 {alt}"
            cb_data = "noop"

        emoji_row.append(InlineKeyboardButton(text=btn_text, callback_data=cb_data))

        # Группируем кнопки по 5 в ряд
        if len(emoji_row) == 5:
            inline_keyboard.append(emoji_row)
            emoji_row = []

    if emoji_row:
        inline_keyboard.append(emoji_row)

    # Кнопки навигации по страницам
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page:{pack_name}:{page - 1}"))
    else:
        nav_row.append(InlineKeyboardButton(text="🚫", callback_data="noop"))

    nav_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))

    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"page:{pack_name}:{page + 1}"))
    else:
        nav_row.append(InlineKeyboardButton(text="🚫", callback_data="noop"))

    inline_keyboard.append(nav_row)

    return text, InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


# ================= МИДДЛВАРЬ ПРОВЕРКИ ВЛАДЕЛЬЦА =================
@dp.message.outer_middleware()
@dp.callback_query.outer_middleware()
async def admin_check_middleware(handler, event, data):
    """Пропускает только владельца бота."""
    user = data.get("event_from_user")
    if not user or user.id != ADMIN_ID:
        if isinstance(event, types.Message):
            await event.answer("⛔ <b>Доступ запрещен!</b> Вы не являетесь владельцем этого бота.", parse_mode="HTML")
        elif isinstance(event, types.CallbackQuery):
            await event.answer("⛔ Доступ запрещен!", show_alert=True)
        return
    return await handler(event, data)


# ================= ХЕНДЛЕРЫ =================
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"👋 Привет, Владелец!\nВоспользуйся меню ниже для работы с паками и публикацией постов.",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


# --- Секция 1: Добавление и парсинг эмодзи пака ---
@dp.message(F.text == "➕ Добавить эмодзи пак")
async def start_add_pack(message: types.Message, state: FSMContext):
    await state.set_state(BotStates.waiting_for_pack_link)
    await message.answer(
        "🔗 Отправь ссылку на **эмодзипак** или **стикерпак**\n"
        "(например: `https://t.me/addemoji/MashupEmoji` или `https://t.me/addstickers/DuckEmojiPack`):",
        parse_mode="Markdown",
    )


@dp.message(BotStates.waiting_for_pack_link)
async def process_pack_link(message: types.Message, state: FSMContext):
    text = message.text.strip()
    match = re.search(r"(?:addemoji|addstickers)/([a-zA-Z0-9_]+)", text)

    if not match:
        await message.answer("❌ Некорректная ссылка! Отправь ссылку формата:\n`https://t.me/addemoji/НазваниеПака`", parse_mode="Markdown")
        return

    short_name = match.group(1)

    try:
        sticker_set = await bot.get_sticker_set(name=short_name)
    except Exception as e:
        await message.answer(f"⚠️ Не удалось найти пак по этой ссылке.\nОшибка: `{e}`", parse_mode="Markdown")
        return

    title = sticker_set.title
    stickers = sticker_set.stickers

    parsed_emojis = []
    for s in stickers:
        is_custom = bool(s.custom_emoji_id)
        emoji_id = s.custom_emoji_id if is_custom else s.file_id
        alt = s.emoji or "❓"

        parsed_emojis.append({
            "id": emoji_id,
            "alt": alt,
            "is_custom": is_custom
        })

    if not parsed_emojis:
        await message.answer("❌ В этом паке не найдено элементов.")
        await state.clear()
        return

    USER_PACKS[short_name] = {"title": title, "emojis": parsed_emojis}
    await state.clear()

    response_text, keyboard = build_pack_page(title, parsed_emojis, 0, short_name)
    await message.answer(response_text, reply_markup=keyboard, parse_mode="HTML")


@dp.callback_query(F.data.startswith("page:"))
async def handle_pagination(callback: types.CallbackQuery):
    _, pack_name, page_str = callback.data.split(":")
    page = int(page_str)

    pack_data = USER_PACKS.get(pack_name)
    if not pack_data:
        await callback.answer("Сессия пака истекла. Отправьте ссылку заново.", show_alert=True)
        return

    response_text, keyboard = build_pack_page(pack_data["title"], pack_data["emojis"], page, pack_name)
    await callback.message.edit_text(response_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("copy:"))
async def handle_copy_id(callback: types.CallbackQuery):
    """Выплевывает отдельный моноширинный ID для моментального копирования по клику."""
    emoji_id = callback.data.split(":")[1]
    await callback.message.answer(f"<code>{emoji_id}</code>", parse_mode="HTML")
    await callback.answer("ID отправлен ниже!")


@dp.callback_query(F.data == "noop")
async def handle_noop(callback: types.CallbackQuery):
    await callback.answer()


# --- Секция 2: Создание поста и проверка админки в канале ---
@dp.message(F.text == "📝 Сделать пост")
async def start_create_post(message: types.Message, state: FSMContext):
    await state.set_state(BotStates.waiting_for_channel)
    await message.answer(
        "📢 <b>Укажите канал для публикации:</b>\n\n"
        "1. Перешлите любое сообщение из вашего канала сюда\n"
        "2. Или отправьте <code>@username_канала</code> / ID канала (например: <code>-100123456789</code>)",
        parse_mode="HTML",
    )


@dp.message(BotStates.waiting_for_channel)
async def process_channel_input(message: types.Message, state: FSMContext):
    channel_id = None

    # Если переслано сообщение из канала
    if message.forward_from_chat:
        channel_id = message.forward_from_chat.id
    else:
        text = message.text.strip()
        if text.startswith("@") or text.startswith("-100") or text.lstrip("-").isdigit():
            channel_id = text

    if not channel_id:
        await message.answer("❌ Не удалось определить канал. Перешлите сообщение из канала или укажите `@username`.")
        return

    # Проверяем, есть ли бот в канале и является ли он администратором
    try:
        chat_member = await bot.get_chat_member(chat_id=channel_id, user_id=bot.id)
        if chat_member.status not in ["administrator", "creator"]:
            await message.answer("⚠️ Бот **не является администратором** в этом канале! Добавьте бота в канал и дайте ему права на публикацию сообщений.", parse_mode="Markdown")
            return

        # Проверяем права на отправку
        if hasattr(chat_member, "can_post_messages") and not chat_member.can_post_messages:
            await message.answer("⚠️ У бота нет разрешения **'Публикация сообщений'** в этом канале.")
            return

    except TelegramBadRequest:
        await message.answer("❌ Бот не найден в этом канале или указан неверный ID/Username канала.")
        return
    except Exception as e:
        await message.answer(f"⚠️ Ошибка проверки канала: `{e}`", parse_mode="Markdown")
        return

    await state.update_data(target_channel=channel_id)
    await state.set_state(BotStates.waiting_for_post_content)

    await message.answer(
        "✅ <b>Канал успешно подтвержден!</b>\n\n"
        "Теперь отправьте текст или медиафайл поста. Вы можете использовать HTML-теги и премиум эмодзи:\n"
        "<code>&lt;tg-emoji custom_emoji_id=\"АЙДИ\"&gt;😀&lt;/tg-emoji&gt;</code>",
        parse_mode="HTML",
    )


@dp.message(BotStates.waiting_for_post_content)
async def publish_post(message: types.Message, state: FSMContext):
    data = await state.get_data()
    channel_id = data.get("target_channel")

    try:
        # Копируем сообщение целиком (с сохранением разметки, медиафайлов и эмодзи) в канал
        await message.copy_to(chat_id=channel_id)
        await message.answer("🚀 <b>Пост успешно опубликован в канал!</b>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Не удалось опубликовать пост в канал.\nОшибка: `{e}`", parse_mode="Markdown")

    await state.clear()


# ================= ЗАПУСК =================
async def main():
    print("🤖 Бот запущен и готов к работе!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
