#!/usr/bin/env python3
import argparse
import feedparser
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    load_sources, load_categories, url_id, week_number,
    daily_path, weekly_path, detect_category, clean_html,
    truncate, setup_logging, save_json
)

log = setup_logging("fetch_rss")


def parse_entry_date(entry):
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def in_window(dt, window_start, window_end):
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return window_start <= dt <= window_end


def extract_article_url(entry, feed_url):
    candidates = []
    link = getattr(entry, "link", None)
    if link:
        candidates.append(link)
    eid = getattr(entry, "id", None)
    if eid and eid.startswith("http"):
        candidates.append(eid)
    for enc in getattr(entry, "enclosures", []):
        url = getattr(enc, "href", None) or getattr(enc, "url", None)
        if url and url.startswith("http"):
            candidates.append(url)
    for url in candidates:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        if len(path) > 3 and not path.endswith((".rss", ".xml", ".atom")):
            return url
    return candidates[0] if candidates else ""


def fetch_source(source, window_start, window_end, categories, cat_overrides):
    rss_url = source["rss_url"]
    source_id = source["id"]
    log.info(f"  Fetching {source['name']} ...")
    try:
        feed = feedparser.parse(rss_url, request_headers={"User-Agent": "SciDigest/3.0"})
    except Exception as e:
        log.warning(f"    ERROR {source_id}: {e}")
        return []

    if feed.bozo and not feed.entries:
        log.warning(f"    Malformed/empty feed: {source_id}")
        return []

    articles = []
    seen_urls = set()

    for entry in feed.entries:
        pub_date = parse_entry_date(entry)
        if not in_window(pub_date, window_start, window_end):
            continue

        url = extract_article_url(entry, rss_url)
        if not url:
            continue

        uid = url_id(url)
        if uid in seen_urls:
            continue
        seen_urls.add(uid)

        title = clean_html(getattr(entry, "title", "")).strip()
        if not title:
            continue

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

        article = {
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
        article["id"] = ""
        articles.append(article)

    log.info(f"    → {len(articles)} articles")
    return articles


def deduplicate(articles):
    seen = set()
    result = []
    for a in articles:
        uid = url_id(a["url"])
        if uid not in seen:
            seen.add(uid)
            result.append(a)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daily", "weekly"], required=True)
    parser.add_argument("--date")
    parser.add_argument("--week", type=int)
    parser.add_argument("--sources")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)

    if args.mode == "daily":
        if args.date:
            ref = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            ref = now.replace(hour=0, minute=0, second=0, microsecond=0)
        window_start = ref
        window_end = ref + timedelta(hours=24)
        out_path = daily_path(ref.strftime("%Y-%m-%d"))
        label = ref.strftime("%Y-%m-%d")
    else:
        wnum = args.week or week_number(now)
        year = now.year
        monday = datetime.fromisocalendar(year, wnum, 1).replace(tzinfo=timezone.utc)
        window_start = monday
        window_end = monday + timedelta(days=7)
        out_path = weekly_path(wnum)
        label = f"W{wnum:02d}"

    log.info(f"Mode: {args.mode.upper()} | Period: {label}")
    log.info(f"Window: {window_start.date()} → {window_end.date()}")

    sources = load_sources()
    categories, _, cat_overrides = load_categories()

    if args.sources:
        wanted = set(args.sources.split(","))
        sources = [s for s in sources if s["id"] in wanted]

    log.info(f"Sources: {len(sources)}")

    all_articles = []
    source_counts = {}

    for source in sources:
        if not source.get("has_rss", False):
            continue
        articles = fetch_source(source, window_start, window_end, categories, cat_overrides)
        source_counts[source["id"]] = len(articles)
        all_articles.extend(articles)
        time.sleep(0.5)

    before = len(all_articles)
    all_articles = deduplicate(all_articles)
    log.info(f"Total: {len(all_articles)} (removed {before - len(all_articles)} duplicates)")

    from collections import Counter
    for cat, n in Counter(a["category"] for a in all_articles).most_common():
        log.info(f"  {cat:15s} {n}")

    if not args.dry_run:
        save_json(all_articles, out_path)
        log.info(f"Saved → {out_path}")


if __name__ == "__main__":
    main()
