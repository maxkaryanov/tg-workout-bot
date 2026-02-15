import os
import re
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
NAME_WIDTH = 22

# ================== DATE HELPERS ==================

def now():
    return datetime.now(TZ)

def today():
    return now().date()

def week_start(d):
    return d - timedelta(days=d.weekday())

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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                chat_id INTEGER,
                user_id INTEGER,
                created TEXT
            )
        """)
        await db.commit()

async def save_event(chat_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO events VALUES (?, ?, ?)",
            (chat_id, user_id, now().isoformat(timespec="seconds"))
        )
        await db.commit()

async def save_progress(chat_id, user_id, name, done, goal):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO progress VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                name=excluded.name,
                done=excluded.done,
                goal=excluded.goal,
                updated=excluded.updated
        """, (
            chat_id, user_id, name, done, goal,
            now().isoformat(timespec="seconds")
        ))
        await db.commit()

async def get_all(chat_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT name, done, goal FROM progress WHERE chat_id=?",
            (chat_id,)
        ) as cur:
            return await cur.fetchall()

async def get_user_events(chat_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT created FROM events WHERE chat_id=? AND user_id=? ORDER BY created DESC",
            (chat_id, user_id)
        ) as cur:
            rows = await cur.fetchall()
            return [datetime.fromisoformat(r[0]).date() for r in rows]

# ================== MOTIVATION PHRASES ==================

def streak_phrase(days):
    phrases = {
        2: "Вторая тренировка подряд! Отличный ритм 💪",
        3: "Третья тренировка подряд! Ты входишь в режим 🔥",
        4: "Четвёртая тренировка подряд! Вот это дисциплина 👏",
        5: "Пятая тренировка подряд! Очень мощная серия 🚀",
        6: "Шестая тренировка подряд! Железная привычка 🦾",
        7: "Седьмой день подряд! Ты в топе по дисциплине 🥇",
    }
    if days in phrases:
        return phrases[days]
    if days > 7:
        return f"Серия {days} дней подряд! Это уже уровень профи 😎"
    return None

def weekly_phrase(count):
    phrases = {
        1: "Первая тренировка за неделю. Хорошее начало 👍",
        2: "Вторая тренировка за неделю. Двигаешься стабильно 👌",
        3: "Третья тренировка за неделю — это базовый минимум 💪",
        4: "Четвёртая тренировка за неделю — это выше среднего! 🔥",
        5: "Пятая тренировка за неделю! Ого! 🚀",
        6: "Шестая тренировка за неделю! Ого! Выше, чем у 90% участников 🏆",
        7: "Седьмая тренировка за неделю! Ты абсолютный монстр режима 🦾",
    }
    if count in phrases:
        return phrases[count]
    if count > 7:
        return f"Уже {count} тренировок за неделю?! Это уровень элиты 😎"
    return None

# ================== FORMAT ==================

def short_name(name):
    name = (name or "—").strip()
    return name if len(name) <= NAME_WIDTH else name[:NAME_WIDTH - 1] + "…"

def render_table(rows, title="🏁 Рейтинг обновлён"):
    lines = [title, "", "#  Участник — Сделано", "-" * 28]
    rows = sorted(rows, key=lambda r: -r[1])
    for i, (name, done, goal) in enumerate(rows, 1):
        lines.append(f"{i}. {short_name(name)} — {done}/{goal}")
    return "\n".join(lines)

# ================== MAIN ==================

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")

    await init_db()

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    last_chat_id = {"id": None}

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
        await save_event(m.chat.id, m.from_user.id)

        events = await get_user_events(m.chat.id, m.from_user.id)

        phrase = None
        if len(events) >= 2 and events[0] == events[1] + timedelta(days=1):
            streak = 1
            for i in range(len(events) - 1):
                if events[i] == events[i + 1] + timedelta(days=1):
                    streak += 1
                else:
                    break
            phrase = streak_phrase(streak)

        if not phrase:
            ws = week_start(today())
            weekly_count = sum(1 for d in events if d >= ws)
            phrase = weekly_phrase(weekly_count)

        rows = await get_all(m.chat.id)

        if phrase:
            await bot.send_message(m.chat.id, phrase + "\n\n" + render_table(rows))
        else:
            await bot.send_message(m.chat.id, render_table(rows))

    async def weekly_post(chat_id):
        rows = await get_all(chat_id)
        await bot.send_message(chat_id, render_table(rows, title="🏁 Рейтинг обновлён"))

    scheduler = AsyncIOScheduler(timezone=TZ)
    scheduler.add_job(
        lambda: asyncio.create_task(weekly_post(last_chat_id["id"]))
        if last_chat_id["id"] else None,
        trigger="cron",
        day_of_week="mon",
        hour=9,
        minute=0
    )
    scheduler.start()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
