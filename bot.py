import asyncio
import re
import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# 🔑 Токен вашего бота
BOT_TOKEN = "8734630843:AAFH-0gQa9EBbD_oDTBLFwemGVk9GK9BEis"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранилище распарсенных паков в памяти (in-memory)
USER_PACKS = {}
ITEMS_PER_PAGE = 5  # Количество элементов на одной странице таблицы


def build_page_text(pack_title: str, emojis: list, page: int) -> str:
    total_pages = (len(emojis) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_items = emojis[start_idx:end_idx]

    text = f"📦 <b>Параметры пака:</b> {pack_title}\n"
    text += f"📖 <b>Страница:</b> {page + 1} из {total_pages}\n"
    text += "⎯" * 20 + "\n\n"

    text += "<b>Эмодзи | Символ | custom_emoji_id</b>\n"
    for item in current_items:
        emoji_id = item["id"]
        alt = item["alt"]
        text += f'• <tg-emoji custom_emoji_id="{emoji_id}">{alt}</tg-emoji> | <code>{alt}</code> | <code>{emoji_id}</code>\n'

    return text


def build_keyboard(page: int, total_items: int, pack_short_name: str) -> InlineKeyboardMarkup:
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    buttons = []

    prev_btn = (
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page:{pack_short_name}:{page - 1}")
        if page > 0
        else InlineKeyboardButton(text="🚫", callback_data="noop")
    )

    page_btn = InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")

    next_btn = (
        InlineKeyboardButton(text="Вперед ➡️", callback_data=f"page:{pack_short_name}:{page + 1}")
        if page < total_pages - 1
        else InlineKeyboardButton(text="🚫", callback_data="noop")
    )

    buttons.append([prev_btn, page_btn, next_btn])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Привет! Отправь мне ссылку на **эмодзипак** или **стикерпак**\n"
        "(например: `https://t.me/addemoji/DuckEmojiPack`), и я сформирую таблицу с `custom_emoji_id`!",
        parse_mode="Markdown"
    )


@dp.message(F.text)
async def handle_pack_link(message: types.Message):
    text = message.text.strip()

    # Извлекаем short_name из ссылок t.me/addemoji/... или t.me/addstickers/...
    match = re.search(r"(?:addemoji|addstickers)/([a-zA-Z0-9_]+)", text)
    if not match:
        await message.answer("❌ Отправьте корректную ссылку на эмодзипак/стикерпак.")
        return

    short_name = match.group(1)

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getStickerSet?sticker_set_name={short_name}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()

    if not data.get("ok"):
        await message.answer("⚠️ Не удалось найти пак по этой ссылке. Убедитесь, что ссылка правильная.")
        return

    result = data["result"]
    title = result.get("title", short_name)
    stickers = result.get("stickers", [])

    parsed_emojis = []
    for s in stickers:
        emoji_id = s.get("custom_emoji_id") or s.get("file_id")
        alt = s.get("emoji", "❓")
        parsed_emojis.append({"id": emoji_id, "alt": alt})

    if not parsed_emojis:
        await message.answer("❌ В этом паке не найдено элементов.")
        return

    USER_PACKS[short_name] = {"title": title, "emojis": parsed_emojis}

    response_text = build_page_text(title, parsed_emojis, 0)
    keyboard = build_keyboard(0, len(parsed_emojis), short_name)

    await message.answer(response_text, reply_markup=keyboard, parse_mode="HTML")


@dp.callback_query(F.data == "noop")
async def noop_handler(callback: types.CallbackQuery):
    await callback.answer()


@dp.callback_query(F.data.startswith("page:"))
async def pagination_handler(callback: types.CallbackQuery):
    _, short_name, page_str = callback.data.split(":")
    page = int(page_str)

    pack_data = USER_PACKS.get(short_name)
    if not pack_data:
        await callback.answer("Сессия истекла. Отправьте ссылку заново.", show_alert=True)
        return

    emojis = pack_data["emojis"]
    title = pack_data["title"]

    response_text = build_page_text(title, emojis, page)
    keyboard = build_keyboard(page, len(emojis), short_name)

    await callback.message.edit_text(response_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


async def main():
    print("🤖 Бот успешно запущен и ждет ссылок!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
