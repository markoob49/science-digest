#!/usr/bin/env python3
"""
fetch_rss.py — Collect articles from all configured RSS sources.

Usage:
    python pipeline/fetch_rss.py --mode daily [--date YYYY-MM-DD]
    python pipeline/fetch_rss.py --mode weekly [--week NN]
"""

import argparse
import feedparser
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    load_sources, load_categories, url_id, week_number,
    daily_path, weekly_path, suffix_path,
    detect_category, clean_html, truncate,
    setup_logging, save_json, DATA_DIR
)

log = setup_logging("fetch_rss")

# ── Time window helpers ──────────────────────────────────────────────────────

def parse_entry_date(entry) -> datetime | None:
    """Extract publication datetime from a feedparser entry, UTC-aware."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                dt = datetime(*t[:6], tzinfo=timezone.utc)
                return dt
            except Exception:
                continue
    return None


def in_window(dt: datetime | None, window_start: datetime, window_end: datetime) -> bool:
    if dt is None:
        return False
    # Make sure dt is tz-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return window_start <= dt <= window_end


# ── URL extraction ────────────────────────────────────────────────────────────

def extract_article_url(entry, feed_url: str) -> str:
    """
    Extract the URL of the *specific article*, not the site homepage.
    Priority: entry.link > entry.id (if looks like URL) > entry.guid
    NEVER return feed_url or its domain root.
    """
    candidates = []

    link = getattr(entry, "link", None)
    if link:
        candidates.append(link)

    # entry.id is often the permalink GUID
    eid = getattr(entry, "id", None)
    if eid and eid.startswith("http"):
        candidates.append(eid)

    # Some feeds use enclosure
    for enc in getattr(entry, "enclosures", []):
        url = getattr(enc, "href", None) or getattr(enc, "url", None)
        if url and url.startswith("http"):
            candidates.append(url)

    for url in candidates:
        # Reject if it looks like just a homepage/feed root (too short path)
        from urllib.parse import urlparse
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        if len(path) > 3 and not path.endswith((".rss", ".xml", ".atom")):
            return url

    # Fallback — return the best candidate even if imperfect
    return candidates[0] if candidates else ""


# ── Per-source fetch ─────────────────────────────────────────────────────────

def fetch_source(source: dict, window_start: datetime, window_end: datetime,
                 categories: dict, cat_overrides: dict) -> list[dict]:
    """Fetch and filter articles from one RSS source."""
    rss_url = source["rss_url"]
    source_id = source["id"]

    log.info(f"  Fetching {source['name']} ({rss_url})")
    try:
        # feedparser handles redirects, gzip, etag etc.
        feed = feedparser.parse(rss_url, request_headers={"User-Agent": "SciDigest/3.0"})
    except Exception as e:
        log.warning(f"    ERROR fetching {source_id}: {e}")
        return []

    if feed.bozo and not feed.entries:
        log.warning(f"    Malformed feed or empty: {source_id} (bozo={feed.bozo_exception})")
        return []

    articles = []
    seen_urls: set[str] = set()

    for entry in feed.entries:
        pub_date = parse_entry_date(entry)

        if not in_window(pub_date, window_start, window_end):
            continue

        url = extract_article_url(entry, rss_url)
        if not url:
            log.debug(f"    Skip entry (no URL): {getattr(entry, 'title', '?')}")
            continue

        # Dedup by URL hash
        uid = url_id(url)
        if uid in seen_urls:
            continue
        seen_urls.add(uid)

        title = clean_html(getattr(entry, "title", "")).strip()
        if not title:
            continue

        # Extract summary: prefer summary > description > content
        raw_summary = ""
        for attr in ("summary", "description"):
            val = getattr(entry, attr, None)
            if val:
                raw_summary = val
                break
        if not raw_summary and hasattr(entry, "content"):
            for c in entry.content:
                if c.get("value"):
                    raw_summary = c["value"]
                    break

        summary = truncate(clean_html(raw_summary), max_chars=500)

        article: dict = {
            "url": url,
            "title": title,
            "summary": summary,
            "source_id": source_id,
            "source_name": source["name"],
            "source_lang": source.get("lang", "en"),
            "date": pub_date.strftime("%Y-%m-%d") if pub_date else "",
            "datetime": pub_date.isoformat() if pub_date else "",
            "category_default": source.get("category_default", "general"),
            "score": 0,
            "level": None,
            "translations": {},
        }

        article["category"] = detect_category(article, categories, cat_overrides)
        article["id"] = ""  # assigned in score.py after category is finalised

        articles.append(article)

    log.info(f"    → {len(articles)} articles in window")
    return articles


# ── Deduplication across sources ─────────────────────────────────────────────

def deduplicate(articles: list[dict]) -> list[dict]:
    """Remove duplicates by URL hash (keeps first occurrence = higher-priority source)."""
    seen: set[str] = set()
    result = []
    for a in articles:
        uid = url_id(a["url"])
        if uid not in seen:
            seen.add(uid)
            result.append(a)
    return result


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch RSS articles")
    parser.add_argument("--mode", choices=["daily", "weekly"], required=True)
    parser.add_argument("--date", help="YYYY-MM-DD (daily mode, default=today)")
    parser.add_argument("--week", type=int, help="Week number (weekly mode, default=current)")
    parser.add_argument("--sources", help="Comma-separated source IDs to fetch (default=all)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write output file")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)

    # Determine time window
    if args.mode == "daily":
        if args.date:
            ref = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            ref = now.replace(hour=0, minute=0, second=0, microsecond=0)
        window_start = ref
        window_end = ref + timedelta(hours=24)
        out_path = daily_path(ref.strftime("%Y-%m-%d"))
        label = ref.strftime("%Y-%m-%d")
    else:  # weekly
        wnum = args.week or week_number(now)
        # Find Monday of target week
        year = now.year
        monday = datetime.fromisocalendar(year, wnum, 1).replace(tzinfo=timezone.utc)
        window_start = monday
        window_end = monday + timedelta(days=7)
        out_path = weekly_path(wnum)
        label = f"W{wnum:02d}"

    log.info(f"Mode: {args.mode.upper()} | Period: {label}")
    log.info(f"Window: {window_start.date()} → {window_end.date()}")

    # Load config
    sources = load_sources()
    categories, _, cat_overrides = load_categories()

    # Filter sources if requested
    if args.sources:
        wanted = set(args.sources.split(","))
        sources = [s for s in sources if s["id"] in wanted]

    log.info(f"Sources to fetch: {len(sources)}")

    all_articles: list[dict] = []
    source_counts: dict[str, int] = {}

    for source in sources:
        if not source.get("has_rss", False):
            log.info(f"  Skip {source['name']} (no RSS)")
            continue

        articles = fetch_source(source, window_start, window_end, categories, cat_overrides)
        source_counts[source["id"]] = len(articles)
        all_articles.extend(articles)

        # Brief pause to avoid hammering servers
        time.sleep(0.5)

    # Deduplicate (sources.json is ordered by priority)
    before_dedup = len(all_articles)
    all_articles = deduplicate(all_articles)
    dupes = before_dedup - len(all_articles)

    log.info("─" * 60)
    log.info(f"Total articles: {len(all_articles)}  (removed {dupes} duplicates)")
    log.info("By source:")
    for src_id, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        if count > 0:
            log.info(f"  {src_id:30s} {count:4d}")

    # Category distribution
    from collections import Counter
    cat_dist = Counter(a["category"] for a in all_articles)
    log.info("By category:")
    for cat, count in cat_dist.most_common():
        log.info(f"  {cat:15s} {count:4d}")

    if args.dry_run:
        log.info("Dry run — not writing output")
        return

    save_json(all_articles, out_path)
    log.info(f"Saved → {out_path}")


if __name__ == "__main__":
    main()
