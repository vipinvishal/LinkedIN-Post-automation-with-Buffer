"""
Hook Matrix — scroll-stopping openers tuned to ONE niche: an individual engineer studying AI/ML
in public (not a founder, not a company voice). Every formula below is written for that persona.

Five categories, as requested:
  1. Pattern interrupts   — visually/logically break the scroll rhythm
  2. Psychological triggers — status, insider-knowledge, specificity-as-authority
  3. Curiosity gaps       — tease + resolve within the first ~210 chars (LinkedIn's "see more" cutoff)
  4. Power phrases        — grounded, first-person connective tissue (not sales language)
  5. Hook structures      — full opening skeletons adapted from proven viral formulas

Selection is deterministic (day-of-year + slot index), same philosophy as the STYLE_1/STYLE_2
rotation in generate_and_schedule.py — every formula gets exercised evenly over time instead of
clustering by chance, so it's possible to later look back and see which formula/topic pairing
actually performed best.
"""

# ══════════════════════════════════════════════════════════════════════════════
# 5. HOOK STRUCTURES — full opening skeletons (each becomes the post's step-1 instruction)
# ══════════════════════════════════════════════════════════════════════════════

HOOK_MATRIX = [
    {
        "id": "HS1",
        "category": "structure",
        "name": "Number-First Technical Reveal",
        "best_for": ["news", "advanced"],
        "skeleton": (
            "Open with ONE oddly specific number pulled straight from the research — not rounded "
            "('48.9 points', '$0.0043', '3.2x', never '50 points' or 'a lot cheaper'). No lead-in "
            "sentence before it. The number IS line 1, and nothing else is."
        ),
        "example": "GPQA scores jumped 48.9 points in a single year.",
    },
    {
        "id": "HS2",
        "category": "structure",
        "name": "Time-Anchor Confession",
        "best_for": ["personal", "educational"],
        "skeleton": (
            "Line 1: '{N} days/weeks ago, I {couldn't do the thing / believed the wrong thing}.' "
            "Line 2 must be the first concrete, dated consequence — a real number, never 'here's "
            "what happened next'. No announced candor ('let me be honest', 'confession:') — just "
            "the dated fact, stated flat."
        ),
        "example": "Two days ago I couldn't reproduce a published benchmark on my own hardware.",
    },
    {
        "id": "HS3",
        "category": "structure",
        "name": "Controlled A/B Anecdote",
        "best_for": ["advanced", "news"],
        "skeleton": (
            "Line 1: {action} -> {outcome A}. Line 2: the identical action with exactly ONE variable "
            "changed -> {the opposite outcome B}. Line 3: 'Same X. Same Y. The only variable was Z.' "
            "The two situations must differ by exactly one thing — never stack multiple changes."
        ),
        "example": "Same prompt. Same model. Default temperature: confident nonsense. Temperature 0: the right answer.",
    },
    {
        "id": "HS4",
        "category": "structure",
        "name": "Curiosity-Gap Teaser",
        "best_for": ["news", "personal"],
        "skeleton": (
            "Line 1: 'My {script/model/pipeline} did something I didn't expect.' Line 2: deepen the "
            "gap with one concrete detail, still no reveal. Line 3 (still inside the first ~210 "
            "characters, before any 'see more' cutoff): the specific, concrete reveal — a number or "
            "a name, never a vague 'and it changed everything'."
        ),
        "example": "My eval script returned a number that shouldn't have been possible. Turned out the bug was in my own harness, not the model.",
    },
    {
        "id": "HS5",
        "category": "structure",
        "name": "Contrarian + Dated Receipts",
        "best_for": ["news", "advanced"],
        "skeleton": (
            "Line 1: '{X} has been \"dead\"/\"solved\"/\"obsolete\" since {year}.' Then 3-4 short "
            "dated entries (Month Year - claim) showing the same prediction repeating. Then the "
            "counter-evidence: what actually happened, with real numbers."
        ),
        "example": "RAG has been 'dead' since 2023. Every quarter since, someone's called it. Here's what actually shipped instead.",
    },
    {
        "id": "HS6",
        "category": "structure",
        "name": "Anecdote-Meets-Evidence Bridge",
        "best_for": ["advanced", "educational"],
        "skeleton": (
            "Line 1: a small, first-person technical noticing. Line 2: 'Turned out it was already "
            "measured.' (a plain bridge — never 'the result?' or 'here's what the data says'). The "
            "arrow-bullet evidence that follows becomes the post's main body."
        ),
        "example": "I thought I'd found a weird tokenizer edge case. Turned out it was already documented.",
    },
    {
        "id": "HS7",
        "category": "structure",
        "name": "Explain-While-Learning",
        "best_for": ["educational"],
        "skeleton": (
            "Line 1: name the jargon term plainly, no question mark ('{Term}, the part I kept "
            "getting wrong.'). Frame it as the thing YOU had to re-learn, not a dumbed-down "
            "explainer for someone else — explain it the way you wish someone had explained it "
            "to you the first time."
        ),
        "example": "KV cache. The thing I nodded along to for months without actually understanding.",
    },
    {
        "id": "HS8",
        "category": "structure",
        "name": "False-Binary Dissolve",
        "best_for": ["advanced"],
        "skeleton": (
            "Line 1: 'Everyone reaches for one of two fixes when {problem}: {A} or {B}.' Line 2: "
            "one line each killing A and B. Then: 'Both miss {the shared flaw}.' The rest of the "
            "post introduces the actual solution as the third option. This is the post's one "
            "allowed contrast frame — don't add another."
        ),
        "example": "Everyone reaches for either fine-tuning or a bigger context window. Both miss where the latency actually comes from.",
    },
    {
        "id": "PI1",
        "category": "pattern_interrupt",
        "name": "The Broken Assumption",
        "best_for": ["personal", "educational"],
        "skeleton": (
            "Line 1: state a belief you held plainly, past tense, no hedge ('I thought {X} meant "
            "{Y}.'). Line 2: the specific moment or data point that broke it, with a number or a name."
        ),
        "example": "I thought quantization always cost accuracy. Then I benchmarked a 4-bit model that beat the FP16 baseline.",
    },
    {
        "id": "PI2",
        "category": "pattern_interrupt",
        "name": "The Silent Change",
        "best_for": ["news", "advanced"],
        "skeleton": (
            "Line 1: list what did NOT change (no fine-tuning, no new training data, no architecture "
            "change). Line 2: the one thing that did change, and the outcome that flipped because of it."
        ),
        "example": "No fine-tuning. No new training data. One sampling parameter changed, and accuracy jumped 12 points.",
    },
]

_ALL_IDS = [h["id"] for h in HOOK_MATRIX]

# ══════════════════════════════════════════════════════════════════════════════
# 1-3. Reference categories — pattern interrupts / psychological triggers / curiosity gaps are
# each represented by at least one full structure above (tagged in "category"); these two lists
# are the underlying MECHANISMS a generated hook should embody, used as inline guidance rather
# than standalone skeletons, since they're properties of a good hook, not alternate templates.
# ══════════════════════════════════════════════════════════════════════════════

PSYCHOLOGICAL_TRIGGERS = [
    "Competence-gap (gentle status threat): 'Most people still think {common belief}. It hasn't "
    "been true since {dated fact}.'",
    "Insider-knowledge: 'This is buried on page {N} of the paper, and almost nobody reads that far.'",
    "Relatable-struggle (engineer solidarity, not manufactured vulnerability): a specific, dated "
    "technical failure with a real cost — 'Spent three days on this before finding the one-line fix.'",
    "Specificity-as-authority: an oddly precise number or config in line 1 signals hands-on testing, "
    "not a summarized blog post.",
    "Unresolved tension: state two facts that seem to contradict each other; don't resolve it until "
    "later in the post.",
]

CURIOSITY_GAP_RULES = [
    "The gap must close within the first ~210 characters (before LinkedIn's 'see more' cutoff) — "
    "never past the fold.",
    "The reveal is always a concrete detail (a number, a name, a specific mechanism), never a vague "
    "'and it changed everything' or 'you won't believe what happened next'.",
    "Never use the phrases 'here's what nobody tells you', 'what most people miss', 'this is where "
    "it gets interesting', or 'the real question is' — these read as manufactured curiosity, not "
    "real curiosity.",
]

# ══════════════════════════════════════════════════════════════════════════════
# 4. POWER PHRASES — grounded, first-person connective tissue. Not hype, not sales language.
# Offered as optional seasoning, never forced into every post.
# ══════════════════════════════════════════════════════════════════════════════

POWER_PHRASES = [
    "I ran this myself.",
    "Here's what the logs actually showed.",
    "The number that changed my mind:",
    "I tested this so I didn't have to guess.",
    "This broke my mental model of {X}.",
    "Nobody mentions this part.",
    "The real bottleneck wasn't {the assumed thing}.",
]


def select_hook_formula(content_slot: str, day_of_year: int, slot_index: int) -> dict:
    """Deterministically rotate through hook formulas tagged for this content slot (falling back
    to the full matrix if none match), so every formula gets exercised evenly over time instead
    of clustering by chance — same rotation philosophy as the STYLE_1/STYLE_2 pick."""
    candidates = [h for h in HOOK_MATRIX if content_slot in h["best_for"]] or HOOK_MATRIX
    idx = (day_of_year + slot_index) % len(candidates)
    return candidates[idx]
