"""
Telegram Channel Mirror Bot
--------------------------
A bot that automatically mirrors posts between Telegram channels while preserving
formatting and supporting link replacement rules.

Features:
- Mirror posts between multiple source and destination channels
- Preserve message formatting (HTML)
- Replace links using regex patterns
- Support all major content types (text, media, polls)
- SQLite storage for configuration
- Admin-only configuration commands

Author: Your Name
License: MIT
"""

import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, ChatMemberUpdated, ChatJoinRequest, ContentType
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from config import BOT_TOKEN, ADMIN_IDS
from storage import init_db, upsert_channel, list_channels, add_mapping, remove_mapping, list_mappings_for_source, add_link_rule, remove_link_rule, list_link_rules
from link_rules import replace_links_in_html

# Initialize bot and dispatcher
dp = Dispatcher()
bot = Bot(BOT_TOKEN, parse_mode=ParseMode.HTML)


def is_admin(user_id: int) -> bool:
    """Check if user is in the admin list.
    
    Args:
        user_id (int): Telegram user ID to check
        
    Returns:
        bool: True if user is admin, False otherwise
    """
    return user_id in ADMIN_IDS


@dp.message(Command("start"))
async def start(m: Message):
    """Initialize bot and send welcome message.
    
    Args:
        m (Message): Incoming start command message
    """
    await init_db()
    await m.answer("Hello! I'm a channel mirror bot. Available commands: /help")


@dp.message(Command("help"))
async def help_cmd(m: Message):
    """Show help message with available commands.
    
    Args:
        m (Message): Incoming help command message
    """
    txt = (
        "<b>Commands (admin only):</b>\n"
        "/add_source - Add current channel as source (run in channel)\n"
        "/add_dest - Add current channel as destination (run in channel)\n"
        "/channels - List registered channels\n"
        "/map &lt;source_id&gt; &lt;dest_id&gt; - Create mirroring link\n"
        "/unmap &lt;source_id&gt; &lt;dest_id&gt; - Remove mirroring link\n"
        "/rules - Show link replacement rules\n"
        "/addrule &lt;pattern&gt; &lt;replacement&gt; - Add replacement rule (regex)\n"
        "/delrule &lt;id&gt; - Delete rule by ID\n"
        "\n<b>Setup:</b> Add bot as admin to source channels (to receive posts) "
        "and destination channels (to send posts)."
    )
    await m.answer(txt)


async def ensure_admin(m: Message) -> bool:
    if not is_admin(m.from_user.id):
        await m.answer("Тільки для адмінів.")
        return False
    return True


@dp.message(Command("add_source"))
async def add_source(m: Message):
    if not await ensure_admin(m):
        return
    if m.chat.type != "channel":
        await m.answer("Цю команду потрібно викликати саме в каналі-джерелі.")
        return
    await upsert_channel(m.chat.id, m.chat.title or "", "source")
    await m.answer(f"Додано канал-джерело: <code>{m.chat.title}</code> (ID: <code>{m.chat.id}</code>)")


@dp.message(Command("add_dest"))
async def add_dest(m: Message):
    if not await ensure_admin(m):
        return
    if m.chat.type != "channel":
        await m.answer("Цю команду потрібно викликати саме в каналі-призначенні.")
        return
    await upsert_channel(m.chat.id, m.chat.title or "", "destination")
    await m.answer(f"Додано канал-призначення: <code>{m.chat.title}</code> (ID: <code>{m.chat.id}</code>)")


@dp.message(Command("channels"))
async def channels(m: Message):
    if not await ensure_admin(m):
        return
    items = await list_channels()
    if not items:
        await m.answer("Список каналів порожній.")
        return
    lines = []
    for cid, tg_id, title, kind in items:
        lines.append(f"#{cid} <b>{kind}</b> — {title or '-'} (tg_id: <code>{tg_id}</code>)")
    await m.answer("\n".join(lines))


@dp.message(Command("map"))
async def map_cmd(m: Message):
    if not await ensure_admin(m):
        return
    parts = m.text.strip().split()
    if len(parts) != 3:
        await m.answer("Синтаксис: /map &lt;source_id&gt; &lt;dest_id&gt; (це <b>tg_id</b> каналів)")
        return
    src = int(parts[1]); dst = int(parts[2])
    await add_mapping(src, dst)
    await m.answer(f"Зв'язано: <code>{src}</code> ➜ <code>{dst}</code>")


@dp.message(Command("unmap"))
async def unmap_cmd(m: Message):
    if not await ensure_admin(m):
        return
    parts = m.text.strip().split()
    if len(parts) != 3:
        await m.answer("Синтаксис: /unmap &lt;source_id&gt; &lt;dest_id&gt; (це <b>tg_id</b> каналів)")
        return
    src = int(parts[1]); dst = int(parts[2])
    await remove_mapping(src, dst)
    await m.answer(f"Видалено зв'язок: <code>{src}</code> ✖ <code>{dst}</code>")


@dp.message(Command("rules"))
async def rules_cmd(m: Message):
    if not await ensure_admin(m):
        return
    rules = await list_link_rules()
    if not rules:
        await m.answer("Правил заміни ще немає.")
        return
    lines = ["<b>Правила заміни посилань (regex → replacement):</b>"]
    for rid, pat, rep in rules:
        lines.append(f"{rid}. <code>{pat}</code> → <code>{rep}</code>")
    await m.answer("\n".join(lines))


@dp.message(Command("addrule"))
async def addrule_cmd(m: Message):
    if not await ensure_admin(m):
        return
    try:
        # Split only into 3 parts: cmd, pattern, replacement (replacement may contain spaces)
        head, pattern, replacement = m.text.strip().split(" ", 2)
    except ValueError:
        await m.answer("Синтаксис: /addrule <pattern> <replacement>")
        return
    await add_link_rule(pattern, replacement)
    await m.answer("Додано правило.")


@dp.message(Command("delrule"))
async def delrule_cmd(m: Message):
    if not await ensure_admin(m):
        return
    parts = m.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await m.answer("Синтаксис: /delrule <id>")
        return
    await remove_link_rule(int(parts[1]))
    await m.answer("Видалено (якщо існувало).")


async def get_rules():
    rows = await list_link_rules()
    return [(r[1], r[2]) for r in rows]


async def mirror_to_dests(source_chat_id: int, send_fn):
    dest_ids = await list_mappings_for_source(source_chat_id)
    for dest in dest_ids:
        try:
            await send_fn(dest)
        except Exception:
            # You may log errors per-destination here
            pass


# Core mirroring logic: handle new channel posts
@dp.channel_post()
async def on_channel_post(m: Message):
    """Handle new posts in source channels and mirror them to destinations.
    
    This handler processes new posts from source channels and mirrors them to all
    linked destination channels. It preserves formatting and handles all content
    types including:
    - Text messages with formatting
    - Media (photos, videos, documents)
    - Polls
    - Voice messages and video notes
    
    For text content, links are processed according to configured replacement rules.
    
    Args:
        m (Message): New channel post message
    """
    # Get linked destination channels
    dest_ids = await list_mappings_for_source(m.chat.id)
    if not dest_ids:
        return  # No destinations configured for this source

    rules = await get_rules()

    # Helper to process text/caption with link replacements preserving formatting via HTML
    def transform_html(html_text: str) -> str:
        return replace_links_in_html(html_text or "", rules)

    # Send per content type
    if m.content_type == ContentType.TEXT:
        html = transform_html(m.html_text)

        async def send(dest_id: int):
            await bot.send_message(dest_id, html, disable_web_page_preview=False)

        await mirror_to_dests(m.chat.id, send)

    elif m.content_type == ContentType.PHOTO:
        html = transform_html(m.caption_html or "")

        async def send(dest_id: int):
            await bot.send_photo(dest_id, m.photo[-1].file_id, caption=html)

        await mirror_to_dests(m.chat.id, send)

    elif m.content_type == ContentType.VIDEO:
        html = transform_html(m.caption_html or "")

        async def send(dest_id: int):
            await bot.send_video(dest_id, m.video.file_id, caption=html)

        await mirror_to_dests(m.chat.id, send)

    elif m.content_type == ContentType.ANIMATION:
        html = transform_html(m.caption_html or "")

        async def send(dest_id: int):
            await bot.send_animation(dest_id, m.animation.file_id, caption=html)

        await mirror_to_dests(m.chat.id, send)

    elif m.content_type == ContentType.DOCUMENT:
        html = transform_html(m.caption_html or "")

        async def send(dest_id: int):
            await bot.send_document(dest_id, m.document.file_id, caption=html)

        await mirror_to_dests(m.chat.id, send)

    elif m.content_type == ContentType.AUDIO:
        html = transform_html(m.caption_html or "")

        async def send(dest_id: int):
            await bot.send_audio(dest_id, m.audio.file_id, caption=html)

        await mirror_to_dests(m.chat.id, send)

    elif m.content_type == ContentType.VOICE:
        html = transform_html(m.caption_html or "")

        async def send(dest_id: int):
            await bot.send_voice(dest_id, m.voice.file_id, caption=html)

        await mirror_to_dests(m.chat.id, send)

    elif m.content_type == ContentType.VIDEO_NOTE:

        async def send(dest_id: int):
            await bot.send_video_note(dest_id, m.video_note.file_id)

        await mirror_to_dests(m.chat.id, send)

    elif m.content_type == ContentType.POLL and m.poll:
        # Recreate poll
        async def send(dest_id: int):
            await bot.send_poll(
                chat_id=dest_id,
                question=m.poll.question,
                options=[o.text for o in m.poll.options],
                is_anonymous=m.poll.is_anonymous,
                allows_multiple_answers=m.poll.allows_multiple_answers,
                type=m.poll.type,
                correct_option_id=m.poll.correct_option_id if m.poll.type == "quiz" else None,
                explanation=m.poll.explanation if m.poll.type == "quiz" else None,
            )

        await mirror_to_dests(m.chat.id, send)

    else:
        # Fallback: try to copy as-is when we don't handle explicitly
        async def send(dest_id: int):
            await bot.copy_message(chat_id=dest_id, from_chat_id=m.chat.id, message_id=m.message_id)

        await mirror_to_dests(m.chat.id, send)


# Edited posts mirroring (update text/captions)
@dp.edited_channel_post()
async def on_edited_channel_post(m: Message):
    # Simple approach: resend updated version as a new post to destinations (advanced: track message mapping to edit)
    dest_ids = await list_mappings_for_source(m.chat.id)
    if not dest_ids:
        return

    rules = await get_rules()

    def transform_html(html_text: str) -> str:
        return replace_links_in_html(html_text or "", rules)

    if m.content_type == ContentType.TEXT:
        html = transform_html(m.html_text)

        async def send(dest_id: int):
            await bot.send_message(dest_id, f"🔁 <i>Оновлено</i>\n\n{html}")

        await mirror_to_dests(m.chat.id, send)
    else:
        # For media edits, re-post the updated version similarly
        await on_channel_post(m)


async def main():
    await init_db()
    print("Bot started.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
