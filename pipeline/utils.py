#!/usr/bin/env python3
"""Shared utilities for the science digest pipeline."""

import json
import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"


def load_sources() -> list[dict]:
    with open(CONFIG_DIR / "sources.json") as f:
        return json.load(f)["sources"]


def load_categories() -> dict:
    with open(CONFIG_DIR / "categories.json") as f:
        data = json.load(f)
        return data["categories"], data.get("category_order", []), data.get("source_category_overrides", {})


def url_id(url: str) -> str:
    """Stable short ID from URL (md5 hex, 8 chars)."""
    return hashlib.md5(url.encode()).hexdigest()[:8]


def week_number(dt: datetime | None = None) -> int:
    """ISO week number for a given date (default: today)."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.isocalendar()[1]


def daily_path(date_str: str) -> Path:
    """data/daily/YYYY-MM-DD_raw.json"""
    return DATA_DIR / "daily" / f"{date_str}_raw.json"


def weekly_path(week: int) -> Path:
    """data/W{nn}_raw.json"""
    return DATA_DIR / f"W{week:02d}_raw.json"


def suffix_path(base_path: Path, suffix: str) -> Path:
    """Replace _raw with _scored / _translated / etc."""
    return base_path.parent / base_path.name.replace("_raw", suffix)


def detect_category(article: dict, categories: dict, overrides: dict) -> str:
    """
    Assign category by:
    1. source override (always wins)
    2. keyword match in title + summary
    3. fallback to source category_default
    4. 'general'
    """
    source_id = article.get("source_id", "")
    if source_id in overrides:
        return overrides[source_id]

    text = (article.get("title", "") + " " + article.get("summary", "")).lower()
    cat_default = article.get("category_default", "general")

    best_cat = None
    best_count = 0
    for cat, info in categories.items():
        if cat == "general":
            continue
        count = sum(1 for kw in info.get("keywords", []) if kw in text)
        if count > best_count:
            best_count = count
            best_cat = cat

    if best_cat and best_count >= 2:
        return best_cat
    return cat_default


def clean_html(text: str) -> str:
    """Strip HTML tags from text."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def truncate(text: str, max_chars: int = 500) -> str:
    """Truncate text at word boundary."""
    if not text or len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.8:
        truncated = truncated[:last_space]
    return truncated + "…"


def setup_logging(name: str = "pipeline") -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )
    return logging.getLogger(name)


def load_json(path: Path) -> list | dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def save_json(data: list | dict, path: Path, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
