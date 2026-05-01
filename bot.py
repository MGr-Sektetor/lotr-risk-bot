import os
import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import tasks
import aiohttp

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])
GAME_FILTER = os.environ.get("GAME_FILTER", "LOTR RISK").upper()
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))

WC3STATS_URL = "https://api.wc3stats.com/gamelist"

SERVER_NAMES = {
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


def uptime_str(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m"


def make_active_embed(game: dict) -> discord.Embed:
    name = game.get("name", "Unknown")
    map_name = game.get("map", "Unknown")
    host = game.get("host", "Unknown")
    taken = game.get("slotsTaken", 0)
    total = game.get("slotsTotal", 0)
    server_code = game.get("server", "?")
    server = SERVER_NAMES.get(server_code, server_code.upper())
    uptime = game.get("uptime", 0)
    created = game.get("created", 0)

    embed = discord.Embed(
        title=f"🏰 {name}",
        color=discord.Color.gold(),
    )
    embed.add_field(name="🗺️ Map", value=map_name, inline=True)
    embed.add_field(name="👤 Host", value=host, inline=True)
    embed.add_field(name="🌍 Server", value=server, inline=True)
    embed.add_field(name="👥 Players", value=f"**{taken} / {total}**", inline=True)
    embed.add_field(name="⏱️ Uptime", value=uptime_str(uptime), inline=True)

    if created:
        embed.add_field(
            name="📅 Created",
            value=f"<t:{created}:R>",
            inline=True,
        )

    embed.set_footer(text="🔄 Last updated")
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


@tasks.loop(seconds=POLL_INTERVAL)
async def poll():
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("[WARN] Channel not found — check DISCORD_CHANNEL_ID")
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                WC3STATS_URL, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    print(f"[WARN] WC3Stats returned HTTP {resp.status}")
                    return
                data = await resp.json()
    except Exception as e:
        print(f"[ERROR] Fetch failed: {e}")
        return

    games = data.get("body", [])
    matching = {
        str(g["id"]): g
        for g in games
        if GAME_FILTER in g.get("name", "").upper()
    }

    # Update or post messages for active lobbies
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
            print(f"[INFO] New lobby: {game.get('name')} (id={gid})")

    # Mark closed lobbies
    for gid in list(tracked.keys()):
        if gid not in matching:
            try:
                msg = await channel.fetch_message(tracked[gid])
                # Best-effort: get the last known name from the embed title
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
