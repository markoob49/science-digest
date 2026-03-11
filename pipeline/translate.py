#!/usr/bin/env python3
"""
translate.py — Translate articles (title + summary) to RU and HE using Anthropic API.

Strategy:
  - Level 1 + Level 2: translate title + summary (full)
  - Level 3: translate title only (cost reduction)
  - Cache: reuse translations if URL was translated in a previous run (translation_cache.json)

Usage:
    python pipeline/translate.py --mode daily [--date YYYY-MM-DD]
    python pipeline/translate.py --mode weekly [--week NN]
    python pipeline/translate.py --mode weekly --week 13 --dry-run  (no API calls, use placeholders)
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    week_number, daily_path, weekly_path, suffix_path,
    setup_logging, load_json, save_json, DATA_DIR, url_id
)

log = setup_logging("translate")

CACHE_PATH = DATA_DIR / "translation_cache.json"
BATCH_SIZE = 20          # articles per Anthropic API call
MAX_RETRIES = 3
RETRY_DELAY = 5          # seconds between retries


# ── Cache ─────────────────────────────────────────────────────────────────────

def load_cache() -> dict:
    if CACHE_PATH.exists():
        with open(CACHE_PATH) as f:
            return json.load(f)
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ── Anthropic API call ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a professional scientific translator.
Translate the given scientific news items into Russian (ru) and Hebrew (he).

RULES:
- Russian: accurate scientific translation, not paraphrase. Use proper scientific terminology.
- Hebrew: use Modern Israeli Hebrew scientific journalism register.
  * Transliterate proper names if no standard Hebrew equivalent exists.
  * Keep source/journal names and author names in original Latin script.
  * Use Western Arabic numerals (0-9), not Hebrew numerals.
  * Example: 'Nature journal' → 'כתב העת "Nature"' (keep Latin name quoted).
- For both languages: keep technical terms precise, do not simplify.
- Respond ONLY with valid JSON, absolutely no preamble, markdown, or explanation.

Output format (one object per input URL):
{
  "url_hash": {
    "ru": {"title": "...", "summary": "..."},
    "he": {"title": "...", "summary": "..."}
  }
}
Where url_hash is the 8-char md5 hash of the URL provided in input."""


def translate_batch(items: list[dict], client: anthropic.Anthropic, dry_run: bool) -> dict:
    """
    Translate a batch of articles. Returns dict keyed by url_hash.
    items: list of {"url_hash": str, "title": str, "summary": str | None}
    """
    if dry_run:
        # Return placeholder translations
        result = {}
        for item in items:
            h = item["url_hash"]
            result[h] = {
                "ru": {"title": f"[RU] {item['title']}", "summary": f"[RU] {item.get('summary', '')}"},
                "he": {"title": f"[HE] {item['title']}", "summary": f"[HE] {item.get('summary', '')}"},
            }
        return result

    user_content = json.dumps(
        [{"url_hash": i["url_hash"], "title": i["title"],
          "summary": i.get("summary") or ""} for i in items],
        ensure_ascii=False
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}]
            )
            raw = response.content[0].text.strip()
            # Strip any accidental markdown fences
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            return json.loads(raw)
        except json.JSONDecodeError as e:
            log.warning(f"  JSON decode error (attempt {attempt}): {e}")
            if attempt == MAX_RETRIES:
                log.error("  Failed to parse translation response after retries")
                return {}
        except anthropic.APIError as e:
            log.warning(f"  API error (attempt {attempt}): {e}")
            if attempt == MAX_RETRIES:
                return {}
            time.sleep(RETRY_DELAY * attempt)

    return {}


# ── Main translation logic ────────────────────────────────────────────────────

def translate_articles(articles: list[dict], dry_run: bool = False) -> list[dict]:
    client = anthropic.Anthropic() if not dry_run else None
    cache = load_cache()

    # Separate into batches based on level
    to_translate_full: list[dict] = []    # L1+L2: title + summary
    to_translate_title: list[dict] = []   # L3: title only
    already_cached = 0

    for a in articles:
        h = url_id(a["url"])
        if h in cache:
            a["translations"] = cache[h]
            already_cached += 1
            continue
        if a.get("level") in (1, 2):
            to_translate_full.append(a)
        else:
            to_translate_title.append(a)

    log.info(f"From cache: {already_cached}")
    log.info(f"To translate (full): {len(to_translate_full)}")
    log.info(f"To translate (title only): {len(to_translate_title)}")

    def process_batch_list(batch_articles: list[dict], include_summary: bool):
        for i in range(0, len(batch_articles), BATCH_SIZE):
            batch = batch_articles[i:i + BATCH_SIZE]
            items = []
            for a in batch:
                item = {"url_hash": url_id(a["url"]), "title": a["title"]}
                if include_summary:
                    item["summary"] = a.get("summary", "")
                items.append(item)

            log.info(f"  Translating batch {i//BATCH_SIZE + 1} "
                     f"({'full' if include_summary else 'title-only'}), "
                     f"{len(items)} items…")

            result = translate_batch(items, client, dry_run)

            for a in batch:
                h = url_id(a["url"])
                if h in result:
                    trans = result[h]
                    # For title-only, don't overwrite summary field
                    if not include_summary:
                        for lang in ("ru", "he"):
                            if lang in trans:
                                trans[lang].pop("summary", None)
                    a["translations"] = trans
                    cache[h] = trans
                else:
                    log.warning(f"  No translation returned for: {a['title'][:60]}")
                    a["translations"] = {}

            # Save cache incrementally (don't lose work on crash)
            save_cache(cache)

            if not dry_run:
                time.sleep(1)  # rate limiting

    process_batch_list(to_translate_full, include_summary=True)
    process_batch_list(to_translate_title, include_summary=False)

    return articles


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Translate articles")
    parser.add_argument("--mode", choices=["daily", "weekly"], required=True)
    parser.add_argument("--date")
    parser.add_argument("--week", type=int)
    parser.add_argument("--dry-run", action="store_true",
                        help="Use placeholder translations (no API calls)")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)

    if args.mode == "daily":
        if args.date:
            ref = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            ref = now.replace(hour=0, minute=0, second=0, microsecond=0)
        raw_path = daily_path(ref.strftime("%Y-%m-%d"))
    else:
        wnum = args.week or week_number(now)
        raw_path = weekly_path(wnum)

    scored_path = suffix_path(raw_path, "_scored")
    translated_path = suffix_path(raw_path, "_translated")

    log.info(f"Loading {scored_path}")
    articles = load_json(scored_path)
    if not articles:
        log.error(f"No scored articles at {scored_path}")
        sys.exit(1)

    log.info(f"Articles: {len(articles)}")

    articles = translate_articles(articles, dry_run=args.dry_run)

    # Count translation coverage
    translated = sum(1 for a in articles if a.get("translations"))
    log.info(f"Translated: {translated}/{len(articles)}")

    save_json(articles, translated_path)
    log.info(f"Saved → {translated_path}")


if __name__ == "__main__":
    main()
