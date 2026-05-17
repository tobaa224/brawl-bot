import os
import json
import sqlite3
import requests
import discord
from discord.ext import tasks

# ======================
# CONFIG
# ======================

API_KEY = os.environ.get("BRAWLSTARS_API_KEY")
TOKEN = os.environ.get("DISCORD_TOKEN")

CLUB_TAG = "2QRL2UGPR"
CHANNEL_ID = 958351466937085

DB_FILE = "brawl.db"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}"
}

# ======================
# DATABASE
# ======================

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS players (
        tag TEXT PRIMARY KEY,
        name TEXT,
        trophies INTEGER,
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS club_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        data TEXT
    )
    """)

    conn.commit()
    conn.close()


def upsert_player(tag, name, trophies):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
    INSERT INTO players (tag, name, trophies)
    VALUES (?, ?, ?)
    ON CONFLICT(tag) DO UPDATE SET
        name=excluded.name,
        trophies=excluded.trophies,
        last_seen=CURRENT_TIMESTAMP
    """, (tag, name, trophies))

    conn.commit()
    conn.close()


def save_snapshot(data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
    INSERT INTO club_state (data)
    VALUES (?)
    """, (json.dumps(data),))

    conn.commit()
    conn.close()


def load_last_snapshot():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
    SELECT data FROM club_state
    ORDER BY id DESC
    LIMIT 1
    """)

    row = c.fetchone()
    conn.close()

    if row:
        return json.loads(row[0])

    return None

# ======================
# API
# ======================

def get_club_data():
    url = f"https://api.brawlstars.com/v1/clubs/%23{CLUB_TAG}"

    try:
        r = requests.get(url, headers=HEADERS, timeout=10)

        print("API STATUS:", r.status_code)

        if r.status_code != 200:
            print("API ERROR:", r.text)
            return {"members": []}

        data = r.json()

        members = []

        for m in data.get("members", []):
            members.append({
                "tag": m.get("tag"),
                "name": m.get("name"),
                "trophies": m.get("trophies", 0)
            })

        return {"members": members}

    except Exception as e:
        print("REQUEST ERROR:", e)
        return {"members": []}

# ======================
# LEADERBOARD
# ======================

def build_leaderboard(members, previous_snapshot=None):

    leaderboard = []

    for m in members:

        trophies = m["trophies"]
        change = 0

        if previous_snapshot:
            old = next(
                (
                    x for x in previous_snapshot.get("members", [])
                    if x["tag"] == m["tag"]
                ),
                None
            )

            if old:
                change = trophies - old.get("trophies", 0)

        leaderboard.append({
            "name": m["name"],
            "trophies": trophies,
            "change": change
        })

    # SORT BY PUSHED TROPHIES
    leaderboard.sort(key=lambda x: x["change"], reverse=True)

    lines = []
    lines.append("🏆 **Brawl Stars Leaderboard (Hourly Push)**\n")

    for i, p in enumerate(leaderboard[:27], 1):

        if i == 1:
            rank = "🥇"
        elif i == 2:
            rank = "🥈"
        elif i == 3:
            rank = "🥉"
        else:
            rank = f"#{i}"

        change_text = f"+{p['change']}" if p["change"] > 0 else str(p["change"])

        lines.append(
            f"{rank} **{p['name']}** — {change_text} 🏆 (total {p['trophies']})"
        )

    return "\n".join(lines)

# ======================
# DISCORD BOT
# ======================

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# ======================
# HOURLY LOOP
# ======================

@tasks.loop(hours=1)
async def hourly_update():

    print("🔄 Running hourly update...")

    # LOAD OLD SNAPSHOT FIRST
    previous = load_last_snapshot()

    # GET NEW DATA
    data = get_club_data()

    print("Members:", len(data["members"]))

    # UPDATE DB
    for p in data["members"]:
        upsert_player(
            p["tag"],
            p["name"],
            p["trophies"]
        )

    # BUILD LEADERBOARD
    msg = build_leaderboard(
        data["members"],
        previous
    )

    # SEND TO DISCORD
    try:
        channel = await client.fetch_channel(CHANNEL_ID)
        await channel.send(msg)

    except Exception as e:
        print("DISCORD ERROR:", e)

    # SAVE NEW SNAPSHOT LAST
    save_snapshot(data)

# ======================
# COMMANDS
# ======================

@client.event
async def on_message(message):

    if message.author.bot:
        return

    # MANUAL UPDATE TEST
    if message.content == "!test":

        previous = load_last_snapshot()
        data = get_club_data()

        msg = build_leaderboard(
            data["members"],
            previous
        )

        await message.channel.send(msg)

        save_snapshot(data)

    # DOWNLOAD DATABASE
    if message.content == "!db":

        await message.channel.send(
            file=discord.File(DB_FILE)
        )

# ======================
# READY
# ======================

@client.event
async def on_ready():

    print(f"✅ Logged in as {client.user}")

    init_db()

    if not hourly_update.is_running():
        hourly_update.start()

# ======================
# RUN
# ======================

client.run(TOKEN)
