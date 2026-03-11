#!/usr/bin/env python3
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
BATCH_SIZE = 20
BATCH_SIZE_FULL = 5        # меньше батч для статей с summary
MAX_TOKENS_FULL = 8192     # максимум для haiku
MAX_TOKENS_TITLE = 4096
MAX_RETRIES = 3
RETRY_DELAY = 5

SYSTEM_PROMPT = """You are a professional scientific translator.
Translate the given scientific news items into Russian (ru) and Hebrew (he).

RULES:
- Russian: accurate scientific translation, not paraphrase.
- Hebrew: Modern Israeli Hebrew scientific journalism register.
  * Keep source/journal names in original Latin script.
  * Use Western Arabic numerals (0-9), not Hebrew numerals.
- Respond ONLY with valid JSON, no preamble or markdown.

Output format:
{
  "url_hash": {
    "ru": {"title": "...", "summary": "..."},
    "he": {"title": "...", "summary": "..."}
  }
}
Where url_hash is the 8-char md5 hash of the URL provided in input."""


def load_cache():
    if CACHE_PATH.exists():
        with open(CACHE_PATH) as f:
            return json.load(f)
    return {}


def save_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def translate_batch(items, client, dry_run):
    if dry_run:
        return {i["url_hash"]: {
            "ru": {"title": f"[RU] {i['title']}", "summary": f"[RU] {i.get('summary','')}"},
            "he": {"title": f"[HE] {i['title']}", "summary": f"[HE] {i.get('summary','')}"},
        } for i in items}

    user_content = json.dumps(
        [{"url_hash": i["url_hash"], "title": i["title"], "summary": i.get("summary") or ""} for i in items],
        ensure_ascii=False
    )

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}]
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            return json.loads(raw)
        except json.JSONDecodeError as e:
            log.warning(f"JSON error attempt {attempt}: {e}")
            if attempt == MAX_RETRIES:
                return {}
        except anthropic.APIError as e:
            log.warning(f"API error attempt {attempt}: {e}")
            if attempt == MAX_RETRIES:
                return {}
            time.sleep(RETRY_DELAY * attempt)
    return {}


def translate_articles(articles, dry_run=False):
    client = anthropic.Anthropic() if not dry_run else None
    cache = load_cache()

    to_translate_full = []
    to_translate_title = []
    cached = 0

    for a in articles:
        h = url_id(a["url"])
        if h in cache:
            a["translations"] = cache[h]
            cached += 1
        elif a.get("level") in (1, 2):
            to_translate_full.append(a)
        else:
            to_translate_title.append(a)

    log.info(f"From cache: {cached}, full: {len(to_translate_full)}, title-only: {len(to_translate_title)}")

    def process(batch_articles, include_summary):
        bsize = BATCH_SIZE_FULL if include_summary else BATCH_SIZE
        mtokens = MAX_TOKENS_FULL if include_summary else MAX_TOKENS_TITLE
        for i in range(0, len(batch_articles), bsize):
            batch = batch_articles[i:i + bsize]

            items = [{"url_hash": url_id(a["url"]), "title": a["title"],
                      **({"summary": a.get("summary", "")} if include_summary else {})}
                     for a in batch]
            log.info(f"Translating batch {i//BATCH_SIZE+1} ({'full' if include_summary else 'title-only'}), {len(items)} items")
            result = translate_batch(items, client, dry_run, max_tokens=mtokens)
            for a in batch:
                h = url_id(a["url"])
                if h in result:
                    trans = result[h]
                    if not include_summary:
                        for lang in ("ru", "he"):
                            if lang in trans:
                                trans[lang].pop("summary", None)
                    a["translations"] = trans
                    cache[h] = trans
                else:
                    a["translations"] = {}
            save_cache(cache)
            if not dry_run:
                time.sleep(1)

    process(to_translate_full, True)
    process(to_translate_title, False)
    return articles


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daily", "weekly"], required=True)
    parser.add_argument("--date")
    parser.add_argument("--week", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)

    if args.mode == "daily":
        ref = (datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
               if args.date else now.replace(hour=0, minute=0, second=0, microsecond=0))
        raw_path = daily_path(ref.strftime("%Y-%m-%d"))
    else:
        wnum = args.week or week_number(now)
        raw_path = weekly_path(wnum)

    scored_path = suffix_path(raw_path, "_scored")
    translated_path = suffix_path(raw_path, "_translated")

    articles = load_json(scored_path)
    if not articles:
        log.error(f"No articles at {scored_path}")
        sys.exit(1)

    log.info(f"Loaded {len(articles)} articles")
    articles = translate_articles(articles, dry_run=args.dry_run)

    translated = sum(1 for a in articles if a.get("translations"))
    log.info(f"Translated: {translated}/{len(articles)}")

    save_json(articles, translated_path)
    log.info(f"Saved → {translated_path}")


if __name__ == "__main__":
    main()
