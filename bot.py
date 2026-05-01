import os
from datetime import datetime, timezone

import discord
from discord.ext import tasks
import aiohttp

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])
GAME_FILTER = os.environ.get("GAME_FILTER", "LOTR RISK").upper()
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))

WC3STATS_URL = "https://api.wc3stats.com/gamelist"
ENT_URL = "https://host.entgaming.net/allgames"

WC3STATS_SERVER_NAMES = {
    "usw": "US West",
    "use": "US East",
    "eu": "Europe",
    "kr": "Korea",
    "as": "Asia",
}

intents = discord.Intents.default()
client = discord.Client(intents=intents)

# game id (str) -> discord message id (int)
tracked: dict[str, int] = {}


# --- API normalisation ---

def _ent_uptime_to_seconds(uptime: str) -> int:
    """Convert ENT uptime string 'H:MM' to seconds."""
    try:
        parts = uptime.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 3600 + int(parts[1]) * 60
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except (ValueError, AttributeError):
        pass
    return 0


def _normalise_wc3stats(game: dict) -> dict:
    server_code = game.get("server", "?")
    return {
        "id": str(game["id"]),
        "name": game.get("name", "Unknown"),
        "map": game.get("map", "Unknown"),
        "host": game.get("host", "Unknown"),
        "slots_taken": game.get("slotsTaken", 0),
        "slots_total": game.get("slotsTotal", 0),
        "server": WC3STATS_SERVER_NAMES.get(server_code, server_code.upper()),
        "uptime": game.get("uptime", 0),
        "created": game.get("created", 0),
        "source": "WC3Stats",
    }


def _normalise_ent(game: dict) -> dict:
    return {
        "id": f"ent-{game['id']}",
        "name": game.get("name", "Unknown"),
        "map": game.get("map", "Unknown"),
        "host": game.get("host") or "ENT Bot",
        "slots_taken": game.get("slots_taken", 0),
        "slots_total": game.get("slots_total", 0),
        "server": game.get("location", "Unknown"),
        "uptime": _ent_uptime_to_seconds(game.get("uptime", "0:00")),
        "created": 0,
        "source": "WC3Connect",
    }


async def fetch_games(session: aiohttp.ClientSession) -> tuple[list[dict], str]:
    """Try WC3Stats first, fall back to ENT. Returns (games, source_label)."""
    try:
        async with session.get(WC3STATS_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                data = await resp.json()
                games = [_normalise_wc3stats(g) for g in data.get("body", [])]
                return games, "WC3Stats"
            print(f"[WARN] WC3Stats returned HTTP {resp.status}, trying ENT fallback")
    except Exception as e:
        print(f"[WARN] WC3Stats failed ({e}), trying ENT fallback")

    try:
        async with session.get(ENT_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                data = await resp.json()
                games = [_normalise_ent(g) for g in data]
                return games, "WC3Connect"
            print(f"[WARN] ENT returned HTTP {resp.status}")
    except Exception as e:
        print(f"[ERROR] ENT fallback also failed: {e}")

    return [], ""


# --- Discord embeds ---

def uptime_str(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m"


def make_active_embed(game: dict) -> discord.Embed:
    embed = discord.Embed(title=f"🏰 {game['name']}", color=discord.Color.gold())
    embed.add_field(name="🗺️ Map", value=game["map"], inline=True)
    embed.add_field(name="👤 Host", value=game["host"], inline=True)
    embed.add_field(name="🌍 Server", value=game["server"], inline=True)
    embed.add_field(name="👥 Players", value=f"**{game['slots_taken']} / {game['slots_total']}**", inline=True)
    embed.add_field(name="⏱️ Uptime", value=uptime_str(game["uptime"]), inline=True)

    if game["created"]:
        embed.add_field(name="📅 Created", value=f"<t:{game['created']}:R>", inline=True)

    embed.set_footer(text=f"🔄 Last updated • Source: {game['source']}")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


def make_closed_embed(name: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"🔒 {name} — Closed",
        description="This lobby is no longer available.",
        color=discord.Color.dark_gray(),
    )
    embed.timestamp = datetime.now(timezone.utc)
    return embed


# --- Polling task ---

@tasks.loop(seconds=POLL_INTERVAL)
async def poll():
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("[WARN] Channel not found — check DISCORD_CHANNEL_ID")
        return

    async with aiohttp.ClientSession() as session:
        games, source = await fetch_games(session)

    if not source:
        print("[ERROR] Both APIs failed, skipping this poll")
        return

    matching = {
        g["id"]: g for g in games if GAME_FILTER in g["name"].upper()
    }

    for gid, game in matching.items():
        embed = make_active_embed(game)
        if gid in tracked:
            try:
                msg = await channel.fetch_message(tracked[gid])
                await msg.edit(embed=embed)
            except discord.NotFound:
                msg = await channel.send(embed=embed)
                tracked[gid] = msg.id
        else:
            msg = await channel.send(embed=embed)
            tracked[gid] = msg.id
            print(f"[INFO] New lobby via {source}: {game['name']} (id={gid})")

    for gid in list(tracked.keys()):
        if gid not in matching:
            try:
                msg = await channel.fetch_message(tracked[gid])
                old_name = "LOTR RISK"
                if msg.embeds:
                    title = msg.embeds[0].title or ""
                    old_name = title.lstrip("🏰 ").strip() or old_name
                await msg.edit(embed=make_closed_embed(old_name))
            except Exception as e:
                print(f"[WARN] Could not update closed lobby {gid}: {e}")
            del tracked[gid]
            print(f"[INFO] Lobby closed (id={gid})")


@poll.before_loop
async def before_poll():
    await client.wait_until_ready()


@client.event
async def on_ready():
    print(f"[INFO] Logged in as {client.user} — polling every {POLL_INTERVAL}s for '{GAME_FILTER}'")
    poll.start()


client.run(DISCORD_TOKEN)
