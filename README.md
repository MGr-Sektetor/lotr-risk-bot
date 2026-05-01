# LOTR Risk Bot

Discord bot that monitors WC3Stats for active **LOTR RISK** lobbies and posts/updates a notification every 60 seconds.

When a lobby appears it posts an embed with the map name, host, player count, server, and uptime. The message is edited in-place every minute. When the lobby closes, it is marked as closed.

## Notification preview

```
🏰 LOTR RISK #1
🗺️ Map      LoTR Risk Reforged
👤 Host     SomePlayer#1234
🌍 Server   Europe
👥 Players  6 / 12
⏱️ Uptime   3m 22s
📅 Created  5 minutes ago
🔄 Last updated  [timestamp]
```

---

## Setup

### 1. Create a Discord bot

1. Go to https://discord.com/developers/applications → **New Application**
2. **Bot** tab → **Add Bot** → copy the token
3. **OAuth2 → URL Generator**: scopes `bot`, permissions `Send Messages` + `Embed Links` + `Read Message History`
4. Open the generated URL and invite the bot to your server
5. Right-click your notification channel → **Copy Channel ID** (enable Developer Mode in Discord settings first)

### 2. Run locally

```bash
pip install -r requirements.txt

# Windows
set DISCORD_TOKEN=your_token
set DISCORD_CHANNEL_ID=your_channel_id
python bot.py

# Linux / macOS
DISCORD_TOKEN=your_token DISCORD_CHANNEL_ID=your_channel_id python bot.py
```

Or with a `.env` file (copy `.env.example` → `.env` and fill in the values), then use `python-dotenv`:

```bash
pip install python-dotenv
```

Add to the top of `bot.py`:
```python
from dotenv import load_dotenv; load_dotenv()
```

### 3. Run with Docker

```bash
docker build -t lotr-risk-bot .

docker run -d \
  -e DISCORD_TOKEN=your_token \
  -e DISCORD_CHANNEL_ID=your_channel_id \
  lotr-risk-bot
```

---

## Free hosting — Fly.io

Fly.io offers a free tier with 3 shared VMs (256 MB RAM each). No credit card required for the free allowance. The bot uses ~30 MB RAM.

### One-time setup

```bash
# Install flyctl
# Windows (PowerShell):
iwr https://fly.io/install.ps1 -useb | iex

# macOS / Linux:
curl -L https://fly.io/install.sh | sh

fly auth signup   # or: fly auth login
```

### Deploy

```bash
# From the project root:
fly launch --name lotr-risk-bot --region ams --no-deploy

# Set secrets (never commit these)
fly secrets set DISCORD_TOKEN=your_token DISCORD_CHANNEL_ID=your_channel_id

# Deploy
fly deploy
```

### Useful commands

```bash
fly status          # check if it's running
fly logs            # stream live logs
fly secrets list    # list set secrets (values hidden)
fly scale count 1   # ensure 1 instance is running
```

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | Yes | — | Discord bot token |
| `DISCORD_CHANNEL_ID` | Yes | — | Channel to post notifications in |
| `GAME_FILTER` | No | `LOTR RISK` | Case-insensitive substring to match game names |
| `POLL_INTERVAL` | No | `60` | Seconds between polls |
