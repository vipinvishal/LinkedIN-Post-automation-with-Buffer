# LinkedIn Post Automation

An AI agent that researches trending topics, generates engaging posts, and publishes them to LinkedIn automatically — every day at 10 AM IST.

**No VPS needed. No manual work. Fully automated via GitHub Actions.**

---

## How It Works

```
GitHub Actions (10 AM IST daily)
        ↓
Exa — neural web research on a random AI/tech topic
        ↓
Gemini — generates a viral, first-person post
  └─ fallback: Gemini key #2 → Euron API
        ↓
Buffer — schedules and publishes to your LinkedIn profile
```

---

## Tech Stack

| Tool | Purpose |
|---|---|
| **GitHub Actions** | Daily scheduling (replaces VPS/cron) |
| **Exa** | Real-time neural web research |
| **Google Gemini** | Post generation (dual-key with quota rotation) |
| **Euron API** | Fallback when all Gemini keys are exhausted |
| **Buffer** | Schedules and publishes posts to LinkedIn |

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/vipinvishal/LinkedIN-Post-automation-with-Buffer.git
cd LinkedIN-Post-automation-with-Buffer
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Set up your `.env` file

```bash
cp .env.example .env
```

Fill in your API keys (see [Configuration](#configuration) below).

### 4. Test locally before going live

```bash
# Preview a generated post without sending to Buffer
python scripts/generate_and_schedule.py --preview

# Run the full pipeline (research → generate → schedule to Buffer)
python scripts/generate_and_schedule.py
```

---

## Configuration

Add these to your `.env` file:

| Variable | Where to get it | Required |
|---|---|---|
| `GEMINI_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Yes |
| `GEMINI_API_KEY_2` | Same — second Google account | Optional (quota fallback) |
| `EURON_API_KEY` | [euron.one](https://euron.one) | Optional (last-resort fallback) |
| `EXA_API_KEY` | [exa.ai](https://exa.ai) | Yes |
| `BUFFER_API_KEY` | buffer.com → Settings → API | Yes |
| `BUFFER_CHANNEL_ID` | Run `python scripts/get_buffer_channel.py` | Yes |

### Finding your Buffer Channel ID

```bash
# Make sure BUFFER_API_KEY is set in .env first
python scripts/get_buffer_channel.py
```

Copy the ID for your LinkedIn channel and paste it into `.env` as `BUFFER_CHANNEL_ID`.

---

## GitHub Actions Setup (Automated Daily Posting)

### 1. Add secrets to your GitHub repo

Go to **Settings → Secrets and variables → Actions → New repository secret** and add:

- `GEMINI_API_KEY`
- `GEMINI_API_KEY_2`
- `EURON_API_KEY`
- `EXA_API_KEY`
- `BUFFER_API_KEY`
- `BUFFER_CHANNEL_ID`

### 2. The workflow runs automatically

The workflow is defined in `.github/workflows/daily_post.yml` and triggers every day at **10:00 AM IST (04:30 UTC)**.

You can also trigger it manually anytime:
**GitHub repo → Actions → Daily LinkedIn Post → Run workflow**

---

## Customizing Topics & Persona

Edit `scripts/topics.json` to change:

- **`niche`** — the content category
- **`persona`** — the voice and style of the posts
- **`topics`** — list of topics to randomly pick from each day
- **`tones`** — list of tones to randomly apply

---

## Project Structure

```
├── scripts/
│   ├── generate_and_schedule.py   # main pipeline
│   ├── topics.json                # niche, topics, tones, persona
│   └── get_buffer_channel.py      # one-time helper to find Buffer channel ID
├── .github/
│   └── workflows/
│       └── daily_post.yml         # GitHub Actions workflow
├── .env.example                   # template — copy to .env and fill in keys
├── requirements.txt               # Python dependencies
└── .gitignore
```

---

## Fallback Chain

If Gemini hits its daily free-tier quota, the bot automatically falls back:

```
Gemini key #1 → Gemini key #2 → Euron API (gemini-2.0-flash)
```

No manual intervention needed.

---

## License

MIT
