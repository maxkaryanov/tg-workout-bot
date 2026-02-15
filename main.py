import os
import re
import math
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import html

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "bot.db"
TZ = ZoneInfo("Europe/Helsinki")

PROGRESS_RE = re.compile(r"(\d+)\s*/\s*(\d+)")
NAME_WIDTH = 20  # фикс ширина имени (в символах, моноширинный шрифт)

# ================== DATE HELPERS ==================
def now():
    return datetime.now(TZ)

def next_jan_1():
    d = now()
    return datetime(d.year + 1, 1, 1, tzinfo=TZ)

def weeks_left():
    days = (next_jan_1().date() - now().date()).days
    return max(1, math.ceil(days / 7))

# ================== DATABASE ==================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS progress (
                chat_id INTEGER,
                user_id INTEGER,
                name TEXT,
                done INTEGER,
                goal INTEGER,
                updated TEXT,
                PRIMARY KEY (chat_id, user_id)
            )
        """)
        await db.commit()

async def save_progress(chat_id: int, user_id: int, name: str, done: int, goal: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO progress VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                name=excluded.name,
                done=excluded.done,
                goal=excluded.goal,
                updated=excluded.updated
        """, (chat_id, user_id, name, done, goal, now().isoformat(timespec="seconds")))
        await db.commit()

async def get_all(chat_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT name, done, goal FROM progress WHERE chat_id=?",
            (chat_id,)
        ) as cur:
            return await cur.fetchall()

# ================== FORMAT ==================
def format_name(name: str) -> str:
    name = (name or "—").strip()
    if len(name) <= NAME_WIDTH:
        return name.ljust(NAME_WIDTH)
    # аккуратное троеточие, чтобы длина всегда была ровно NAME_WIDTH
    return (name[:NAME_WIDTH - 1] + "…")

def render_table(rows, title: str = "🏁 Рейтинг обновлён") -> str:
    wl = weeks_left()
    deadline = next_jan_1().date()

    header = (
        f"{title}\n"
        f"Дедлайн: {deadline} • недель осталось: {wl}\n\n"
        f" #  {'Участник':<{NAME_WIDTH}}  Сделано   Осталось  /нед\n"
        + "-" * (NAME_WIDTH + 39)
    )

    rows = list(rows)
    rows.sort(key=lambda r: -r[1])  # по "Сделано" по убыванию

    lines = [header]
    for i, (name, done, goal) in enumerate(rows, 1):
        left = max(0, goal - done)
        per_week = math.ceil(left / wl) if left else 0
        lines.append(
            f"{i:>2}  {format_name(name)}  {done:>3}/{goal:<3}      {left:>3}     {per_week:>3}"
        )

    table_text = "\n".join(lines)
    # экранируем HTML, чтобы имена с символами < > & не ломали разметку
    return f"<pre>{html.escape(table_text)}</pre>"

# ================== MAIN ==================
async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set (environment variable).")

    await init_db()

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    last_chat_id = {"id": None}

    @dp.message(Command("top"))
    async def top(m: Message):
        rows = await get_all(m.chat.id)
        await m.answer(render_table(rows), parse_mode="HTML")

    @dp.message(F.text)
    async def catch(m: Message):
        match = PROGRESS_RE.search(m.text or "")
        if not match:
            return

        done, goal = map(int, match.groups())
        if goal <= 0 or done < 0 or done > goal:
            return

        last_chat_id["id"] = m.chat.id

        await save_progress(
            m.chat.id,
            m.from_user.id,
            m.from_user.full_name or m.from_user.username or str(m.from_user.id),
            done,
            goal
        )

        rows = await get_all(m.chat.id)
        await bot.send_message(m.chat.id, render_table(rows), parse_mode="HTML")

    async def weekly_post(chat_id: int):
        rows = await get_all(chat_id)
        await bot.send_message(chat_id, render_table(rows, title="🏋️ Лидерборд недели"), parse_mode="HTML")

    scheduler = AsyncIOScheduler(timezone=TZ)
    scheduler.add_job(
        lambda: asyncio.create_task(weekly_post(last_chat_id["id"])) if last_chat_id["id"] else None,
        trigger="cron",
        day_of_week="mon",
        hour=9,
        minute=0
    )
    scheduler.start()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
