"""
Telegram Channel Mirror Bot
--------------------------
A bot that automatically mirrors posts between Telegram channels while preserving
formatting and supporting link replacement rules.

Changes in this version:
- aiogram 3.13 compatible Bot init (DefaultBotProperties)
- Robust AiohttpSession timeouts to avoid polling hangs
- Added channel_post command handlers for /add_source and /add_dest
- Basic logging
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, ContentType
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession

from config import BOT_TOKEN, ADMIN_IDS
from storage import (
    init_db,
    upsert_channel,
    list_channels,
    add_mapping,
    remove_mapping,
    list_mappings_for_source,
    add_link_rule,
    remove_link_rule,
    list_link_rules,
)
from link_rules import replace_links_in_html

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mirror-bot")

# ---------- Aiogram objects ----------
# More robust HTTP client timeouts for unstable networks
session = AiohttpSession(timeout=60)

bot = Bot(
    BOT_TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ---------- Common commands (private chat) ----------
@dp.message(Command("start"))
async def start(m: Message):
    await init_db()
    await m.answer("Привіт! Я бот-дзеркало для каналів. Доступні команди: /help")

@dp.message(Command("help"))
async def help_cmd(m: Message):
    txt = (
        "<b>Команди (тільки для адмінів у приваті):</b>\n"
        "/channels - список каналів\n"
        "/map &lt;source_id&gt; &lt;dest_id&gt; - зв'язати джерело з призначенням (tg_id)\n"
        "/unmap &lt;source_id&gt; &lt;dest_id&gt; - видалити зв'язок\n"
        "/rules - показати правила заміни посилань\n"
        "/addrule &lt;pattern&gt; &lt;replacement&gt; - додати правило (regex)\n"
        "/delrule &lt;id&gt; - видалити правило за ID\n\n"
        "<b>У каналах:</b>\n"
        "Надішліть (від імені каналу) /add_source у джерелі або /add_dest у призначенні."
    )
    await m.answer(txt)

async def ensure_admin(m: Message) -> bool:
    if not is_admin(m.from_user.id):
        await m.answer("Тільки для адмінів.")
        return False
    return True

@dp.message(Command("channels"))
async def channels_cmd(m: Message):
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
        await m.answer("Синтаксис: /map &lt;source_tg_id&gt; &lt;dest_tg_id&gt;")
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
        await m.answer("Синтаксис: /unmap &lt;source_tg_id&gt; &lt;dest_tg_id&gt;")
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
        _, pattern, replacement = m.text.strip().split(" ", 2)
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


# ---------- Channel-sent commands (channel_post) ----------
@dp.channel_post(Command("add_source"))
async def add_source_from_channel(m: Message):
    # here we cannot check from_user; channel_post has no actual user
    if m.chat.type != "channel":
        return
    await upsert_channel(m.chat.id, m.chat.title or "", "source")
    await m.answer(
        f"Додано канал-джерело: <code>{m.chat.title}</code> (ID: <code>{m.chat.id}</code>)"
    )
    logger.info("Source registered: %s (%s)", m.chat.title, m.chat.id)

@dp.channel_post(Command("add_dest"))
async def add_dest_from_channel(m: Message):
    if m.chat.type != "channel":
        return
    await upsert_channel(m.chat.id, m.chat.title or "", "destination")
    await m.answer(
        f"Додано канал-призначення: <code>{m.chat.title}</code> (ID: <code>{m.chat.id}</code>)"
    )
    logger.info("Destination registered: %s (%s)", m.chat.title, m.chat.id)


# ---------- Mirroring helpers ----------
async def get_rules():
    rows = await list_link_rules()
    return [(r[1], r[2]) for r in rows]

async def mirror_to_dests(source_chat_id: int, send_fn):
    dest_ids = await list_mappings_for_source(source_chat_id)
    for dest in dest_ids:
        try:
            await send_fn(dest)
        except Exception as e:
            logger.warning("Send to %s failed: %s", dest, e)

def transform_html_with_rules(html_text: str, rules):
    return replace_links_in_html(html_text or "", rules)


# ---------- New channel posts ----------
@dp.channel_post()
async def on_channel_post(m: Message):
    dest_ids = await list_mappings_for_source(m.chat.id)
    if not dest_ids:
        return

    rules = await get_rules()

    if m.content_type == ContentType.TEXT:
        html = transform_html_with_rules(m.html_text, rules)
        async def send(dest_id: int):
            await bot.send_message(dest_id, html, disable_web_page_preview=False)
        await mirror_to_dests(m.chat.id, send)

    elif m.content_type == ContentType.PHOTO:
        html = transform_html_with_rules(m.caption_html or "", rules)
        async def send(dest_id: int):
            await bot.send_photo(dest_id, m.photo[-1].file_id, caption=html)
        await mirror_to_dests(m.chat.id, send)

    elif m.content_type == ContentType.VIDEO:
        html = transform_html_with_rules(m.caption_html or "", rules)
        async def send(dest_id: int):
            await bot.send_video(dest_id, m.video.file_id, caption=html)
        await mirror_to_dests(m.chat.id, send)

    elif m.content_type == ContentType.ANIMATION:
        html = transform_html_with_rules(m.caption_html or "", rules)
        async def send(dest_id: int):
            await bot.send_animation(dest_id, m.animation.file_id, caption=html)
        await mirror_to_dests(m.chat.id, send)

    elif m.content_type == ContentType.DOCUMENT:
        html = transform_html_with_rules(m.caption_html or "", rules)
        async def send(dest_id: int):
            await bot.send_document(dest_id, m.document.file_id, caption=html)
        await mirror_to_dests(m.chat.id, send)

    elif m.content_type == ContentType.AUDIO:
        html = transform_html_with_rules(m.caption_html or "", rules)
        async def send(dest_id: int):
            await bot.send_audio(dest_id, m.audio.file_id, caption=html)
        await mirror_to_dests(m.chat.id, send)

    elif m.content_type == ContentType.VOICE:
        html = transform_html_with_rules(m.caption_html or "", rules)
        async def send(dest_id: int):
            await bot.send_voice(dest_id, m.voice.file_id, caption=html)
        await mirror_to_dests(m.chat.id, send)

    elif m.content_type == ContentType.VIDEO_NOTE:
        async def send(dest_id: int):
            await bot.send_video_note(dest_id, m.video_note.file_id)
        await mirror_to_dests(m.chat.id, send)

    elif m.content_type == ContentType.POLL and m.poll:
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
        # fallback copy when content type not handled explicitly
        async def send(dest_id: int):
            await bot.copy_message(chat_id=dest_id, from_chat_id=m.chat.id, message_id=m.message_id)
        await mirror_to_dests(m.chat.id, send)


# ---------- Edited posts (MVP: repost with "updated") ----------
@dp.edited_channel_post()
async def on_edited_channel_post(m: Message):
    dest_ids = await list_mappings_for_source(m.chat.id)
    if not dest_ids:
        return

    rules = await get_rules()
    def transform(html_text: str) -> str:
        return transform_html_with_rules(html_text or "", rules)

    if m.content_type == ContentType.TEXT:
        html = transform(m.html_text)
        async def send(dest_id: int):
            await bot.send_message(dest_id, f"🔁 <i>Оновлено</i>\n\n{html}")
        await mirror_to_dests(m.chat.id, send)
    else:
        await on_channel_post(m)


# ---------- Entrypoint ----------
async def main():
    await init_db()
    logger.info("Bot started.")
    # shorter polling timeout helps behind strict proxies/NATs
    await dp.start_polling(bot, polling_timeout=25)

if __name__ == "__main__":
    asyncio.run(main())
