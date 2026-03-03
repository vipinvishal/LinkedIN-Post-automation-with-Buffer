#!/usr/bin/env python3
"""
X Viral Bot — Approval Server (Flask)
Runs permanently on VPS, handles approve/reject clicks from email.
Start with: python approve.py  (or via systemd — see README)
"""

import os
import json
import logging
from datetime import datetime, timedelta

import tweepy
from flask import Flask, abort
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    filename="logs/server.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

app = Flask(__name__)
PENDING_DIR = "pending"

X_API_KEY      = os.getenv("X_API_KEY")
X_API_SECRET   = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_SECRET= os.getenv("X_ACCESS_SECRET")


def load_pending(token: str) -> dict:
    path = os.path.join(PENDING_DIR, f"{token}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def update_pending(token: str, status: str):
    path = os.path.join(PENDING_DIR, f"{token}.json")
    with open(path) as f:
        data = json.load(f)
    data["status"] = status
    data["resolved_at"] = datetime.now().isoformat()
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def is_expired(created_at_str: str) -> bool:
    created = datetime.fromisoformat(created_at_str)
    return datetime.now() > created + timedelta(hours=24)


def post_to_x(tweet: str, image_path: str | None = None) -> str:
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
    log.info(f"Tweet posted! ID: {tweet_id}")
    return tweet_id


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/approve/<token>")
def approve(token):
    data = load_pending(token)
    if not data:
        return _html_response("❌ Not Found", "This approval link is invalid or already used.", "#f85149")

    if data["status"] != "pending":
        return _html_response("⚠️ Already Resolved", f"This tweet was already <strong>{data['status']}</strong>.", "#d29922")

    if is_expired(data["created_at"]):
        update_pending(token, "expired")
        return _html_response("⏰ Link Expired", "This approval link expired after 24 hours. Run the bot again.", "#d29922")

    try:
        tweet_id = post_to_x(data["tweet"], data.get("image_path"))
        update_pending(token, "approved")
        tweet_url = f"https://x.com/i/web/status/{tweet_id}"
        return _html_response(
            "✅ Tweet Posted!",
            f'Your tweet is now live on X.<br><br>'
            f'<a href="{tweet_url}" style="color:#58a6ff">View on X →</a><br><br>'
            f'<div style="background:#0d1117;border:1px solid #30363d;border-radius:10px;padding:16px;margin-top:12px;font-size:15px;line-height:1.7">'
            f'{data["tweet"]}</div>',
            "#3fb950"
        )
    except Exception as e:
        log.error(f"Failed to post tweet: {e}", exc_info=True)
        return _html_response("❌ Post Failed", f"Error posting to X: {str(e)}", "#f85149")


@app.route("/reject/<token>")
def reject(token):
    data = load_pending(token)
    if not data:
        return _html_response("❌ Not Found", "This link is invalid or already used.", "#f85149")

    if data["status"] != "pending":
        return _html_response("⚠️ Already Resolved", f"This tweet was already <strong>{data['status']}</strong>.", "#d29922")

    update_pending(token, "rejected")
    log.info(f"Tweet rejected: {token}")
    return _html_response("🗑️ Tweet Rejected", "The tweet was discarded. The bot will generate a new one tomorrow.", "#8b949e")


@app.route("/status")
def status():
    """Health check endpoint"""
    return {"status": "running", "time": datetime.now().isoformat()}, 200


def _html_response(title: str, message: str, color: str) -> str:
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{ font-family:'Segoe UI',sans-serif; background:#0d1117; color:#e6edf3;
           display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; }}
    .card {{ background:#161b22; border:1px solid #30363d; border-radius:16px;
             padding:40px; max-width:480px; width:90%; text-align:center; }}
    h1 {{ color:{color}; font-size:26px; margin:0 0 16px; }}
    p {{ color:#8b949e; font-size:15px; line-height:1.7; margin:0; }}
    .dot {{ width:48px; height:48px; border-radius:50%; background:{color}22;
            border:2px solid {color}; display:flex; align-items:center;
            justify-content:center; font-size:22px; margin:0 auto 20px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="dot">{title[0]}</div>
    <h1>{title}</h1>
    <p>{message}</p>
  </div>
</body>
</html>
"""


if __name__ == "__main__":
    os.makedirs(PENDING_DIR, exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    app.run(host="0.0.0.0", port=5000)
