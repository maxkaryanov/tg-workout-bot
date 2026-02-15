import os
import re
import math
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "bot.db"
TZ = ZoneInfo("Europe/Helsinki")

PROGRESS_RE = re.compile(r"(\d+)\s*/\s*(\d+)")

def now():
    return datetime.now(TZ)

def next_jan_1():
    d = now()
    return datetime(d.year + 1, 1, 1, tzinfo=TZ)

def weeks_left():
    days = (next_jan_1().date() - now().date()).days
    return max(1, math.ceil(days / 7))

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

async def save_progress(chat_id, user_id, name, done, goal):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO progress VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
            done=excluded.done,
            goal=excluded.goal,
            updated=excluded.updated
        """, (chat_id, user_id, name, done, goal, now().isoformat()))
        await db.commit()

async def get_all(chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT name, done, goal FROM progress WHERE chat_id=?",
            (chat_id,)
        ) as cur:
            return await cur.fetchall()

def render_table(rows):
    wl = weeks_left()
    lines = [
        "🏁 Рейтинг обновлён",
        f"Дедлайн: {next_jan_1().date()} • недель осталось: {wl}",
        "",
        " #  Участник            Сделано  Осталось  /нед"
    ]

    rows.sort(key=lambda r: -r[1])

    for i, (name, done, goal) in enumerate(rows, 1):
        left = max(0, goal - done)
        per_week = math.ceil(left / wl) if left else 0
        lines.append(
            f"{i:>2}  {name[:18]:<18}  {done:>3}/{goal:<3}   {left:>5}   {per_week:>3}"
        )
    return "\n".join(lines)

async def main():
    await init_db()

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    @dp.message(Command("top"))
    async def top(m: Message):
        rows = await get_all(m.chat.id)
        await m.answer(render_table(rows))

    @dp.message(F.text)
    async def catch(m: Message):
        match = PROGRESS_RE.search(m.text or "")
        if not match:
            return

        done, goal = map(int, match.groups())
        if done > goal:
            return

        await save_progress(
            m.chat.id,
            m.from_user.id,
            m.from_user.full_name,
            done,
            goal
        )

        rows = await get_all(m.chat.id)
        await bot.send_message(m.chat.id, render_table(rows))

    scheduler = AsyncIOScheduler(timezone=TZ)
    scheduler.add_job(
        lambda: asyncio.create_task(
            bot.send_message(
                m.chat.id, render_table(await get_all(m.chat.id))
            )
        ),
        trigger="cron",
        day_of_week="mon",
        hour=9
    )
    scheduler.start()

    await dp.start_polling(bot)

asyncio.run(main())
