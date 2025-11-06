import aiosqlite
from typing import List, Tuple, Optional

import os
DB_PATH = os.getenv("MIRROR_DB_PATH", "mirror.db")  # підтримка персистентного диска

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER UNIQUE NOT NULL,
            title TEXT,
            kind TEXT CHECK(kind IN ('source','destination')) NOT NULL
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_tg_id INTEGER NOT NULL,
            dest_tg_id INTEGER NOT NULL,
            UNIQUE(source_tg_id, dest_tg_id)
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS link_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern TEXT NOT NULL,
            replacement TEXT NOT NULL
        )""")
        # міграція: додаємо колонку text_repl, якщо її ще нема
        try:
            await db.execute("ALTER TABLE link_rules ADD COLUMN text_repl TEXT DEFAULT NULL")
        except Exception:
            pass
        await db.commit()

async def upsert_channel(tg_id: int, title: str, kind: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO channels (tg_id, title, kind) VALUES (?,?,?) "
            "ON CONFLICT(tg_id) DO UPDATE SET title=excluded.title, kind=excluded.kind",
            (tg_id, title, kind)
        )
        await db.commit()

async def list_channels(kind: Optional[str] = None) -> List[Tuple[int,int,str,str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        if kind:
            q = await db.execute(
                "SELECT id, tg_id, title, kind FROM channels WHERE kind=? ORDER BY id DESC",
                (kind,)
            )
        else:
            q = await db.execute("SELECT id, tg_id, title, kind FROM channels ORDER BY id DESC")
        rows = await q.fetchall()
        return rows

async def add_mapping(source_tg_id: int, dest_tg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO mappings (source_tg_id, dest_tg_id) VALUES (?,?)",
            (source_tg_id, dest_tg_id)
        )
        await db.commit()

async def remove_mapping(source_tg_id: int, dest_tg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM mappings WHERE source_tg_id=? AND dest_tg_id=?",
            (source_tg_id, dest_tg_id)
        )
        await db.commit()

async def list_mappings_for_source(source_tg_id: int) -> List[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        q = await db.execute("SELECT dest_tg_id FROM mappings WHERE source_tg_id=?", (source_tg_id,))
        rows = await q.fetchall()
        return [r[0] for r in rows]

# ------- ОНОВЛЕНО: правила з текстом -------
async def add_link_rule(pattern: str, replacement: str, text_repl: Optional[str] = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO link_rules (pattern, replacement, text_repl) VALUES (?,?,?)",
            (pattern, replacement, text_repl)
        )
        await db.commit()

async def remove_link_rule(rule_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM link_rules WHERE id=?", (rule_id,))
        await db.commit()

async def list_link_rules():
    async with aiosqlite.connect(DB_PATH) as db:
        q = await db.execute(
            "SELECT id, pattern, replacement, text_repl FROM link_rules ORDER BY id ASC"
        )
        return await q.fetchall()
