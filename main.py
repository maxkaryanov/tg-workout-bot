{\rtf1\ansi\ansicpg1251\cocoartf2818
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\paperw11900\paperh16840\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx566\tx1133\tx1700\tx2267\tx2834\tx3401\tx3968\tx4535\tx5102\tx5669\tx6236\tx6803\pardirnatural\partightenfactor0

\f0\fs24 \cf0 import os\
import re\
import math\
import asyncio\
from datetime import datetime\
from zoneinfo import ZoneInfo\
\
import aiosqlite\
from aiogram import Bot, Dispatcher, F\
from aiogram.types import Message\
from aiogram.filters import Command\
from apscheduler.schedulers.asyncio import AsyncIOScheduler\
\
DB_PATH = os.getenv("DB_PATH", "bot.db")\
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()\
TZ_NAME = os.getenv("TZ", "Europe/Helsinki")\
TZ = ZoneInfo(TZ_NAME)\
\
# \uc0\u1045 \u1089 \u1083 \u1080  \u1079 \u1072 \u1076 \u1072 \u1085  \'97 \u1073 \u1086 \u1090  \u1073 \u1091 \u1076 \u1077 \u1090  \u1087 \u1086 \u1089 \u1090 \u1080 \u1090 \u1100  \u1072 \u1074 \u1090 \u1086 \u1089 \u1074 \u1086 \u1076 \u1082 \u1080  \u1074 \u1089 \u1077 \u1075 \u1076 \u1072  \u1089 \u1102 \u1076 \u1072 . \u1045 \u1089 \u1083 \u1080  \u1085 \u1077 \u1090  \'97 \u1079 \u1072 \u1087 \u1086 \u1084 \u1085 \u1080 \u1090  \u1095 \u1072 \u1090  \u1087 \u1086  \u1087 \u1077 \u1088 \u1074 \u1099 \u1084  \u1076 \u1072 \u1085 \u1085 \u1099 \u1084 .\
TARGET_CHAT_ID = os.getenv("TARGET_CHAT_ID")\
TARGET_CHAT_ID = int(TARGET_CHAT_ID) if TARGET_CHAT_ID else None\
\
# (\uc0\u1086 \u1087 \u1094 \u1080 \u1086 \u1085 \u1072 \u1083 \u1100 \u1085 \u1086 ) \u1072 \u1076 \u1084 \u1080 \u1085 \u1099  \u1076 \u1083 \u1103  /setchat\
ADMIN_IDS = set()\
_admin_raw = os.getenv("ADMIN_IDS", "").strip()\
if _admin_raw:\
    ADMIN_IDS = \{int(x.strip()) for x in _admin_raw.split(",") if x.strip().isdigit()\}\
\
# \uc0\u1048 \u1097 \u1077 \u1084  \u1087 \u1077 \u1088 \u1074 \u1086 \u1077  \u1074 \u1093 \u1086 \u1078 \u1076 \u1077 \u1085 \u1080 \u1077  X/Y \u1074  \u1090 \u1077 \u1082 \u1089 \u1090 \u1077 \
PROGRESS_RE = re.compile(r"(?<!\\d)(\\d\{1,5\})\\s*/\\s*(\\d\{1,5\})(?!\\d)")\
\
# \uc0\u1063 \u1090 \u1086 \u1073 \u1099  \u1073 \u1086 \u1090  \u1085 \u1077  \u1092 \u1083 \u1091 \u1076 \u1080 \u1083  \u1089 \u1083 \u1080 \u1096 \u1082 \u1086 \u1084  \u1095 \u1072 \u1089 \u1090 \u1086  (\u1085 \u1072 \u1087 \u1088 \u1080 \u1084 \u1077 \u1088 , \u1077 \u1089 \u1083 \u1080  \u1085 \u1077 \u1089 \u1082 \u1086 \u1083 \u1100 \u1082 \u1086  \u1089 \u1086 \u1086 \u1073 \u1097 \u1077 \u1085 \u1080 \u1081  \u1087 \u1086 \u1076 \u1088 \u1103 \u1076 )\
POST_COOLDOWN_SECONDS = int(os.getenv("POST_COOLDOWN_SECONDS", "15"))\
\
def now_tz() -> datetime:\
    return datetime.now(TZ)\
\
def next_jan_1_deadline(ref: datetime) -> datetime:\
    # \uc0\u1062 \u1077 \u1083 \u1100  \u1076 \u1086 \u1083 \u1078 \u1085 \u1072  \u1073 \u1099 \u1090 \u1100  \u1076 \u1086 \u1089 \u1090 \u1080 \u1075 \u1085 \u1091 \u1090 \u1072  "\u1076 \u1086  1 \u1103 \u1085 \u1074 \u1072 \u1088 \u1103 " \'97 \u1073 \u1077 \u1088 \u1105 \u1084  1 \u1103 \u1085 \u1074 \u1072 \u1088 \u1103  \u1089 \u1083 \u1077 \u1076 \u1091 \u1102 \u1097 \u1077 \u1075 \u1086  \u1075 \u1086 \u1076 \u1072 \
    return datetime(ref.year + 1, 1, 1, 0, 0, 0, tzinfo=TZ)\
\
def weeks_left_to_deadline(ref: datetime) -> int:\
    deadline = next_jan_1_deadline(ref)\
    delta_days = (deadline.date() - ref.date()).days\
    if delta_days <= 0:\
        return 0\
    return max(1, math.ceil(delta_days / 7))\
\
def fmt_pct(x: int, y: int) -> int:\
    if y <= 0:\
        return 0\
    return int(round((x / y) * 100))\
\
def display_name(msg: Message) -> str:\
    u = msg.from_user\
    if not u:\
        return "Unknown"\
    return u.full_name or u.username or str(u.id)\
\
async def init_db():\
    async with aiosqlite.connect(DB_PATH) as db:\
        await db.execute("""\
            CREATE TABLE IF NOT EXISTS progress (\
                chat_id INTEGER NOT NULL,\
                user_id INTEGER NOT NULL,\
                name TEXT NOT NULL,\
                x INTEGER NOT NULL,\
                y INTEGER NOT NULL,\
                updated_at TEXT NOT NULL,\
                PRIMARY KEY (chat_id, user_id)\
            )\
        """)\
        await db.execute("""\
            CREATE TABLE IF NOT EXISTS settings (\
                key TEXT PRIMARY KEY,\
                value TEXT NOT NULL\
            )\
        """)\
        await db.commit()\
\
async def set_setting(key: str, value: str):\
    async with aiosqlite.connect(DB_PATH) as db:\
        await db.execute(\
            "INSERT INTO settings(key, value) VALUES(?, ?) "\
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",\
            (key, value),\
        )\
        await db.commit()\
\
async def get_setting(key: str):\
    async with aiosqlite.connect(DB_PATH) as db:\
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:\
            row = await cur.fetchone()\
            return row[0] if row else None\
\
async def upsert_progress(chat_id: int, user_id: int, name: str, x: int, y: int):\
    now = now_tz().isoformat(timespec="seconds")\
    async with aiosqlite.connect(DB_PATH) as db:\
        await db.execute("""\
            INSERT INTO progress(chat_id, user_id, name, x, y, updated_at)\
            VALUES(?, ?, ?, ?, ?, ?)\
            ON CONFLICT(chat_id, user_id) DO UPDATE SET\
                name=excluded.name,\
                x=excluded.x,\
                y=excluded.y,\
                updated_at=excluded.updated_at\
        """, (chat_id, user_id, name, x, y, now))\
        await db.commit()\
\
async def get_user_progress(chat_id: int, user_id: int):\
    async with aiosqlite.connect(DB_PATH) as db:\
        async with db.execute("""\
            SELECT name, x, y, updated_at\
            FROM progress\
            WHERE chat_id = ? AND user_id = ?\
        """, (chat_id, user_id)) as cur:\
            return await cur.fetchone()\
\
async def get_all(chat_id: int):\
    async with aiosqlite.connect(DB_PATH) as db:\
        async with db.execute("""\
            SELECT name, x, y, updated_at\
            FROM progress\
            WHERE chat_id = ?\
        """, (chat_id,)) as cur:\
            return await cur.fetchall()\
\
async def ensure_chat_for_autopost(chat_id: int):\
    if TARGET_CHAT_ID is None:\
        await set_setting("autopost_chat_id", str(chat_id))\
\
async def get_autopost_chat_id() -> int | None:\
    if TARGET_CHAT_ID is not None:\
        return TARGET_CHAT_ID\
    v = await get_setting("autopost_chat_id")\
    return int(v) if v and v.lstrip("-").isdigit() else None\
\
def compute_needed_per_week(x: int, y: int, weeks_left: int) -> int:\
    remaining = max(0, y - x)\
    if remaining == 0:\
        return 0\
    if weeks_left <= 0:\
        return remaining  # \uc0\u1076 \u1077 \u1076 \u1083 \u1072 \u1081 \u1085  \u1091 \u1078 \u1077  \u1085 \u1072 \u1089 \u1090 \u1091 \u1087 \u1080 \u1083  \'97 \u1087 \u1086 \u1082 \u1072 \u1079 \u1099 \u1074 \u1072 \u1077 \u1084 , \u1089 \u1082 \u1086 \u1083 \u1100 \u1082 \u1086  \u1085 \u1077  \u1089 \u1076 \u1077 \u1083 \u1072 \u1085 \u1086 \
    return math.ceil(remaining / weeks_left)\
\
def format_leaderboard(rows, title: str):\
    ref = now_tz()\
    weeks_left = weeks_left_to_deadline(ref)\
    deadline = next_jan_1_deadline(ref).date().isoformat()\
\
    if not rows:\
        return f"\{title\}\\n\\n\uc0\u1055 \u1086 \u1082 \u1072  \u1085 \u1077 \u1090  \u1076 \u1072 \u1085 \u1085 \u1099 \u1093 . \u1055 \u1080 \u1096 \u1080 \u1090 \u1077  \u1087 \u1088 \u1086 \u1075 \u1088 \u1077 \u1089 \u1089  \u1074  \u1092 \u1086 \u1088 \u1084 \u1072 \u1090 \u1077  12/150."\
\
    # \uc0\u1089 \u1086 \u1088 \u1090 \u1080 \u1088 \u1086 \u1074 \u1082 \u1072 : X desc, % desc, updated_at asc\
    def sort_key(r):\
        name, x, y, updated_at = r\
        pct = (x / y) if y else 0\
        return (-x, -pct, updated_at)\
\
    rows = list(rows)\
    rows.sort(key=sort_key)\
\
    header = [\
        title,\
        f"\uc0\u1044 \u1077 \u1076 \u1083 \u1072 \u1081 \u1085 : \{deadline\} \'95 \u1085 \u1077 \u1076 \u1077 \u1083 \u1100  \u1086 \u1089 \u1090 \u1072 \u1083 \u1086 \u1089 \u1100 : \{weeks_left\}" if weeks_left > 0 else f"\u1044 \u1077 \u1076 \u1083 \u1072 \u1081 \u1085 : \{deadline\} (\u1091 \u1078 \u1077  \u1085 \u1072 \u1089 \u1090 \u1091 \u1087 \u1080 \u1083 )",\
        "",\
        " #  \uc0\u1059 \u1095 \u1072 \u1089 \u1090 \u1085 \u1080 \u1082                \u1055 \u1088 \u1086 \u1075 \u1088 \u1077 \u1089 \u1089    \u1054 \u1089 \u1090 \u1072 \u1083 \u1086 \u1089 \u1100   /\u1085 \u1077 \u1076 ",\
    ]\
\
    lines = []\
    for i, (name, x, y, _updated_at) in enumerate(rows, start=1):\
        remaining = max(0, y - x)\
        per_week = compute_needed_per_week(x, y, weeks_left)\
        short = (name[:18] + "\'85") if len(name) > 19 else name\
        lines.append(f"\{i:>2\}  \{short:<20\}  \{x:>3\}/\{y:<3\}   \{remaining:>5\}   \{per_week:>3\}")\
\
    return "\\n".join(header + lines)\
\
async def weekly_post(bot: Bot):\
    chat_id = await get_autopost_chat_id()\
    if not chat_id:\
        return\
    rows = await get_all(chat_id)\
    text = format_leaderboard(rows, title="\uc0\u55356 \u57291 \u65039  \u1051 \u1080 \u1076 \u1077 \u1088 \u1073 \u1086 \u1088 \u1076  \u1085 \u1077 \u1076 \u1077 \u1083 \u1080 ")\
    await bot.send_message(chat_id, text)\
\
async def should_post_now() -> bool:\
    # \uc0\u1072 \u1085 \u1090 \u1080 \u1092 \u1083 \u1091 \u1076 : \u1085 \u1077  \u1095 \u1072 \u1097 \u1077  \u1095 \u1077 \u1084  \u1088 \u1072 \u1079  \u1074  N \u1089 \u1077 \u1082 \u1091 \u1085 \u1076 \
    last = await get_setting("last_post_ts")\
    now_ts = int(now_tz().timestamp())\
    if not last:\
        await set_setting("last_post_ts", str(now_ts))\
        return True\
    try:\
        last_ts = int(last)\
    except ValueError:\
        await set_setting("last_post_ts", str(now_ts))\
        return True\
    if now_ts - last_ts >= POST_COOLDOWN_SECONDS:\
        await set_setting("last_post_ts", str(now_ts))\
        return True\
    return False\
\
async def main():\
    if not BOT_TOKEN:\
        raise RuntimeError("BOT_TOKEN is empty. Set it in Render environment variables.")\
\
    await init_db()\
\
    bot = Bot(token=BOT_TOKEN)\
    dp = Dispatcher()\
\
    @dp.message(Command("top"))\
    async def cmd_top(message: Message):\
        rows = await get_all(message.chat.id)\
        await message.reply(format_leaderboard(rows, title="\uc0\u55356 \u57291 \u65039  \u1051 \u1080 \u1076 \u1077 \u1088 \u1073 \u1086 \u1088 \u1076 "))\
\
    @dp.message(Command("me"))\
    async def cmd_me(message: Message):\
        row = await get_user_progress(message.chat.id, message.from_user.id)\
        if not row:\
            await message.reply("\uc0\u1055 \u1086 \u1082 \u1072  \u1085 \u1077 \u1090  \u1090 \u1074 \u1086 \u1080 \u1093  \u1076 \u1072 \u1085 \u1085 \u1099 \u1093 . \u1053 \u1072 \u1087 \u1080 \u1096 \u1080  \u1087 \u1088 \u1086 \u1075 \u1088 \u1077 \u1089 \u1089  \u1074  \u1092 \u1086 \u1088 \u1084 \u1072 \u1090 \u1077  12/150.")\
            return\
        name, x, y, updated_at = row\
        remaining = max(0, y - x)\
        weeks_left = weeks_left_to_deadline(now_tz())\
        per_week = compute_needed_per_week(x, y, weeks_left)\
        pct = fmt_pct(x, y)\
        deadline = next_jan_1_deadline(now_tz()).date().isoformat()\
        await message.reply(\
            f"\uc0\u55357 \u56420  \{name\}\\n"\
            f"\uc0\u1055 \u1088 \u1086 \u1075 \u1088 \u1077 \u1089 \u1089 : \{x\}/\{y\} (\{pct\}%)\\n"\
            f"\uc0\u1054 \u1089 \u1090 \u1072 \u1083 \u1086 \u1089 \u1100 : \{remaining\}\\n"\
            f"\uc0\u1053 \u1091 \u1078 \u1085 \u1086  \u1074  \u1085 \u1077 \u1076 \u1077 \u1083 \u1102 : \{per_week\}\\n"\
            f"\uc0\u1044 \u1077 \u1076 \u1083 \u1072 \u1081 \u1085 : \{deadline\}\\n"\
            f"\uc0\u1054 \u1073 \u1085 \u1086 \u1074 \u1083 \u1077 \u1085 \u1086 : \{updated_at\}"\
        )\
\
    @dp.message(Command("setchat"))\
    async def cmd_setchat(message: Message):\
        if ADMIN_IDS and (message.from_user.id not in ADMIN_IDS):\
            await message.reply("\uc0\u1050 \u1086 \u1084 \u1072 \u1085 \u1076 \u1072  \u1076 \u1086 \u1089 \u1090 \u1091 \u1087 \u1085 \u1072  \u1090 \u1086 \u1083 \u1100 \u1082 \u1086  \u1072 \u1076 \u1084 \u1080 \u1085 \u1072 \u1084 .")\
            return\
        if TARGET_CHAT_ID is not None:\
            await message.reply("TARGET_CHAT_ID \uc0\u1079 \u1072 \u1076 \u1072 \u1085  \u1074  \u1087 \u1077 \u1088 \u1077 \u1084 \u1077 \u1085 \u1085 \u1099 \u1093  \u1086 \u1082 \u1088 \u1091 \u1078 \u1077 \u1085 \u1080 \u1103 , /setchat \u1085 \u1077  \u1085 \u1091 \u1078 \u1077 \u1085 .")\
            return\
        await set_setting("autopost_chat_id", str(message.chat.id))\
        await message.reply("\uc0\u9989  \u1054 \u1082 , \u1101 \u1090 \u1086 \u1090  \u1095 \u1072 \u1090  \u1074 \u1099 \u1073 \u1088 \u1072 \u1085  \u1076 \u1083 \u1103  \u1072 \u1074 \u1090 \u1086 \u1087 \u1086 \u1089 \u1090 \u1086 \u1074  (\u1087 \u1086 \u1085 \u1077 \u1076 \u1077 \u1083 \u1100 \u1085 \u1080 \u1082  + \u1072 \u1074 \u1090 \u1086 \u1086 \u1073 \u1085 \u1086 \u1074 \u1083 \u1077 \u1085 \u1080 \u1103 ).")\
\
    @dp.message(F.text)\
    async def catch_progress(message: Message):\
        m = PROGRESS_RE.search(message.text or "")\
        if not m:\
            return\
\
        x = int(m.group(1))\
        y = int(m.group(2))\
\
        # \uc0\u1087 \u1088 \u1086 \u1089 \u1090 \u1072 \u1103  \u1074 \u1072 \u1083 \u1080 \u1076 \u1072 \u1094 \u1080 \u1103 \
        if y < 1 or y > 10000:\
            return\
        if x < 0 or x > y:\
            return\
\
        chat_id = message.chat.id\
        user_id = message.from_user.id\
        name = display_name(message)\
\
        await upsert_progress(chat_id, user_id, name, x, y)\
        await ensure_chat_for_autopost(chat_id)\
\
        # \uc0\u1040 \u1074 \u1090 \u1086 \u1087 \u1086 \u1089 \u1090  \u1088 \u1077 \u1081 \u1090 \u1080 \u1085 \u1075 \u1072  \u1089 \u1088 \u1072 \u1079 \u1091  \u1087 \u1086 \u1089 \u1083 \u1077  \u1086 \u1073 \u1085 \u1086 \u1074 \u1083 \u1077 \u1085 \u1080 \u1103 \
        if await should_post_now():\
            rows = await get_all(chat_id)\
            text = format_leaderboard(rows, title="\uc0\u55356 \u57281  \u1056 \u1077 \u1081 \u1090 \u1080 \u1085 \u1075  \u1086 \u1073 \u1085 \u1086 \u1074 \u1083 \u1105 \u1085 ")\
            await bot.send_message(chat_id, text)\
\
    # \uc0\u1045 \u1078 \u1077 \u1085 \u1077 \u1076 \u1077 \u1083 \u1100 \u1085 \u1099 \u1081  \u1072 \u1074 \u1090 \u1086 \u1087 \u1086 \u1089 \u1090  \u1087 \u1086  \u1087 \u1086 \u1085 \u1077 \u1076 \u1077 \u1083 \u1100 \u1085 \u1080 \u1082 \u1072 \u1084  09:00 (Europe/Helsinki)\
    scheduler = AsyncIOScheduler(timezone=TZ)\
    scheduler.add_job(lambda: asyncio.create_task(weekly_post(bot)),\
                      trigger="cron", day_of_week="mon", hour=9, minute=0)\
    scheduler.start()\
\
    await dp.start_polling(bot)\
\
if __name__ == "__main__":\
    asyncio.run(main())\
}