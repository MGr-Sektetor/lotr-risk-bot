# LOTR Risk Bot

Discord bot that monitors [WC3Stats](https://api.wc3stats.com/gamelist) for active **LOTR RISK** lobbies and posts a notification in a Discord channel.

## Behaviour

- **New lobby** — posts a new embed at the bottom of the channel
- **Active lobby** — edits the embed every 60 seconds with the latest player count
- **Lobby closes** — edits the embed to a grey "Closed" state, keeping the final player count
- **Restart-safe** — on startup the bot scans the last 100 channel messages to restore state, so it never re-posts a lobby it already knows about

## Notification preview

```
🏰 LOTR RISK
🗺️ Map      Lotr Risk S 2.11.0.w3x
👤 Host     RANDOM#2269
🌍 Server   Europe
👥 Players  6 / 24
📅 Created  3 minutes ago
```

When closed:
```
🔒 LOTR RISK — Closed
👥 Players at close  6 / 24
```

---

## Setup

### 1. Create a Discord bot

1. Go to https://discord.com/developers/applications → **New Application**
2. **Bot** tab → **Reset Token** → copy the token
3. **OAuth2 → URL Generator**: scopes `bot`, bot permissions `Send Messages` + `Embed Links` + `Read Message History`
4. Open the generated URL and invite the bot to your server
5. Enable **Developer Mode** in Discord settings, then right-click your notification channel → **Copy Channel ID**

### 2. Run locally

```powershell
pip install -r requirements.txt

$env:DISCORD_TOKEN="your_token"
$env:DISCORD_CHANNEL_ID="your_channel_id"
python bot.py
```

```bash
# Linux / macOS
DISCORD_TOKEN=your_token DISCORD_CHANNEL_ID=your_channel_id python bot.py
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

## Hosting — Fly.io (free tier)

Fly.io hosts the bot for free (requires a credit card on file, but the bot stays well within the free allowance at ~30 MB RAM).

### One-time setup

```powershell
# Install flyctl (Windows)
iwr https://fly.io/install.ps1 -useb | iex

# macOS / Linux
curl -L https://fly.io/install.sh | sh

flyctl auth login
flyctl apps create lotr-risk-bot
```

### GitHub Actions auto-deploy

Every push to `main` automatically deploys to Fly.io. Add these three secrets at **Settings → Secrets → Actions** in your GitHub repo:

| Secret | Description |
|---|---|
| `DISCORD_TOKEN` | Discord bot token |
| `DISCORD_CHANNEL_ID` | Channel ID to post in |
| `FLY_API_TOKEN` | From `flyctl tokens create deploy -x 999999h -a lotr-risk-bot` |

### Manual deploy

```bash
flyctl secrets set DISCORD_TOKEN=your_token DISCORD_CHANNEL_ID=your_channel_id
flyctl deploy
```

### Useful commands

```bash
flyctl status        # check if running
flyctl logs          # stream live logs
flyctl secrets list  # list secrets (values hidden)
```

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | Yes | — | Discord bot token |
| `DISCORD_CHANNEL_ID` | Yes | — | Channel to post notifications in |
| `GAME_FILTER` | No | `LOTR RISK` | Case-insensitive substring to match game names |
| `POLL_INTERVAL` | No | `60` | Seconds between API polls |
