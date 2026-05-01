import os
import re
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

FOOTER_ID_RE = re.compile(r"id:(\S+)")


def make_active_embed(game: dict) -> discord.Embed:
    server_code = game.get("server", "?")
    gid = str(game["id"])
    embed = discord.Embed(title=f"🏰 {game.get('name', 'Unknown')}", color=discord.Color.gold())
    embed.add_field(name="🗺️ Map", value=game.get("map", "Unknown"), inline=True)
    embed.add_field(name="👤 Host", value=game.get("host", "Unknown"), inline=True)
    embed.add_field(name="🌍 Server", value=SERVER_NAMES.get(server_code, server_code.upper()), inline=True)
    embed.add_field(name="👥 Players", value=f"**{game.get('slotsTaken', 0)} / {game.get('slotsTotal', 0)}**", inline=True)
    if game.get("created"):
        embed.add_field(name="📅 Created", value=f"<t:{game['created']}:R>", inline=True)
    # Game ID stored in footer so the bot can recover state after a restart
    embed.set_footer(text=f"🔄 Last updated • id:{gid}")
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


async def restore_tracked(channel: discord.TextChannel) -> None:
    """Scan recent channel messages to rebuild tracked state after a restart."""
    async for msg in channel.history(limit=50):
        if msg.author != client.user or not msg.embeds:
            continue
        footer = msg.embeds[0].footer.text or ""
        match = FOOTER_ID_RE.search(footer)
        # Only restore active (gold) embeds, not closed ones
        if match and msg.embeds[0].color == discord.Color.gold():
            gid = match.group(1)
            if gid not in tracked:
                tracked[gid] = msg.id
                print(f"[INFO] Restored tracked lobby id={gid} from message {msg.id}")


@tasks.loop(seconds=POLL_INTERVAL)
async def poll():
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("[WARN] Channel not found — check DISCORD_CHANNEL_ID")
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(WC3STATS_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    print(f"[WARN] WC3Stats returned HTTP {resp.status}")
                    return
                data = await resp.json()
    except Exception as e:
        print(f"[ERROR] Fetch failed: {e}")
        return

    games = data.get("body", [])
    matching = {str(g["id"]): g for g in games if GAME_FILTER in g.get("name", "").upper()}

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
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await restore_tracked(channel)
    poll.start()


client.run(DISCORD_TOKEN)
