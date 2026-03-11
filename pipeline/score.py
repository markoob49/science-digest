#!/usr/bin/env python3
import argparse
import sys
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    load_sources, week_number, daily_path, weekly_path,
    suffix_path, setup_logging, load_json, save_json
)

log = setup_logging("score")

KEYWORDS_BOOST = [
    "breakthrough", "first", "discovery", "novel", "unprecedented",
    "record", "revolutionar", "landmark", "major advance",
    "впервые", "открытие", "прорыв",
]

MAX_PER_SOURCE_L1 = 3
MAX_PER_SOURCE_L2 = 5
LEVEL1_PER_CAT_DAILY = 1
LEVEL1_PER_CAT_WEEKLY = 2
LEVEL2_THRESHOLD = 80


def build_base_score_map(sources):
    return {s["id"]: s.get("base_score", 30) for s in sources}


def score_article(article, base_scores, ref_date):
    score = 0
    score += base_scores.get(article.get("source_id", ""), 30)
    n = len(article.get("summary", ""))
    score += 30 if n > 300 else 20 if n > 150 else 10 if n > 50 else 0
    text = (article.get("title", "") + " " + article.get("summary", "")).lower()
    hits = sum(1 for kw in KEYWORDS_BOOST if kw in text)
    score += min(hits * 5, 20)
    try:
        pub = datetime.strptime(article.get("date", ""), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days_old = max((ref_date - pub).days, 0)
        score += 20 if days_old == 0 else 15 if days_old == 1 else 10 if days_old <= 3 else 5
    except ValueError:
        score += 5
    title_len = len(article.get("title", ""))
    if title_len < 20:
        score -= 10
    elif title_len > 60:
        score += 5
    return max(score, 0)


def assign_levels(articles, mode):
    level1_per_cat = LEVEL1_PER_CAT_DAILY if mode == "daily" else LEVEL1_PER_CAT_WEEKLY
    articles = sorted(articles, key=lambda a: a["score"], reverse=True)

    source_count_l1 = defaultdict(int)
    cat_count_l1 = defaultdict(int)
    l1_ids = set()

    for i, a in enumerate(articles):
        cat = a.get("category", "general")
        src = a.get("source_id", "")
        if cat_count_l1[cat] < level1_per_cat and source_count_l1[src] < MAX_PER_SOURCE_L1:
            a["level"] = 1
            cat_count_l1[cat] += 1
            source_count_l1[src] += 1
            l1_ids.add(i)

    source_count_l2 = defaultdict(int)
    for i, a in enumerate(articles):
        if i in l1_ids:
            source_count_l2[a.get("source_id", "")] += 1

    for i, a in enumerate(articles):
        if i in l1_ids:
            continue
        src = a.get("source_id", "")
        if a["score"] >= LEVEL2_THRESHOLD and source_count_l2[src] < MAX_PER_SOURCE_L2:
            a["level"] = 2
            source_count_l2[src] += 1
        else:
            a["level"] = 3

    return articles


def assign_ids(articles, label):
    cat_counters = defaultdict(int)
    for a in articles:
        cat = a.get("category", "GEN").upper()[:3]
        cat_counters[cat] += 1
        a["id"] = f"{label}-{cat}-{cat_counters[cat]:03d}"
    return articles


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daily", "weekly"], required=True)
    parser.add_argument("--date")
    parser.add_argument("--week", type=int)
    args = parser.parse_args()

    now = datetime.now(timezone.utc)

    if args.mode == "daily":
        ref = (datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
               if args.date else now.replace(hour=0, minute=0, second=0, microsecond=0))
        raw_path = daily_path(ref.strftime("%Y-%m-%d"))
        label = "D" + ref.strftime("%Y%m%d")
    else:
        wnum = args.week or week_number(now)
        raw_path = weekly_path(wnum)
        label = f"W{wnum:02d}"

    scored_path = suffix_path(raw_path, "_scored")

    articles = load_json(raw_path)
    if not articles:
        log.error(f"No articles at {raw_path}")
        sys.exit(1)

    log.info(f"Loaded {len(articles)} articles")
    sources = load_sources()
    base_scores = build_base_score_map(sources)
    ref_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    for a in articles:
        a["score"] = score_article(a, base_scores, ref_date)

    articles = assign_levels(articles, args.mode)
    articles = assign_ids(articles, label)

    levels = Counter(a.get("level") for a in articles)
    log.info(f"Level 1: {levels[1]}  Level 2: {levels[2]}  Level 3: {levels[3]}")

    save_json(articles, scored_path)
    log.info(f"Saved → {scored_path}")


if __name__ == "__main__":
    main()
