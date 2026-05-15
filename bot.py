import os
import json
import sqlite3
import requests
import discord
from discord.ext import tasks

# ======================
# CONFIG
# ======================

API_KEY = os.environ["BRAWLSTARS_API_KEY"]
TOKEN = os.environ["DISCORD_TOKEN"]

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


# ======================
# BRAWL STARS API
# ======================

def get_club_data():
    url = f"https://api.brawlstars.com/v1/clubs/%23{CLUB_TAG}"

    r = requests.get(url, headers=HEADERS)

    if r.status_code != 200:
        print("API ERROR:", r.text)
        return {"members": []}

    data = r.json()

    members = []

    for m in data.get("members", []):
        members.append({
            "tag": m["tag"],
            "name": m["name"],
            "trophies": m["trophies"]
        })

    return {"members": members}


# ======================
# DISCORD BOT
# ======================

intents = discord.Intents.default()
client = discord.Client(intents=intents)


@tasks.loop(hours=1)
async def hourly_update():
    print("Running hourly update...")

    data = get_club_data()

    for p in data["members"]:
        upsert_player(p["tag"], p["name"], p["trophies"])

    save_snapshot(data)

    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await channel.send("📊 Hourly update hotov!")


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    init_db()
    hourly_update.start()


# ======================
# RUN BOT
# ======================

TOKEN = os.environ["DISCORD_TOKEN"]
client.run(TOKEN)
