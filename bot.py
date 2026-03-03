#!/usr/bin/env python3
"""
X Viral Bot — Main Pipeline
Flow: Research (Tavily) → Gemini synthesis → Generate tweet → Generate image card → Approval email → Post to X
"""

import os
import sys
import json
import re
import uuid
import smtplib
import logging
import time
import textwrap
import unicodedata
from datetime import datetime

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

import requests
from PIL import Image, ImageDraw, ImageFont
from tavily import TavilyClient
from google import genai
from google.genai import types
from dotenv import load_dotenv

# ── Setup ──────────────────────────────────────────────────────────────────────
load_dotenv()
os.makedirs("logs", exist_ok=True)
os.makedirs("pending", exist_ok=True)
os.makedirs("cards", exist_ok=True)
logging.basicConfig(
    filename="logs/bot.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# ── Config from .env ───────────────────────────────────────────────────────────
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY")
X_API_KEY           = os.getenv("X_API_KEY")
X_API_SECRET        = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN      = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_SECRET     = os.getenv("X_ACCESS_SECRET")
EMAIL_SENDER        = os.getenv("EMAIL_SENDER")          # your Gmail
EMAIL_PASSWORD      = os.getenv("EMAIL_PASSWORD")        # Gmail app password
EMAIL_RECIPIENT     = os.getenv("EMAIL_RECIPIENT")       # your personal email
SERVER_BASE_URL     = os.getenv("SERVER_BASE_URL")       # e.g. http://YOUR_VPS_IP:5000
NICHE               = os.getenv("NICHE", "Tech & AI")
X_HANDLE            = os.getenv("X_HANDLE", "@yourhandle")
POST_DIRECTLY       = os.getenv("POST_DIRECTLY", "").lower() in ("1", "true", "yes")  # skip email, post to X at once
GEMINI_MODEL        = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")  # or gemini-2.0-flash, gemini-1.5-flash
GEMINI_FALLBACK_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]  # if primary hits quota

PENDING_DIR = "pending"
CARDS_DIR   = "cards"

# Font paths — works on Linux VPS (Hostinger) and macOS
FONT_PATHS_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial Bold.ttf",
]
FONT_PATHS_REG = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
]

# Retry config for 429 (quota)
MAX_GEMINI_RETRIES = 5
RETRY_BASE_SECONDS = 15


def _find_font(paths: list) -> str | None:
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def _hex(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _strip_emoji(text: str) -> str:
    """Remove emoji/symbol characters that typical server fonts can't render cleanly.

    This only affects the card image; the tweet text sent to X still keeps emojis.
    """
    return "".join(ch for ch in text if unicodedata.category(ch) != "So")


def _parse_retry_seconds(error: Exception) -> int:
    """Parse 'Please retry in X.XXs' from error details if present."""
    msg = str(error)
    m = re.search(r"retry in (\d+(?:\.\d+)?)\s*s", msg, re.I)
    if m:
        return max(1, int(float(m.group(1))))
    return RETRY_BASE_SECONDS


def _is_quota_error(error: Exception) -> bool:
    """True if the error is a 429 / resource exhausted."""
    msg = str(error).lower()
    return "429" in msg or "resource_exhausted" in msg or "quota" in msg


def _is_retryable_server_error(error: Exception) -> bool:
    """True if the error is 503 / overloaded / temporary (retry or try next model)."""
    msg = str(error).lower()
    return "503" in msg or "unavailable" in msg or "high demand" in msg or "servererror" in msg


def _generate_with_retry(prompt: str, model_name: str, system_instruction: str | None = None) -> str:
    """Call Gemini generate_content with retries on 429/503 and optional model fallback."""
    client = genai.Client(api_key=GEMINI_API_KEY)
    models_to_try = [model_name] + [m for m in GEMINI_FALLBACK_MODELS if m != model_name]

    last_error = None
    for model_id in models_to_try:
        config = None
        if system_instruction:
            config = types.GenerateContentConfig(system_instruction=system_instruction)
        for attempt in range(1, MAX_GEMINI_RETRIES + 1):
            try:
                response = client.models.generate_content(
                    model=model_id,
                    contents=prompt,
                    config=config,
                )
                return response.text or ""
            except Exception as e:
                if _is_quota_error(e) or _is_retryable_server_error(e):
                    last_error = e
                    wait = _parse_retry_seconds(e)
                    kind = "quota (429)" if _is_quota_error(e) else "overloaded (503)"
                    log.warning(
                        f"Gemini {kind} on {model_id}, attempt {attempt}/{MAX_GEMINI_RETRIES}. "
                        f"Retrying in {wait}s..."
                    )
                    if attempt < MAX_GEMINI_RETRIES:
                        time.sleep(wait)
                    else:
                        log.warning(f"Retries exhausted for {model_id}, trying next model.")
                        break
                else:
                    raise
    raise last_error or RuntimeError("No Gemini model succeeded.")


# ── Research (multi-channel synthesis) ────────────────────────────────────────
RESEARCH_USER_TEMPLATE = """Topic focus: {topic_focus}
Reference date: {reference_date}
{recency_instruction}
{angle_instruction}
{avoid_instruction}

REAL-WORLD RESEARCH (freshly fetched via Tavily — use as primary source when available):
{tavily_context}

When the above is present, use it as ground truth and synthesize to find the non-obvious angle. Otherwise use the channel guidance below.

You have access to multiple research channels. Use ALL of them:

CHANNEL 1 — Breaking news (last 7 days):
Search for recent announcements, launches, and controversies in {topic_focus}.
Prioritize stories that are 1-4 days old — not yet over-covered.

CHANNEL 2 — HackerNews signal:
What is the technical AI community on HackerNews actually debating right now?
These discussions surface real engineering pain points 48hrs before mainstream coverage.

CHANNEL 3 — Research papers (ArXiv):
Find 1-2 papers published in the last 14 days on {topic_focus}.
Extract the single most surprising finding or benchmark result.
This is your unfair advantage — most X accounts never cite papers.

CHANNEL 4 — Company signals:
Check GitHub repos, developer blogs, and changelog pages of:
OpenAI, Anthropic, Google DeepMind, Microsoft, Meta AI, Mistral, Cohere, LangChain, LlamaIndex.
What shipped quietly that nobody wrote a headline about yet?

CHANNEL 5 — Counter-narrative:
What is the most upvoted CRITICAL or skeptical take on current AI trends?
Find the dissenting voice, the "this is overhyped" argument.
Contrarian angles get 3x more replies on X than consensus takes.

Synthesize all 5 channels into research notes (JSON only):
{{
  "trend": "One-line summary of the single most timely/viral topic for the tweet",
  "angle": "Best hook angle for maximum engagement with AI builders",
  "headlines": ["headline 1", "headline 2", ...],
  "summaries": ["1-2 sentence summary per headline"],
  "links": ["url1", "url2", ...],
  "contrarian_angle": "The one surprising, counterintuitive, or under-reported insight. Not what everyone is saying — what SHOULD they be saying?",
  "second_order_impact": ["2-3 downstream consequences nobody is talking about yet"],
  "date_context": "brief note on what's timely",
  "company_moves": ["Strategic moves — focus on WHAT THEY ARE BETTING ON and WHY"],
  "new_tools_and_agents": ["Name + description + who benefits + what it disrupts"],
  "key_trends": ["2-4 trends framed as a TENSION or SHIFT"],
  "how_to_use": ["Concrete builder takeaways — specific enough to act on today"],
  "viral_hook_angles": ["3 first-line hooks under 12 words each — surprising, curiosity-gap creating"],
  "paper_insight": "One finding from a recent ArXiv paper that would surprise an AI engineer",
  "hn_pulse": "The dominant sentiment or debate on HackerNews about this topic right now",
  "underreported_story": "One story that has fewer than 5 articles written about it but deserves attention"
}}

Rules:
- Be concrete: real product names, real numbers, real companies.
- Avoid generic AI hype. Dig for the non-obvious story.
- The underreported_story field is mandatory — do not leave it empty.
- Output valid JSON only: escape double quotes with \\, no trailing commas, no newlines inside strings."""


# ── X content system (viral ghostwriter for AI builders) ───────────────────────
X_CONTENT_SYSTEM = """You are a viral X (Twitter) ghostwriter for AI builders and developers. Your tweets regularly hit 100K+ impressions in the technical AI community.

────────────────────────────
PERSONA LAYER (CRITICAL)
────────────────────────────

You are not an AI news account.
You are an AI infrastructure strategist focused on:

- Compute control
- Economic leverage
- Sovereign AI
- Capital allocation in AI
- Infrastructure asymmetry
- Open vs closed power dynamics

Every tweet must reflect strategic thinking.
If the topic does not connect to power, economics, leverage, or control — discard it and choose a sharper angle.

────────────────────────────
POWER FILTER (MANDATORY BEFORE WRITING)
────────────────────────────

Before selecting the final angle, ask internally:

1. Does this change who controls compute?
2. Does this shift economic leverage?
3. Does this alter capital flow?
4. Does this weaken or strengthen AI sovereignty?
5. Who wins if this scales? Who loses?

If none apply, the angle is too weak. Find a stronger one.

────────────────────────────
MONETIZATION OPTIMIZATION
────────────────────────────

On X, replies drive revenue more than likes.

Therefore:
- Prefer tension over summary.
- Prefer tradeoffs over explanations.
- Prefer binary framing (X vs Y).
- Prefer consequences over descriptions.

Avoid neutral reporting tone.

────────────────────────────
HOOK UPGRADE
────────────────────────────

The first 8 words must create at least one of:

- Ego threat
- Insider advantage
- Fear of being behind
- Status signaling
- Strategic shift

Weak: "New model improves benchmarks."
Strong: "If you’re still paying API margins, you’re behind."

────────────────────────────
AUDIENCE INSERTION RULE
────────────────────────────

At least 30% of tweets must include one of:

- What builders should do now
- What startups are underestimating
- What infra teams must rethink
- What governments will change
- What investors are missing

The reader must feel either exposed or advantaged.

────────────────────────────
SECOND-ORDER DEPTH
────────────────────────────

When using second_order_impact, always frame it as:

- Immediate effect
- Who gains leverage
- Who loses leverage
- What breaks at scale

Never stop at first-order analysis.

────────────────────────────
ENGAGEMENT TRAP ENDINGS
────────────────────────────

End tweets with ONE of:

- A sharp binary tension
- A provocative structural claim
- A consequence framed as inevitable
- A strategic cliffhanger

Never end with:
"What do you think?"
"Thoughts?"
Generic engagement bait.

────────────────────────────
REJECTION FILTER
────────────────────────────

Reject angles that are:
- Obvious
- Already consensus
- Purely descriptive
- Lacking economic or power implications

Always choose the sharpest edge.

────────────────────────────
OUTPUT CONSTRAINTS
────────────────────────────

- ONE IDEA, ONE TWEET. No summarizing. Pick the single sharpest technical insight and say it in one punch.
- The first line is what shows before “show more” — it must earn the tap.
- ≤ 280 characters total including spaces (hard limit).
- Max 2 emojis — only if they add meaning, never decoration.
- No hashtags.
- No external links in the tweet body.
- No "Thread 🧵" — this is a single tweet.
- No "Thoughts?" or "What do you think?".
- Never start with: "AI is", "The future of", "Excited to", "Just released", "Game changer", "Revolutionary", "In today's world".
- No generic AI hype.
- Every word must earn its place.

Output only the tweet text. Nothing else. No quotes around it."""

X_CONTENT_USER_TEMPLATE = """Research notes:
{research_json}

TASK: Write one viral X tweet for an AI builder/developer audience.

Step 1 — Find the sharpest edge:
Look at contrarian_angle, second_order_impact, paper_insight, underreported_story, and hn_pulse in the research.
Ignore everything that's already obvious. Find the ONE thing that would make a senior ML engineer say "huh, I hadn't thought of it that way."

Priority order for angle selection:
1. paper_insight — if there's a surprising research finding, lead with it.
   Nobody else is tweeting about papers. Instant credibility with dev audience.
2. underreported_story — if it has real technical implications, use it.
   Being first on a story compounds your follower growth.
3. contrarian_angle — use if #1 and #2 aren't strong enough.
4. hn_pulse — use to frame your hook as joining an existing debate
   the community is already having.

IMPORTANT: Pick ONE angle and build the entire tweet around it.
If paper_insight or contrarian_angle is stronger than the trend topic,
use that instead — fully. Do not mix two angles in one tweet.
The trend is a starting point, not a constraint.

Step 2 — Pick your attack angle (choose ONE):
A) Counterintuitive claim — something the majority believes that is subtly wrong
B) Specific surprising number or fact from the research
C) First-person builder observation — "We tried X and discovered Y"
D) Hot take — a clear position that experts will want to argue with

Step 3 — Write the tweet:
- Line 1: Hook (first 8 words must earn the read — this is what shows before "show more")
- Line 2 (optional): One sentence of tension or context that deepens the hook
- Line 3 (optional): The insight, implication, or consequence
- Final line: Binary question OR provocative closer OR surprising fact with no explanation

Step 4 — Hard constraints check:
[ ] Total characters ≤ 280?
[ ] Zero hashtags?
[ ] Zero external links?
[ ] First word is NOT "AI", "The", "Excited"?
[ ] Last line is NOT "What do you think?" or "Thoughts?"
[ ] Every word earns its place — remove anything that doesn't add punch?

Output only the final tweet text. Count the characters yourself before outputting."""

X_REWRITE_USER_TEMPLATE = """Previous tweet draft:
---
{previous_post}
---

Diagnose it first:
- Does the first 8 words earn a tap? Or is it forgettable?
- Is there a specific number, name, or fact — or just vague claims?
- Does the last line provoke a reply or just trail off?
- Is it under 280 characters?

Rewrite it fixing exactly those weaknesses.
Same core insight, sharper delivery.
No hashtags. No links. No "Thoughts?".
Output only the new tweet text."""


# ── Tavily: fetch real-world research (replaces raw Gemini “search”) ─────────────
def fetch_tavily_context(topic: str) -> str:
    """
    Pull fresh real-world research from Tavily across 5 channels.
    Returns a formatted string injected into the Gemini research prompt.
    """
    TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
    if not TAVILY_API_KEY:
        log.warning("TAVILY_API_KEY not set — skipping Tavily fetch.")
        return ""

    client = TavilyClient(api_key=TAVILY_API_KEY)
    queries = [
        f"{topic} latest news announcements last 7 days",           # Channel 1: Breaking news
        f"{topic} HackerNews discussion debate engineering",         # Channel 2: HN pulse
        f"{topic} arxiv research paper finding 2025",               # Channel 3: Papers
        f"OpenAI Anthropic Google Meta Microsoft {topic} release",  # Channel 4: Company moves
        f"{topic} overhyped criticism problems failure",            # Channel 5: Counter-narrative
    ]

    sections = []
    for i, query in enumerate(queries, 1):
        try:
            result = client.search(
                query=query,
                search_depth="advanced",
                max_results=3,
                include_answer=True,
            )
            answer = result.get("answer", "")
            results_text = "\n".join([
                f"- [{r.get('title', '')}]: {r.get('content', '')[:300]}"
                for r in result.get("results", [])
            ])
            sections.append(
                f"CHANNEL {i} RESEARCH:\n"
                f"Summary: {answer}\n"
                f"Sources:\n{results_text}"
            )
            log.info(f"Tavily channel {i} fetched: {len(result.get('results', []))} results")
        except Exception as e:
            log.warning(f"Tavily channel {i} failed: {e}")

    return "\n\n".join(sections)


# ── Step 1: Research (Tavily → Gemini synthesis) ───────────────────────────────
def research_trends(
    topic_focus: str | None = None,
    recency_instruction: str = "",
    angle_instruction: str = "",
    avoid_instruction: str = "",
) -> dict:
    log.info("Step 1: Fetching real-world context via Tavily...")
    topic = topic_focus or NICHE
    reference_date = datetime.now().strftime("%B %d, %Y")

    tavily_context = fetch_tavily_context(topic)
    if not tavily_context:
        tavily_context = "No Tavily context available — use general knowledge and the channel guidance below."

    prompt = RESEARCH_USER_TEMPLATE.format(
        topic_focus=topic,
        reference_date=reference_date,
        recency_instruction=recency_instruction or "Prioritize the last 1-7 days.",
        angle_instruction=angle_instruction or "Angle toward technical builders and engineers.",
        avoid_instruction=avoid_instruction or "Avoid topics that are already saturated in mainstream news.",
        tavily_context=tavily_context,
    )

    log.info("Step 1b: Synthesizing research via Gemini...")
    raw = _generate_with_retry(prompt, GEMINI_MODEL)
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    data = json.loads(raw)
    log.info(f"Research done. Keys: {list(data.keys())[:8]}...")
    return data


# ── Step 2: Generate viral tweet (system + user template) ───────────────────────
def generate_tweet(trend_data: dict) -> str:
    log.info("Step 2: Generating tweet via Gemini...")
    research_json = json.dumps(trend_data, indent=2)
    user_prompt = X_CONTENT_USER_TEMPLATE.format(research_json=research_json)
    raw = _generate_with_retry(user_prompt, GEMINI_MODEL, system_instruction=X_CONTENT_SYSTEM)
    tweet = raw.strip().strip('"').strip("'")
    log.info(f"Tweet generated ({len(tweet)} chars): {tweet[:60]}...")
    return tweet


# ── Rewrite a draft tweet (sharper delivery) ──────────────────────────────────
def rewrite_tweet(previous_post: str) -> str:
    """Rewrite a tweet draft to fix weak hook, vague claims, or soft closer."""
    log.info("Rewriting tweet...")
    user_prompt = X_REWRITE_USER_TEMPLATE.format(previous_post=previous_post)
    raw = _generate_with_retry(user_prompt, GEMINI_MODEL, system_instruction=X_CONTENT_SYSTEM)
    return raw.strip().strip('"').strip("'")


# ── Step 3: Generate tweet card image ─────────────────────────────────────────
def generate_tweet_image(tweet: str, token: str) -> str:
    """
    Generate a 1200x675 dark-themed tweet card image.
    Returns the path to the saved PNG.
    """
    log.info("Step 3: Generating tweet card image...")

    W, H = 1200, 675

    BG = "#0d1117"
    CARD = "#161b22"
    BORDER = "#21262d"
    ACCENT = "#58a6ff"
    ACCENT2 = "#bc8cff"
    TEXT = "#e6edf3"
    SUB = "#8b949e"
    GREEN = "#3fb950"

    bold_path = _find_font(FONT_PATHS_BOLD)
    reg_path = _find_font(FONT_PATHS_REG)

    def font(path, size):
        try:
            return ImageFont.truetype(path, size) if path else ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()

    f_bold = font(bold_path, 34)
    f_body = font(reg_path, 29)
    f_small = font(reg_path, 21)
    f_handle = font(bold_path, 23)
    f_foot = font(reg_path, 19)
    f_close = font(bold_path, 27)

    img = Image.new("RGB", (W, H), _hex(BG))
    draw = ImageDraw.Draw(img)

    grid_color = (28, 31, 36)
    for x in range(0, W, 80):
        draw.line([(x, 0), (x, H)], fill=grid_color, width=1)
    for y in range(0, H, 80):
        draw.line([(0, y), (W, y)], fill=grid_color, width=1)

    cx1, cy1, cx2, cy2 = 52, 42, W - 52, H - 42
    draw.rounded_rectangle([cx1, cy1, cx2, cy2], radius=18, fill=_hex(CARD), outline=_hex(BORDER), width=1)
    draw.rounded_rectangle([cx1, cy1, cx2, cy1 + 5], radius=18, fill=_hex(ACCENT))

    ax, ay, ar = 100, 122, 26
    draw.ellipse([ax - ar, ay - ar, ax + ar, ay + ar], fill=_hex(ACCENT))
    draw.text((ax, ay), "X", font=f_bold, fill=(255, 255, 255), anchor="mm")

    date_str = datetime.now().strftime("%b %d, %Y")
    draw.text((140, 106), X_HANDLE, font=f_handle, fill=_hex(ACCENT))
    draw.text((140, 130), f"{date_str}  ·  {NICHE}", font=f_small, fill=_hex(SUB))

    draw.line([(cx1 + 28, 168), (cx2 - 28, 168)], fill=_hex(BORDER), width=1)

    # Some server fonts can't render emojis and show them as empty boxes.
    # Strip those from the image-only version while keeping them in the tweet text.
    tweet_for_card = _strip_emoji(tweet)

    raw_lines = tweet_for_card.strip().split("\n")
    non_empty = [l for l in raw_lines if l.strip()]
    closing_q = non_empty[-1] if non_empty and "?" in non_empty[-1] else None

    y_cur = 186
    max_y = cy2 - 58

    for raw_line in raw_lines:
        if y_cur > max_y:
            break
        if raw_line.strip() == "":
            y_cur += 14
            continue

        is_closing = raw_line.strip() == closing_q

        if is_closing:
            y_cur += 8
            draw.rounded_rectangle(
                [cx1 + 28, y_cur, cx1 + 33, y_cur + 38],
                radius=2,
                fill=_hex(ACCENT2),
            )
            wrapped = textwrap.wrap(raw_line.strip(), width=56) or [""]
            for wl in wrapped:
                draw.text((cx1 + 48, y_cur), wl, font=f_close, fill=_hex(ACCENT2))
                y_cur += 40
        else:
            wrapped = textwrap.wrap(raw_line.strip(), width=62) or [""]
            for wl in wrapped:
                draw.text((cx1 + 32, y_cur), wl, font=f_body, fill=_hex(TEXT))
                y_cur += 37

    draw.line([(cx1 + 20, cy2 - 46), (cx2 - 20, cy2 - 46)], fill=_hex(BORDER), width=1)
    dot_x, dot_y = cx1 + 36, cy2 - 24
    draw.ellipse([dot_x - 5, dot_y - 5, dot_x + 5, dot_y + 5], fill=_hex(GREEN))
    draw.text((dot_x + 14, dot_y), f"AI Builder  ·  {NICHE}", font=f_foot, fill=_hex(SUB), anchor="lm")

    out_path = os.path.join(CARDS_DIR, f"{token}.png")
    img.save(out_path, "PNG", quality=95)
    log.info(f"Tweet card saved: {out_path}")
    return out_path


# ── Generate 10 scroll-stopping hooks ──────────────────────────────────────────
def generate_hooks() -> list[str]:
    """Generate 10 scroll-stopping hooks for AI infra / cloud / autonomous systems."""
    log.info("Generating 10 hooks...")
    prompt = """You are a high-impact AI thought leader writing for X (Twitter).
Position: Cloud Architect & AI Systems Builder. Audience: founders, engineers, enterprise leaders.

Generate exactly 10 scroll-stopping hooks about AI infrastructure, cloud architecture, or autonomous systems.
- Hooks must create curiosity or challenge common beliefs.
- Avoid clichés.
- Keep each hook under 12 words.
- Output one hook per line, numbered 1–10. No other text."""
    raw = _generate_with_retry(prompt, GEMINI_MODEL)
    lines = [line.strip() for line in raw.strip().split("\n") if line.strip()]
    hooks = []
    for line in lines:
        if len(hooks) >= 10:
            break
        # Skip short intro lines only
        lower = line.lower()
        if len(line) < 25 and lower.startswith(("here are", "sure,", "sure!")):
            continue
        # Strip leading "1." "2)" "- " etc
        stripped = re.sub(r"^\s*\d+[.)\-]\s*", "", line).strip()
        if stripped and len(stripped) > 5:
            hooks.append(stripped)
    return hooks[:10]


# ── Step 4: Save pending tweet to disk ────────────────────────────────────────
def save_pending(tweet: str, trend_data: dict, image_path: str | None = None) -> str:
    token = str(uuid.uuid4())
    payload = {
        "token": token,
        "tweet": tweet,
        "trend": trend_data,
        "image_path": image_path,
        "created_at": datetime.now().isoformat(),
        "status": "pending",
    }
    path = os.path.join(PENDING_DIR, f"{token}.json")
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    log.info(f"Pending tweet saved: {token}")
    return token


# ── Post to X (text + optional image) ─────────────────────────────────────────
def post_to_x(tweet: str, image_path: str | None = None) -> str:
    import tweepy

    media_id = None
    if image_path and os.path.exists(image_path):
        auth = tweepy.OAuth1UserHandler(
            X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET
        )
        api_v1 = tweepy.API(auth)
        media = api_v1.media_upload(filename=image_path)
        media_id = media.media_id_string
        log.info(f"Image uploaded to X. media_id: {media_id}")

    client = tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_SECRET,
    )
    kwargs = {"text": tweet}
    if media_id:
        kwargs["media_ids"] = [media_id]
    response = client.create_tweet(**kwargs)
    tweet_id = response.data["id"]
    log.info(f"Tweet posted to X! ID: {tweet_id}")
    return tweet_id


# ── Step 5: Send approval email (with optional inline image preview) ───────────
def send_approval_email(
    tweet: str, trend_data: dict, token: str, image_path: str | None = None
):
    log.info("Step 5: Sending approval email...")

    approve_url = f"{SERVER_BASE_URL}/approve/{token}"
    reject_url = f"{SERVER_BASE_URL}/reject/{token}"

    img_tag = ""
    if image_path and os.path.exists(image_path):
        img_tag = '<img src="cid:tweetcard" style="width:100%;border-radius:12px;margin-bottom:20px;" />'

    trend_safe = trend_data.get("trend", "") or ""
    angle_safe = (trend_data.get("angle", "") or "")[:120]

    html = f"""<!DOCTYPE html>
<html>
<head>
<style>
  body {{ font-family:'Segoe UI',sans-serif; background:#0d1117; color:#e6edf3; margin:0; padding:20px; }}
  .container {{ max-width:620px; margin:0 auto; }}
  .header {{ background:linear-gradient(135deg,#1f6feb,#8b5cf6); padding:24px; border-radius:12px 12px 0 0; text-align:center; }}
  .header h1 {{ margin:0; font-size:20px; color:#fff; }}
  .header p  {{ margin:6px 0 0; color:#ffffffaa; font-size:13px; }}
  .body {{ background:#161b22; padding:24px; border:1px solid #30363d; border-top:none; border-radius:0 0 12px 12px; }}
  .trend-box {{ background:#0d1117; border-left:3px solid #58a6ff; padding:10px 14px; border-radius:6px; margin-bottom:16px; font-size:13px; color:#8b949e; }}
  .tweet-box {{ background:#0d1117; border:1px solid #30363d; border-radius:10px; padding:18px; margin-bottom:20px; font-size:15px; line-height:1.7; color:#e6edf3; white-space:pre-wrap; }}
  .chars {{ font-size:11px; color:#484f58; margin-top:8px; }}
  .buttons {{ display:flex; gap:10px; }}
  .btn-approve {{ flex:2; background:linear-gradient(135deg,#238636,#2ea043); color:#fff; text-decoration:none; padding:13px; border-radius:9px; text-align:center; font-weight:800; font-size:14px; display:block; }}
  .btn-reject  {{ flex:1; background:transparent; border:1px solid #f85149; color:#f85149; text-decoration:none; padding:13px; border-radius:9px; text-align:center; font-weight:700; font-size:14px; display:block; }}
  .footer {{ text-align:center; margin-top:16px; font-size:11px; color:#484f58; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>𝕏 Tweet Ready for Approval</h1>
    <p>{datetime.now().strftime("%B %d, %Y · %I:%M %p")}</p>
  </div>
  <div class="body">
    <div class="trend-box">
      📈 <strong style="color:#58a6ff">Trend:</strong> {trend_safe}<br>
      🎯 <strong style="color:#58a6ff">Angle:</strong> {angle_safe}
    </div>
    {img_tag}
    <p style="font-size:12px;color:#8b949e;margin-bottom:8px;">Tweet text ({len(tweet)}/280 chars):</p>
    <div class="tweet-box">{tweet}<div class="chars">{len(tweet)}/280</div></div>
    <div class="buttons">
      <a href="{reject_url}"  class="btn-reject">✕ Reject</a>
      <a href="{approve_url}" class="btn-approve">✓ Approve &amp; Post</a>
    </div>
    <p style="font-size:11px;color:#484f58;margin-top:14px;text-align:center;">
      Link expires in 24h. Approving posts the tweet + image to X immediately.
    </p>
  </div>
  <div class="footer">X Viral Bot · {NICHE} · {X_HANDLE}</div>
</div>
</body>
</html>"""

    msg = MIMEMultipart("related")
    msg["Subject"] = f"[X Bot] Approve tweet — {datetime.now().strftime('%b %d')}"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECIPIENT

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(html, "html"))
    msg.attach(alt)

    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            img_data = f.read()
        img_mime = MIMEImage(img_data, _subtype="png")
        img_mime.add_header("Content-ID", "<tweetcard>")
        img_mime.add_header("Content-Disposition", "inline", filename="tweet_card.png")
        msg.attach(img_mime)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())

    log.info(f"Approval email sent to {EMAIL_RECIPIENT}")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("X Viral Bot pipeline started")

    try:
        trend_data = research_trends()
        tweet = generate_tweet(trend_data)

        image_token = str(uuid.uuid4())
        image_path = generate_tweet_image(tweet, image_token)

        if POST_DIRECTLY and all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET]):
            post_to_x(tweet, image_path)
            save_pending(tweet, trend_data, image_path)
            log.info("Pipeline complete. Tweet + image posted directly to X.")
        else:
            token = save_pending(tweet, trend_data, image_path)
            send_approval_email(tweet, trend_data, token, image_path)
            log.info("Pipeline complete. Approval email sent.")
    except Exception as e:
        log.error(f"Pipeline failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    if "--hooks" in sys.argv:
        hooks = generate_hooks()
        print("\n--- 10 scroll-stopping hooks ---\n")
        for i, h in enumerate(hooks, 1):
            print(f"{i}. {h}")
        print()
    elif "--rewrite" in sys.argv:
        idx = sys.argv.index("--rewrite")
        draft = " ".join(sys.argv[idx + 1:]).strip() if idx + 1 < len(sys.argv) else ""
        if not draft:
            print("Usage: python3 bot.py --rewrite \"Your draft tweet text here\"")
            sys.exit(1)
        rewritten = rewrite_tweet(draft)
        print("\n--- Rewritten (%d/280 chars) ---\n" % len(rewritten))
        print(rewritten)
        print("\n---")
    elif "--preview" in sys.argv:
        print("Researching trend...")
        trend_data = research_trends()
        print("\nGenerating post...\n")
        tweet = generate_tweet(trend_data)
        print("--- Trend ---")
        print(f"  {trend_data.get('trend', '')}")
        print(f"  Angle: {trend_data.get('angle', '')}")
        print(f"\n--- Your post ({len(tweet)}/280 chars) ---\n")
        print(tweet)
        image_token = str(uuid.uuid4())
        image_path = generate_tweet_image(tweet, image_token)
        print(f"\n--- Tweet card saved ---\n  {image_path}\n---")
    else:
        main()
