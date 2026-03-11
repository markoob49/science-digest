#!/usr/bin/env python3
"""
score.py — Score articles and assign Level 1 / 2 / 3.

Usage:
    python pipeline/score.py --mode daily [--date YYYY-MM-DD]
    python pipeline/score.py --mode weekly [--week NN]
"""

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    load_sources, load_categories, week_number,
    daily_path, weekly_path, suffix_path,
    setup_logging, load_json, save_json
)

log = setup_logging("score")

# ── Base scores (sourced from sources.json) ───────────────────────────────────

def build_base_score_map(sources: list[dict]) -> dict[str, int]:
    return {s["id"]: s.get("base_score", 30) for s in sources}


# ── Scoring formula ───────────────────────────────────────────────────────────

KEYWORDS_BOOST = [
    "breakthrough", "first", "discovery", "novel", "unprecedented",
    "record", "revolutionar", "landmark", "major advance",
    "впервые", "открытие", "прорыв", "впервые в мире",
    # Hebrew terms
    "פריצת דרך", "גילוי", "ראשון",
]

def score_article(article: dict, base_scores: dict, ref_date: datetime) -> int:
    score = 0

    # 1. Source base score
    score += base_scores.get(article.get("source_id", ""), 30)

    # 2. Summary quality bonus
    n = len(article.get("summary", ""))
    score += 30 if n > 300 else 20 if n > 150 else 10 if n > 50 else 0

    # 3. Keyword bonus (max +20)
    text = (article.get("title", "") + " " + article.get("summary", "")).lower()
    hits = sum(1 for kw in KEYWORDS_BOOST if kw in text)
    score += min(hits * 5, 20)

    # 4. Recency bonus
    date_str = article.get("date", "")
    try:
        pub_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days_old = (ref_date - pub_date).days
        if days_old < 0:
            days_old = 0
        score += 20 if days_old == 0 else 15 if days_old == 1 else 10 if days_old <= 3 else 5
    except ValueError:
        score += 5  # unknown date, small bonus

    # 5. Title length heuristic — very short titles often low quality
    title_len = len(article.get("title", ""))
    if title_len < 20:
        score -= 10
    elif title_len > 60:
        score += 5

    return max(score, 0)


# ── Level assignment ──────────────────────────────────────────────────────────

MAX_PER_SOURCE_L1 = 3   # max articles from single source across ALL Level 1
MAX_PER_SOURCE_L2 = 5   # max articles from single source across ALL Level 2

LEVEL1_PER_CAT_DAILY = 1
LEVEL1_PER_CAT_WEEKLY = 2
LEVEL2_THRESHOLD = 80


def assign_levels(articles: list[dict], mode: str) -> list[dict]:
    """
    Assign level to each article:
    - Level 1: top N per category, respecting max-per-source global cap
    - Level 2: score >= threshold, respecting max-per-source cap
    - Level 3: everything else
    """
    level1_per_cat = LEVEL1_PER_CAT_DAILY if mode == "daily" else LEVEL1_PER_CAT_WEEKLY

    # Sort descending by score
    articles = sorted(articles, key=lambda a: a["score"], reverse=True)

    # --- Level 1 ---
    source_count_l1: dict[str, int] = defaultdict(int)
    cat_count_l1: dict[str, int] = defaultdict(int)
    l1_ids: set[int] = set()

    for i, a in enumerate(articles):
        cat = a.get("category", "general")
        src = a.get("source_id", "")
        if (cat_count_l1[cat] < level1_per_cat and
                source_count_l1[src] < MAX_PER_SOURCE_L1):
            a["level"] = 1
            cat_count_l1[cat] += 1
            source_count_l1[src] += 1
            l1_ids.add(i)

    # --- Level 2 ---
    source_count_l2: dict[str, int] = defaultdict(int)
    # Count L1 already toward L2 source cap
    for i, a in enumerate(articles):
        if i in l1_ids:
            source_count_l2[a.get("source_id", "")] += 1

    for i, a in enumerate(articles):
        if i in l1_ids:
            continue  # already L1
        src = a.get("source_id", "")
        if (a["score"] >= LEVEL2_THRESHOLD and
                source_count_l2[src] < MAX_PER_SOURCE_L2):
            a["level"] = 2
            source_count_l2[src] += 1
        else:
            a["level"] = 3

    return articles


# ── ID assignment ─────────────────────────────────────────────────────────────

def assign_ids(articles: list[dict], mode: str, label: str) -> list[dict]:
    """
    Assign unique IDs: W{nn}-{CAT}-{idx} or D{date}-{CAT}-{idx}
    """
    cat_counters: dict[str, int] = defaultdict(int)
    for a in articles:
        cat = a.get("category", "GEN").upper()[:3]
        cat_counters[cat] += 1
        prefix = label.replace("-", "")
        a["id"] = f"{prefix}-{cat}-{cat_counters[cat]:03d}"
    return articles


# ── Stats ─────────────────────────────────────────────────────────────────────

def print_stats(articles: list[dict]) -> None:
    from collections import Counter
    levels = Counter(a.get("level") for a in articles)
    log.info(f"Level 1: {levels[1]}  Level 2: {levels[2]}  Level 3: {levels[3]}")

    scores = [a["score"] for a in articles]
    if scores:
        log.info(f"Score range: {min(scores)} – {max(scores)}, mean: {sum(scores)/len(scores):.1f}")

    cats = Counter(a.get("category") for a in articles if a.get("level") == 1)
    log.info("Level 1 by category:")
    for cat, n in cats.most_common():
        log.info(f"  {cat:15s} {n}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Score articles")
    parser.add_argument("--mode", choices=["daily", "weekly"], required=True)
    parser.add_argument("--date", help="YYYY-MM-DD")
    parser.add_argument("--week", type=int)
    args = parser.parse_args()

    now = datetime.now(timezone.utc)

    if args.mode == "daily":
        if args.date:
            ref = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            ref = now.replace(hour=0, minute=0, second=0, microsecond=0)
        raw_path = daily_path(ref.strftime("%Y-%m-%d"))
        label = "D" + ref.strftime("%Y%m%d")
    else:
        wnum = args.week or week_number(now)
        raw_path = weekly_path(wnum)
        label = f"W{wnum:02d}"

    scored_path = suffix_path(raw_path, "_scored")

    log.info(f"Loading {raw_path}")
    articles = load_json(raw_path)
    if not articles:
        log.error(f"No articles found at {raw_path}")
        sys.exit(1)

    log.info(f"Articles loaded: {len(articles)}")

    sources = load_sources()
    base_scores = build_base_score_map(sources)

    ref_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Score
    for a in articles:
        a["score"] = score_article(a, base_scores, ref_date)

    # Assign levels
    articles = assign_levels(articles, args.mode)

    # Assign IDs
    articles = assign_ids(articles, args.mode, label)

    print_stats(articles)

    save_json(articles, scored_path)
    log.info(f"Saved → {scored_path}")


if __name__ == "__main__":
    main()
