import os
import re
from datetime import datetime, timezone

import discord
from discord.ext import tasks
import aiohttp

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])
MAP_FILTER = os.environ.get("MAP_FILTER", "LOTR RISK").upper()
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))

WC3STATS_URL = "https://api.wc3stats.com/gamelist"
WC3MAPS_URL = "https://wc3maps.com/api/lobbies"

SERVER_NAMES = {
    "usw": "US West",
    "use": "US East",
    "eu": "Europe",
    "kr": "Korea",
    "as": "Asia",
}

intents = discord.Intents.default()
client = discord.Client(intents=intents)

# Lobbies we have already posted about (id -> message id). Never removed so
# we never re-post the same lobby even if it briefly disappears from the API.
posted: dict[str, int] = {}

# Last known game data for active lobbies, used to get player count on close.
last_seen: dict[str, dict] = {}


FOOTER_ID_RE = re.compile(r"id:(\S+)")


def make_active_embed(game: dict) -> discord.Embed:
    server_code = game.get("server", "?")
    gid = str(game["id"])
    embed = discord.Embed(title=f"🏰 {game.get('name', 'Unknown')}", color=discord.Color.green())
    embed.add_field(name="🗺️ Map", value=game.get("map", "Unknown"), inline=True)
    embed.add_field(name="👤 Host", value=game.get("host", "Unknown"), inline=True)
    embed.add_field(name="🌍 Server", value=SERVER_NAMES.get(server_code, server_code.upper()), inline=True)
    embed.add_field(name="👥 Players", value=f"**{game.get('slotsTaken', 0)} / {game.get('slotsTotal', 0)}**", inline=True)
    if game.get("created"):
        embed.add_field(name="📅 Created", value=f"<t:{game['created']}:R>", inline=True)
    embed.set_footer(text=f"id:{gid}")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


def make_closed_embed(game: dict) -> discord.Embed:
    name = game.get("name", "LOTR RISK")
    taken = game.get("slotsTaken", 0)
    total = game.get("slotsTotal", 0)
    embed = discord.Embed(
        title=f"🔒 {name} — Closed",
        color=discord.Color.dark_gray(),
    )
    embed.add_field(name="🗺️ Map", value=game.get("map", "Unknown"), inline=True)
    embed.add_field(name="👤 Host", value=game.get("host", "Unknown"), inline=True)
    embed.add_field(name="👥 Players at close", value=f"{taken} / {total}", inline=True)
    embed.set_footer(text=f"id:{game['id']}")
    embed.timestamp = datetime.now(timezone.utc)
    return embed


def _normalize_wc3maps(g: dict) -> dict:
    """Convert a wc3maps game object to wc3stats field names.

    wc3maps assigns a new numeric id whenever a player joins, so we derive a
    stable id from host+region — a player can only host one game at a time.
    """
    host = g.get("host", "Unknown")
    region = g.get("region", "?")
    return {
        "id": f"wc3maps-{host}-{region}",
        "name": g.get("name", "Unknown"),
        "map": g.get("path", "Unknown"),
        "host": host,
        "server": region,
        "slotsTaken": g.get("slots_taken", 0),
        "slotsTotal": g.get("slots_total", 0),
        "created": g.get("created"),
    }


async def _fetch_wc3stats() -> list[dict] | None:
    """Returns game list on success, None on any error."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(WC3STATS_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    print(f"[WARN] WC3Stats returned HTTP {resp.status}")
                    return None
                data = await resp.json()
                return data.get("body", [])
    except Exception as e:
        print(f"[ERROR] WC3Stats fetch failed: {e}")
        return None


async def _fetch_wc3maps() -> list[dict] | None:
    """Returns normalised game list on success, None on any error."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(WC3MAPS_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    print(f"[WARN] wc3maps returned HTTP {resp.status}")
                    return None
                data = await resp.json(content_type=None)
                games = [_normalize_wc3maps(g) for g in data.get("data", [])]
                print(f"[INFO] wc3maps returned {len(games)} games")
                return games
    except Exception as e:
        print(f"[ERROR] wc3maps fetch failed: {e}")
        return None


async def fetch_games() -> list[dict] | None:
    """Try WC3Stats first. Fall back to wc3maps.com on error."""
    games = await _fetch_wc3stats()
    if games:
        return games
    print("[WARN] WC3Stats unavailable, falling back to wc3maps.com")
    return await _fetch_wc3maps()


async def restore_posted(channel: discord.TextChannel) -> None:
    """On startup, scan recent messages to restore state and delete duplicates.

    channel.history() returns newest-first, so the first message we find for
    a given lobby id is the most recent one — that's the one we keep.
    Any older messages with the same id are duplicates and get deleted.
    """
    async for msg in channel.history(limit=100):
        if msg.author != client.user or not msg.embeds:
            continue
        footer = msg.embeds[0].footer.text or ""
        match = FOOTER_ID_RE.search(footer)
        if not match:
            # No id in footer — orphan from old bot code, delete it
            try:
                await msg.delete()
                print(f"[INFO] Deleted orphaned message {msg.id}")
            except Exception as e:
                print(f"[WARN] Could not delete orphan: {e}")
            continue
        gid = match.group(1)
        if gid not in posted:
            posted[gid] = msg.id
            print(f"[INFO] Restored posted lobby id={gid}")
        else:
            # Duplicate — delete the older message
            try:
                await msg.delete()
                print(f"[INFO] Deleted duplicate message for lobby id={gid}")
            except Exception as e:
                print(f"[WARN] Could not delete duplicate: {e}")


@tasks.loop(seconds=POLL_INTERVAL)
async def poll():
    try:
        channel = client.get_channel(CHANNEL_ID)
        if channel is None:
            print("[WARN] Channel not found — check DISCORD_CHANNEL_ID")
            return

        games = await fetch_games()
        if games is None:
            return

        matching = {str(g["id"]): g for g in games if MAP_FILTER in g.get("map", "").upper()}

        # Update last_seen, post new lobbies, edit existing ones
        for gid, game in matching.items():
            if gid not in last_seen:
                if gid not in posted:
                    msg = await channel.send(embed=make_active_embed(game))
                    posted[gid] = msg.id
                    print(f"[INFO] New lobby: {game.get('name')} (id={gid})")
            else:
                try:
                    msg = await channel.fetch_message(posted[gid])
                    await msg.edit(embed=make_active_embed(game))
                except (discord.NotFound, discord.HTTPException):
                    pass
            last_seen[gid] = game

        # Detect closed lobbies
        for gid in list(last_seen.keys()):
            if gid not in matching:
                game = last_seen.pop(gid)
                if gid in posted:
                    try:
                        msg = await channel.fetch_message(posted[gid])
                        await msg.edit(embed=make_closed_embed(game))
                        print(f"[INFO] Lobby closed (id={gid})")
                    except Exception as e:
                        print(f"[WARN] Could not mark lobby {gid} as closed: {e}")
    except Exception as e:
        print(f"[ERROR] Poll iteration failed: {e}")


@poll.before_loop
async def before_poll():
    await client.wait_until_ready()


@client.event
async def on_ready():
    print(f"[INFO] Logged in as {client.user} — polling every {POLL_INTERVAL}s for map '{MAP_FILTER}'")
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await restore_posted(channel)
    poll.start()


client.run(DISCORD_TOKEN)
