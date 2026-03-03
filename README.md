# 𝕏 Viral Bot — Full Setup Guide
**Stack:** Python · Gemini AI · X API v2 · Flask · Cron · Gmail**Host:** Your Hostinger VPS (or run locally)

---

## Quick start (local)

1. **Copy env and add your keys:**
   ```bash
   cp .env.example .env
   # Edit .env: add GEMINI_API_KEY (and X + email credentials for full flow)
   ```

2. **Install deps and run the bot:**
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   .venv/bin/python bot.py
   ```
   (Or use system Python: `pip install -r requirements.txt` then `python3 bot.py`.)
   - With only `GEMINI_API_KEY`: research + tweet generation runs; you must add `EMAIL_*` and `SERVER_BASE_URL` to get the approval email.
   - With X API keys + `POST_DIRECTLY=1`: research runs and the tweet is posted to X immediately (no email).
   - **Generate 10 scroll-stopping hooks only:** `python3 bot.py --hooks` (AI infra / cloud / autonomous systems, &lt;12 words each).

3. **Run the approval server** (for email flow):
   ```bash
   python3 approve.py
   ```
   Then open `http://localhost:5000/status` to confirm it’s running. Use `SERVER_BASE_URL=http://localhost:5000` in `.env` when testing locally.

---

## How It Works

```
[Cron — daily 9AM]
       ↓
  bot.py runs
       ↓
  Tavily + Gemini research → Gemini writes viral tweet
       ↓
  Generate 1200×675 tweet card → save to cards/
       ↓
  ┌─ If POST_DIRECTLY=1: post tweet + image to X
  └─ Else: email with inline card preview + [Approve] [Reject]
       ↓
  You click Approve → approve.py posts tweet + card image to X
```

---

## Step 1 — Upload files to VPS

SSH into your Hostinger VPS:
```bash
ssh root@YOUR_VPS_IP
```

Create project folder and upload all files:
```bash
mkdir -p /root/x-viral-bot/logs /root/x-viral-bot/pending
cd /root/x-viral-bot
```

Upload via SCP from your local machine:
```bash
scp -r ./x-viral-bot/* root@YOUR_VPS_IP:/root/x-viral-bot/
```

---

## Step 2 — Install dependencies

```bash
cd /root/x-viral-bot
pip3 install -r requirements.txt
# Tweet card image (required for 1200×675 card generation):
pip3 install pillow
```

---

## Step 3 — Configure your .env

```bash
cp .env.example .env
nano .env   # or open .env in your editor
```

**Required for research:** `GEMINI_API_KEY` (get at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)).

Fill in all values:

| Variable | Where to get it |
|---|---|
| `GEMINI_API_KEY` | aistudio.google.com → Get API Key |
| `TAVILY_API_KEY` | tavily.com → API key (real-time web search for research) |
| `X_API_KEY` / `X_API_SECRET` | developer.x.com → Your App → Keys & Tokens |
| `X_ACCESS_TOKEN` / `X_ACCESS_SECRET` | developer.x.com → Your App → Generate |
| `X_HANDLE` | Your X handle for the card (e.g. `@yourhandle`) |
| `EMAIL_SENDER` | Your Gmail address |
| `EMAIL_PASSWORD` | myaccount.google.com/apppasswords → Create App Password |
| `SERVER_BASE_URL` | `http://YOUR_VPS_IP:5000` |

---

## Step 4 — Open firewall port 5000

On Hostinger VPS, allow incoming traffic on port 5000:
```bash
ufw allow 5000/tcp
ufw reload
```

---

## Step 5 — Run the Flask approval server (permanently)

Copy the systemd service file:
```bash
cp xviralbot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable xviralbot
systemctl start xviralbot
```

Check it's running:
```bash
systemctl status xviralbot
# Visit: http://YOUR_VPS_IP:5000/status
```

---

## Step 6 — Set up the cron job

Open crontab:
```bash
crontab -e
```

Add this line to run every day at 9:00 AM:
```
0 9 * * * cd /root/x-viral-bot && /usr/bin/python3 bot.py >> logs/cron.log 2>&1
```

Save and exit. The bot now runs automatically every morning.

---

## Tweet card image (VPS)

The pipeline generates a 1200×675 dark-themed card, embeds it in the approval email, and attaches it to the X post when you approve.

**On your VPS:**

1. **Install Pillow** (if not already in requirements):
   ```bash
   pip3 install pillow
   ```

2. **Add your handle to `.env`:**
   ```bash
   X_HANDLE=@yourhandle
   ```

3. **Test the full flow (tweet + card):**
   ```bash
   python3 bot.py --preview
   ```
   → Generates tweet and saves card to `cards/*.png`.

`approve.py` already passes `data.get("image_path")` to `post_to_x()`, so the card is attached when you click Approve.

---

## Step 7 — Test it manually

```bash
cd /root/x-viral-bot
python3 bot.py
```

You should receive an approval email within ~30 seconds. Click Approve — tweet goes live!

---

## Useful Commands

```bash
# View bot logs
tail -f /root/x-viral-bot/logs/bot.log

# View server logs
tail -f /root/x-viral-bot/logs/server.log

# View all pending/approved/rejected tweets
ls /root/x-viral-bot/pending/

# Restart approval server
systemctl restart xviralbot

# Test approval server health
curl http://localhost:5000/status
```

---

## Gmail App Password Setup

1. Go to myaccount.google.com
2. Security → 2-Step Verification (must be ON)
3. Security → App Passwords
4. Select "Mail" + "Other" → name it "XViralBot"
5. Copy the 16-character password → paste into `.env` as `EMAIL_PASSWORD`

---

## X Developer App — Required Settings

Make sure your X app has:
- **App permissions:** Read and Write
- **Type of App:** Web App (for OAuth)
- Access Token & Secret generated with your **own account**

---

## File Structure

```
x-viral-bot/
├── bot.py            ← Main pipeline (run by cron)
├── approve.py        ← Flask server (runs permanently)
├── requirements.txt
├── .env              ← Your secrets (never share this!)
├── .env.example      ← Template
├── xviralbot.service ← Systemd config
├── logs/
│   ├── bot.log       ← Pipeline logs
│   ├── server.log    ← Flask server logs
│   └── cron.log      ← Cron output
└── pending/
    └── *.json        ← Pending/approved/rejected tweets
```
