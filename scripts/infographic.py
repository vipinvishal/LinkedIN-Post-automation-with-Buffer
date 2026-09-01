"""
Infographic generator for LinkedIn posts.

Pipeline:
  generate_process_content()  → Gemini → "how it works" content dict
  render_infographic()        → Playwright → PNG
  upload_to_linkedin()        → LinkedIn media API → asset URN
"""

import os
import re
import json
import pathlib
import requests

_PROCESS_CONTENT_PROMPT = """
Generate content for a light-theme, detailed "how it works" LinkedIn infographic that breaks a topic down
into a clear beginning → middle → end arc, illustrated like a step-by-step technical diagram. This is for
an individual engineer's personal learning post — technical, precise, no business framing.

Topic: {topic}

The LinkedIn post this infographic will accompany (the infographic MUST illustrate the SAME narrative —
same claims, same specifics. Do not introduce facts not present in this post):
{post_text}

First, read the post and identify its natural 3-part arc — use whichever framing actually fits:
- If it's a technical mechanism: INPUT → PROCESS → OUTPUT (e.g. "You Write Code" → "Model Predicts" →
  "Token Sampled")
- If it's a problem/solution post: THE PROBLEM → THE FIX → THE RESULT
- If it's a personal story or news reaction: BEFORE → THE MOMENT IT CHANGED → AFTER
Pick whichever of these actually matches the post — don't force a mechanism onto a post that doesn't have one.

This infographic has THREE sections. All of it must walk through that SAME 3-part arc, at increasing detail:

1. "stages" — exactly 3 items for the 3-part arc identified above. Each has:
   - "label": 2-3 words, Title Case
   - "snippet": a short fake code/terminal/data line (max 22 characters) that represents that stage —
     e.g. 'print("hello")', '01001 → 01110', '> Hello!', 'retry_count = 3', 'status: FAILED'. Even for a
     personal/news story, phrase the stage as a short code- or log-line-flavored fragment (it's a visual
     device, not literal code) — e.g. for "the bug appeared": 'ERROR: null ptr'.

2. "steps" — exactly 4 numbered cards walking through the arc in more detail than "stages" (step 1 is the
   simplest entry point, step 4 is the payoff/end state). Each has:
   - "label": 2-4 words, Title Case
   - "points": exactly 3 short tag-like phrases, max 3 words each, plain text

3. Two flow summaries of the SAME arc at different granularities:
   - "flow_a_items": 5-6 short words/phrases (1-2 words each) — the detailed/granular pipeline
   - "flow_b_items": 4-5 short words/phrases (1-2 words each) — the simplified big-picture version

Also:
- title_line1 : a short, punchy, curiosity-driving hook phrase (3-5 words) matching the post's hook,
  Title Case, NOT the raw topic name. Favor a bold, opinionated framing over a neutral description —
  a contrast/reveal structure works well when it genuinely fits (e.g. "X Isn't One Thing." / "It's Y."
  split across line1/line2), but don't force it if the post's actual angle is something else.
- title_line2 : the payoff / rest of the hook (3-5 words), Title Case, completes line1. This is the line
  that should stop a scroll — make it hit harder than line1, not just continue it politely.
- tagline : one short, sharp line (under 10 words) that sets up the breakdown — specific, not generic
  ("From typing code to seeing the output" beats "How it works").
- hook : one short, punchy, quotable sentence (max 20 words) — the same core takeaway as the post's
  closing thought, phrased so it reads well standalone (this is the line people screenshot).
- section_label : a short (2-4 words), all-caps, punchy label naming what this specific breakdown is
  (e.g. "UNDER THE HOOD", "HOW IT ACTUALLY WORKS", "THE REAL BREAKDOWN") — specific to this topic, not
  a generic placeholder.

None of these five should sound like a textbook caption. Write them like a sharp engineer trying to
make someone stop scrolling and actually read the post — direct, a little provocative, zero filler
words ("comprehensive", "seamless", "revolutionize", "unlock").

Return ONLY valid JSON — no markdown, no explanation:
{{
  "title_line1": "...", "title_line2": "...", "tagline": "...", "hook": "...", "section_label": "...",
  "stages": [{{"label": "...", "snippet": "..."}}, {{"label": "...", "snippet": "..."}}, {{"label": "...", "snippet": "..."}}],
  "steps": [
    {{"label": "...", "points": ["...", "...", "..."]}},
    {{"label": "...", "points": ["...", "...", "..."]}},
    {{"label": "...", "points": ["...", "...", "..."]}},
    {{"label": "...", "points": ["...", "...", "..."]}}
  ],
  "flow_a_items": ["...", "...", "...", "...", "..."],
  "flow_b_items": ["...", "...", "...", "..."]
}}
""".strip()

_SYSTEM = "You generate structured JSON content for visual infographics. Return only valid JSON, no extra text."


def _clean_text(s: str) -> str:
    """Strip stray markdown/comment markers the model sometimes leaks into 'plain text' fields."""
    s = s.strip()
    s = re.sub(r'^(#+|//+)\s*', '', s)
    s = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', s)
    s = re.sub(r'_{1,2}(.+?)_{1,2}', r'\1', s)
    s = s.replace('`', '')
    return s.strip()


def _clean_process_content(data: dict) -> dict:
    data["title_line1"] = _clean_text(data["title_line1"])
    data["title_line2"] = _clean_text(data["title_line2"])
    data["tagline"] = _clean_text(data["tagline"])
    data["hook"] = _clean_text(data["hook"])
    data["section_label"] = _clean_text(data.get("section_label", "")).upper() or "HOW IT ACTUALLY WORKS"
    for stage in data["stages"]:
        stage["label"] = _clean_text(stage["label"])
        stage["snippet"] = _clean_text(stage["snippet"])
    for step in data["steps"]:
        step["label"] = _clean_text(step["label"])
        step["points"] = [_clean_text(p) for p in step["points"]]
    data["flow_a_items"] = [_clean_text(i) for i in data["flow_a_items"]]
    data["flow_b_items"] = [_clean_text(i) for i in data["flow_b_items"]]
    return data


def generate_process_content(topic: str, post_text: str, generate_text_fn) -> dict:
    """Call the LLM to produce the 'how it works' process-infographic content dict."""
    prompt = _PROCESS_CONTENT_PROMPT.format(topic=topic, post_text=post_text[:2500])

    for attempt in range(2):
        raw = generate_text_fn(prompt, _SYSTEM)
        raw = raw.strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
        raw = raw.strip()
        try:
            data = json.loads(raw)
            required = ["title_line1", "title_line2", "tagline", "hook",
                        "stages", "steps", "flow_a_items", "flow_b_items"]
            if all(k in data for k in required) and len(data["stages"]) == 3 and len(data["steps"]) == 4:
                return _clean_process_content(data)
        except (json.JSONDecodeError, KeyError):
            pass

    raise RuntimeError("Failed to generate valid process-infographic JSON after 2 attempts.")


def render_infographic(content: dict, out_path: str, template: str = "process_infographic.html.j2") -> str:
    """Render the content dict to a PNG using Playwright. Returns PNG path."""
    import sys
    root = pathlib.Path(__file__).parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from renderer.render import render
    return render(content, out_path, template=template)


def upload_to_linkedin(png_path: str, access_token: str, person_id: str) -> str:
    """
    Upload PNG to LinkedIn via the media upload API.
    Returns the asset URN to embed in the ugcPost.
    """
    headers_json = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    # Step 1 — register upload
    reg = requests.post(
        "https://api.linkedin.com/v2/assets?action=registerUpload",
        headers=headers_json,
        json={
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner":   f"urn:li:person:{person_id}",
                "serviceRelationships": [{
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent",
                }],
            }
        },
        timeout=20,
    )
    reg.raise_for_status()
    val = reg.json()["value"]
    upload_url = val["uploadMechanism"][
        "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
    ]["uploadUrl"]
    asset_urn = val["asset"]

    # Step 2 — upload image bytes
    with open(png_path, "rb") as f:
        img_bytes = f.read()

    put = requests.put(
        upload_url,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "image/png"},
        data=img_bytes,
        timeout=60,
    )
    put.raise_for_status()

    print(f"  [infographic] Uploaded → {asset_urn}")
    return asset_urn
