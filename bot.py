import os
import json
import requests
import discord
import asyncio
from datetime import datetime, timezone
from discord.ext import tasks

API_KEY = os.environ["BRAWLSTARS_API_KEY"]
TOKEN = os.environ["DISCORD_TOKEN"]

CLUB_TAG = "2QRL2UGPR"
BASELINE_FILE = "baseline.json"

CHANNEL_ID = 958351466937085965  # 👈 sem dej ID kanálu

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


# --- FETCH CLUB ---
def get_members():
    url = f"https://api.brawlstars.com/v1/clubs/%23{CLUB_TAG}/members"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    r = requests.get(url, headers=headers)
    return r.json().get("items", [])


# --- BASELINE SYSTEM ---
def load_baseline():
    try:
        with open(BASELINE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_baseline(data):
    with open(BASELINE_FILE, "w") as f:
        json.dump(data, f)


def get_leaderboard():
    members = get_members()
    now = datetime.now(timezone.utc)
    current_hour = now.strftime("%Y-%m-%dT%H:00")

    baselines = load_baseline()

    if baselines.get("_hour") != current_hour:
        new_base = {"_hour": current_hour}
        for m in members:
            new_base[m["tag"]] = m["trophies"]
        save_baseline(new_base)
        baselines = new_base

    leaderboard = []

    for m in members:
        tag = m["tag"]
        current = m["trophies"]
        base = baselines.get(tag, current)
        pushed = current - base

        leaderboard.append({
            "name": m["name"],
            "trophies": current,
            "pushed": pushed
        })

    leaderboard.sort(key=lambda x: (-x["pushed"], -x["trophies"]))
    return leaderboard


# --- HOURLY POST ---
@tasks.loop(hours=1)
async def hourly_post():
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    if channel:
        board = get_leaderboard()

        medals = ["🥇", "🥈", "🥉"]
        lines = []

        for i, p in enumerate(board):
            rank = medals[i] if i < 3 else f"#{i+1}"
            push = f"+{p['pushed']}" if p["pushed"] > 0 else str(p["pushed"])

            lines.append(f"{rank} **{p['name']}** — {push} 🏆 (total {p['trophies']})")

        msg = "🏆 **Hourly Brawl Stars Leaderboard**\n\n" + "\n".join(lines)

        await channel.send(msg)


# --- EVENTS ---
@client.event
async def on_ready():
    print(f"Bot ready as {client.user}")
    hourly_post.start()


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content.startswith("!leaderboard"):
        board = get_leaderboard()

        medals = ["🥇", "🥈", "🥉"]
        lines = []

        for i, p in enumerate(board):
            rank = medals[i] if i < 3 else f"#{i+1}"
            push = f"+{p['pushed']}" if p["pushed"] > 0 else str(p["pushed"])

            lines.append(
                f"{rank} **{p['name']}** — {push} 🏆 (total {p['trophies']})"
            )

        msg = "🏆 **Brawl Stars Leaderboard (Hourly Push)**\n\n" + "\n".join(lines)

        await message.channel.send(msg)


client.run(TOKEN)
