#!/usr/bin/env python3
"""
Science Digest render.py
Generates self-contained HTML from W{nn}_translated.json

Usage:
    python pipeline/render.py --mode weekly --week 11 --lang ru
    python pipeline/render.py --mode weekly --week 11 --lang en
    python pipeline/render.py --mode weekly --week 11 --lang he
    python pipeline/render.py --mode weekly --week 11 --lang ru --data path/to/file.json --out docs/index.html
"""

import argparse
import json
import os
import sys
import re
from datetime import datetime, date
from collections import Counter, defaultdict
from html import escape


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

CATEGORIES = {
    "medicine":  {"ru": "Медицина",   "en": "Medicine",    "he": "רפואה",             "emoji": "🩺", "color": "#BE185D", "bg": "#FDF2F8"},
    "biology":   {"ru": "Биология",   "en": "Biology",     "he": "ביולוגיה",          "emoji": "🧬", "color": "#047857", "bg": "#F0FDF4"},
    "physics":   {"ru": "Физика",     "en": "Physics",     "he": "פיזיקה",            "emoji": "⚛️", "color": "#1D4ED8", "bg": "#EFF6FF"},
    "astronomy": {"ru": "Астрономия", "en": "Astronomy",   "he": "אסטרונומיה",       "emoji": "🔭", "color": "#6D28D9", "bg": "#F5F3FF"},
    "chemistry": {"ru": "Химия",      "en": "Chemistry",   "he": "כימיה",             "emoji": "⚗️", "color": "#C2410C", "bg": "#FFF7ED"},
    "ai_it":     {"ru": "ИИ и ИТ",   "en": "AI & IT",     "he": "בינה מלאכותית",    "emoji": "🤖", "color": "#0E7490", "bg": "#ECFEFF"},
    "climate":   {"ru": "Климат",     "en": "Climate",     "he": "אקלים",             "emoji": "🌍", "color": "#15803D", "bg": "#F0FDF4"},
    "general":   {"ru": "Наука",      "en": "Science",     "he": "מדע",               "emoji": "🔬", "color": "#374151", "bg": "#F9FAFB"},
}

UI_STRINGS = {
    "ru": {
        "level1_title": "Главные открытия недели",
        "level2_title": "Важные новости",
        "level3_title": "Полный каталог",
        "search_placeholder": "Поиск по заголовкам...",
        "filter_source": "Источник",
        "sort_by": "Сортировка",
        "sort_score": "По релевантности",
        "sort_date": "По дате",
        "sort_source": "По источнику",
        "show_more": "Показать ещё {n}",
        "show_all": "Показать все",
        "results_count": "Найдено: {n}",
        "read_article": "Читать →",
        "week_label": "Неделя {n}",
        "articles_count": "{n} статей",
        "sources_count": "{n} источников",
        "daily_link": "Ежедневный дайджест",
        "archive_link": "Архив",
        "all_categories": "Все темы",
        "stats_title": "Эта неделя",
        "stats_articles": "статей собрано",
        "stats_sources": "источников",
        "stats_top_source": "Топ источник",
        "top_sources_title": "Топ источники",
        "dist_title": "По категориям",
        "archive_title": "Архив",
        "loading": "Загрузка...",
        "no_results": "Ничего не найдено",
        "group_by_cat": "По категориям",
        "all_flat": "Все подряд",
        "collapsed_hint": "{n} статей в этой категории",
        "back_to_top": "↑ Наверх",
    },
    "en": {
        "level1_title": "Top Discoveries This Week",
        "level2_title": "Notable News",
        "level3_title": "Full Catalog",
        "search_placeholder": "Search headlines...",
        "filter_source": "Source",
        "sort_by": "Sort by",
        "sort_score": "Relevance",
        "sort_date": "Date",
        "sort_source": "Source",
        "show_more": "Show {n} more",
        "show_all": "Show all",
        "results_count": "Found: {n}",
        "read_article": "Read →",
        "week_label": "Week {n}",
        "articles_count": "{n} articles",
        "sources_count": "{n} sources",
        "daily_link": "Daily Digest",
        "archive_link": "Archive",
        "all_categories": "All Topics",
        "stats_title": "This Week",
        "stats_articles": "articles collected",
        "stats_sources": "sources",
        "stats_top_source": "Top source",
        "top_sources_title": "Top Sources",
        "dist_title": "By Category",
        "archive_title": "Archive",
        "loading": "Loading...",
        "no_results": "No results found",
        "group_by_cat": "By category",
        "all_flat": "All mixed",
        "collapsed_hint": "{n} articles in this category",
        "back_to_top": "↑ Top",
    },
    "he": {
        "level1_title": "תגליות מרכזיות השבוע",
        "level2_title": "חדשות חשובות",
        "level3_title": "קטלוג מלא",
        "search_placeholder": "חיפוש כותרות...",
        "filter_source": "מקור",
        "sort_by": "מיון לפי",
        "sort_score": "רלוונטיות",
        "sort_date": "תאריך",
        "sort_source": "מקור",
        "show_more": "הצג עוד {n}",
        "show_all": "הצג הכל",
        "results_count": "נמצאו: {n}",
        "read_article": "← קרא",
        "week_label": "שבוע {n}",
        "articles_count": "{n} מאמרים",
        "sources_count": "{n} מקורות",
        "daily_link": "עיכול יומי",
        "archive_link": "ארכיון",
        "all_categories": "כל הנושאים",
        "stats_title": "השבוע הזה",
        "stats_articles": "מאמרים נאספו",
        "stats_sources": "מקורות",
        "stats_top_source": "מקור מוביל",
        "top_sources_title": "מקורות מובילים",
        "dist_title": "לפי קטגוריה",
        "archive_title": "ארכיון",
        "loading": "טוען...",
        "no_results": "לא נמצאו תוצאות",
        "group_by_cat": "לפי קטגוריה",
        "all_flat": "הכל מעורבב",
        "collapsed_hint": "{n} מאמרים בקטגוריה זו",
        "back_to_top": "↑ למעלה",
    }
}

WEEK_RANGES = {
    11: ("9", "15", "марта", "March", "מרץ", "2026"),
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_title(article, lang):
    if lang == "en":
        return article.get("title", "")
    trans = article.get("translations", {}).get(lang, {})
    return trans.get("title") or article.get("title", "")


def get_summary(article, lang):
    if lang == "en":
        raw = article.get("summary", "")
    else:
        trans = article.get("translations", {}).get(lang, {})
        raw = trans.get("summary") or article.get("summary", "")
    return clean_summary(raw)


def clean_summary(text):
    """Strip publisher/doi/arxiv prefixes that appear at the start of summaries."""
    import re as _re
    if not text:
        return text
    # arXiv: "arXiv:2410.05406v3 Announcement: " or "arXiv:XXXX Объявление о замене: "
    text = _re.sub(r'^arXiv:\S+\s+(Announcement|Объявление\s+о\s+замене|Объявление\s+о\s+кросс-публикации)[:\s]+', '', text, flags=_re.IGNORECASE)
    # Journal prefix: "Nature, Published online: 12 March 2026; doi:XXXX " or "Nature, Опубликовано в сети: ..."
    # "Nature Biotechnology, опубликовано в интернете: 11 марта 2026 г.; doi:XXXX "
    # "Science, Volume 391, Issue 6785, Page 558-561, February 2026."
    text = _re.sub(
        r'^[\w\s\(\)&]+,\s*(Published online|Опубликовано\s+в\s+сети|опубликовано\s+(в\s+интернете|онлайн))[^;]*;\s*doi:\S+\s*',
        '', text, flags=_re.IGNORECASE
    )
    # "Science, Volume NNN, Issue NNN, Page NNN-NNN, Month YYYY."
    text = _re.sub(
        r'^[\w\s\(\)&]+,\s*Volume\s+\d+.*?(?:\d{4})\.\s*',
        '', text, flags=_re.IGNORECASE
    )
    # "doi:10.XXXX/XXXX " at start
    text = _re.sub(r'^doi:\S+\s+', '', text, flags=_re.IGNORECASE)
    return text.strip()



def safe_url(url):
    """Only allow http/https URLs to prevent javascript: injection."""
    if not url:
        return "#"
    stripped = url.strip().lower()
    if stripped.startswith(("https://", "http://")):
        return url.strip()
    return "#"

def truncate(text, max_chars=300):
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def format_date(date_str, lang):
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        if lang == "ru":
            months = ["янв", "фев", "мар", "апр", "май", "июн",
                      "июл", "авг", "сен", "окт", "ноя", "дек"]
            return f"{d.day} {months[d.month - 1]}"
        elif lang == "he":
            months = ["ינו׳", "פבר׳", "מרץ", "אפר׳", "מאי", "יוני",
                      "יולי", "אוג׳", "ספט׳", "אוק׳", "נוב׳", "דצמ׳"]
            return f"{d.day} {months[d.month - 1]}"
        else:
            return d.strftime("%b %d")
    except Exception:
        return date_str[:10]


def get_week_label(week_num, lang):
    s = UI_STRINGS[lang]
    return s["week_label"].replace("{n}", str(week_num))


def get_week_dates(week_num, lang):
    if week_num in WEEK_RANGES:
        d1, d2, ru_month, en_month, he_month, year = WEEK_RANGES[week_num]
        if lang == "ru":
            return f"{d1}–{d2} {ru_month} {year}"
        elif lang == "he":
            return f"{d1}–{d2} {he_month} {year}"
        else:
            return f"{en_month} {d1}–{d2}, {year}"
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# DATA PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def process_data(articles, lang):
    l1 = [a for a in articles if a.get("level") == 1]
    l2 = [a for a in articles if a.get("level") == 2]
    l3 = articles  # all articles for L3 catalog

    l1.sort(key=lambda a: a.get("score", 0), reverse=True)
    l2.sort(key=lambda a: a.get("score", 0), reverse=True)

    # Category counts (all levels)
    cat_counts = Counter(a.get("category", "general") for a in articles)
    # Source counts
    source_counts = Counter(a.get("source_name", "Unknown") for a in articles)

    return l1, l2, l3, cat_counts, source_counts


# ─────────────────────────────────────────────────────────────────────────────
# HTML RENDERERS
# ─────────────────────────────────────────────────────────────────────────────

def render_level1_card(article, lang, cat_info):
    title = escape(get_title(article, lang))
    summary = escape(truncate(get_summary(article, lang), 320))
    source = escape(article.get("source_name", ""))
    date_str = format_date(article.get("date", ""), lang)
    url = escape(safe_url(article.get("url", "")))
    score = article.get("score", 0)
    cat = article.get("category", "general")
    color = cat_info.get("color", "#374151")
    bg = cat_info.get("bg", "#F9FAFB")
    emoji = cat_info.get("emoji", "🔬")
    cat_name = cat_info.get(lang, cat_info.get("en", cat))

    summary_full = escape(get_summary(article, lang))
    return f'''<article class="card card-l1" data-category="{cat}" style="--cat-color:{color};--cat-bg:{bg}">
  <div class="card-accent"></div>
  <div class="card-inner">
    <div class="card-header">
      <span class="cat-badge" style="color:{color};background:{bg}">{emoji} {escape(cat_name)}</span>
      <span class="score-badge">★ {score}</span>
    </div>
    <h3 class="card-title"><a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a></h3>
    <p class="card-summary">{summary_full}</p>
    <div class="card-footer">
      <span class="card-meta">{source} · {date_str}</span>
      <a href="{url}" target="_blank" rel="noopener noreferrer" class="read-btn">{UI_STRINGS[lang]["read_article"]}</a>
    </div>
  </div>
</article>'''


def render_level2_card(article, lang, cat_info):
    title = escape(get_title(article, lang))
    summary = escape(truncate(get_summary(article, lang), 200))
    source = escape(article.get("source_name", ""))
    date_str = format_date(article.get("date", ""), lang)
    url = escape(safe_url(article.get("url", "")))
    score = article.get("score", 0)
    cat = article.get("category", "general")
    color = cat_info.get("color", "#374151")
    bg = cat_info.get("bg", "#F9FAFB")
    emoji = cat_info.get("emoji", "🔬")
    cat_name = cat_info.get(lang, cat_info.get("en", cat))
    art_id = escape(article.get("id", ""))

    summary_full = escape(get_summary(article, lang))
    return f'''<article class="card card-l2" data-category="{cat}" data-id="{art_id}" style="--cat-color:{color};--cat-bg:{bg}">
  <div class="card-accent"></div>
  <div class="card-inner">
    <div class="card-header">
      <span class="cat-badge small" style="color:{color};background:{bg}">{emoji} {escape(cat_name)}</span>
      <span class="score-badge small">★ {score}</span>
    </div>
    <h4 class="card-title"><a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a></h4>
    <p class="card-summary">{summary_full}</p>
    <div class="card-footer">
      <span class="card-meta">{source} · {date_str}</span>
      <a href="{url}" target="_blank" rel="noopener noreferrer" class="read-btn small">{UI_STRINGS[lang]["read_article"]}</a>
    </div>
  </div>
</article>'''


def render_level1_section(l1_articles, lang):
    if not l1_articles:
        return ""
    s = UI_STRINGS[lang]

    # Group by category
    by_cat = defaultdict(list)
    for a in l1_articles:
        by_cat[a.get("category", "general")].append(a)

    cards_html = ""
    for cat, arts in by_cat.items():
        cat_info = CATEGORIES.get(cat, CATEGORIES["general"])
        for art in arts:
            cards_html += render_level1_card(art, lang, cat_info)

    return f'''<section id="level1" class="digest-section">
  <div class="section-header">
    <h2 class="section-title"><span class="trophy">🏆</span> {escape(s["level1_title"])}</h2>
  </div>
  <div class="cards-grid cards-l1">
    {cards_html}
  </div>
</section>'''


def render_level2_section(l2_articles, lang):
    if not l2_articles:
        return ""
    s = UI_STRINGS[lang]

    # Group by category
    by_cat = defaultdict(list)
    for a in l2_articles:
        by_cat[a.get("category", "general")].append(a)

    sections_html = ""
    for cat, arts in by_cat.items():
        cat_info = CATEGORIES.get(cat, CATEGORIES["general"])
        color = cat_info["color"]
        emoji = cat_info["emoji"]
        cat_name = cat_info.get(lang, cat_info.get("en", cat))

        # Show first 6, hide rest
        INITIAL_SHOW = 6
        visible = arts[:INITIAL_SHOW]
        hidden = arts[INITIAL_SHOW:]

        cards = "".join(render_level2_card(a, lang, cat_info) for a in visible)
        hidden_cards = ""
        show_more_btn = ""
        if hidden:
            hidden_cards = f'<div class="l2-hidden" id="l2-hidden-{cat}" style="display:none">'
            hidden_cards += "".join(render_level2_card(a, lang, cat_info) for a in hidden)
            hidden_cards += '</div>'
            more_text = s["show_more"].replace("{n}", str(len(hidden)))
            show_more_btn = f'<button class="show-more-btn" onclick="showMoreL2(\'{cat}\')" style="border-color:{color};color:{color}">{more_text}</button>'

        sections_html += f'''<div class="l2-category-group" id="l2-cat-{cat}" data-category="{cat}">
  <div class="l2-cat-header">
    <span class="l2-cat-dot" style="background:{color}"></span>
    <span class="l2-cat-name" style="color:{color}">{emoji} {escape(cat_name)}</span>
    <span class="l2-cat-count">({len(arts)})</span>
  </div>
  <div class="cards-grid cards-l2">
    {cards}
    {hidden_cards}
  </div>
  {show_more_btn}
</div>'''

    return f'''<section id="level2" class="digest-section">
  <div class="section-header">
    <h2 class="section-title"><span class="pin">📌</span> {escape(s["level2_title"])}</h2>
  </div>
  <div id="l2-content">
    {sections_html}
  </div>
</section>'''


def render_level3_section(lang):
    s = UI_STRINGS[lang]
    return f'''<section id="level3" class="digest-section">
  <div class="section-header">
    <h2 class="section-title"><span>📋</span> {escape(s["level3_title"])}</h2>
  </div>
  <div class="l3-controls">
    <div class="search-wrap">
      <input type="search" id="l3-search" placeholder="{escape(s["search_placeholder"])}" 
             autocomplete="off" spellcheck="false">
      <span class="search-count" id="search-count"></span>
    </div>
    <div class="l3-filters">
      <select id="l3-source-filter">
        <option value="">{escape(s["filter_source"])}: все</option>
      </select>
      <select id="l3-sort">
        <option value="score">{escape(s["sort_score"])}</option>
        <option value="date">{escape(s["sort_date"])}</option>
        <option value="source">{escape(s["sort_source"])}</option>
      </select>
      <select id="l3-group">
        <option value="category">{escape(s["group_by_cat"])}</option>
        <option value="flat">{escape(s["all_flat"])}</option>
      </select>
    </div>
  </div>
  <div id="l3-list"></div>
</section>'''


def render_header(meta, lang, week_num):
    s = UI_STRINGS[lang]
    week_label = get_week_label(week_num, lang)
    week_dates = get_week_dates(week_num, lang)
    total = meta["total"]
    sources = meta["num_sources"]

    arts_text = s["articles_count"].replace("{n}", str(total))
    srcs_text = s["sources_count"].replace("{n}", str(sources))

    # Language switcher URLs
    lang_links = {
        "ru": "../index.html" if lang != "ru" else "#",
        "en": ("../en/index.html" if lang == "ru" else ("index.html" if lang == "en" else "../en/index.html")),
        "he": ("../he/index.html" if lang == "ru" else ("../he/index.html" if lang == "en" else "index.html")),
    }
    # Simpler: just relative paths
    if lang == "ru":
        lang_links = {"ru": "#", "en": "en/index.html", "he": "he/index.html"}
    elif lang == "en":
        lang_links = {"ru": "../index.html", "en": "#", "he": "../he/index.html"}
    else:
        lang_links = {"ru": "../index.html", "en": "../en/index.html", "he": "#"}

    def lang_btn(l, label):
        active = 'class="lang-btn active"' if l == lang else 'class="lang-btn"'
        href = lang_links[l]
        if href == "#":
            return f'<span {active}>{label}</span>'
        return f'<a href="{href}" {active}>{label}</a>'

    return f'''<header class="site-header" id="site-header">
  <div class="header-inner">
    <div class="header-brand">
      <span class="brand-icon">🔬</span>
      <div class="brand-text">
        <span class="brand-name">Science Digest</span>
        <span class="brand-meta">{week_label} · {week_dates} · {arts_text} · {srcs_text}</span>
      </div>
    </div>
    <nav class="header-nav">
      <a href="daily.html" class="nav-link">{escape(s["daily_link"])}</a>
      <a href="archive/" class="nav-link">{escape(s["archive_link"])}</a>
      <div class="lang-switcher">
        {lang_btn("ru", "RU")}
        {lang_btn("en", "EN")}
        {lang_btn("he", "עב")}
      </div>
    </nav>
  </div>
</header>'''


def render_category_nav(cat_counts, lang):
    s = UI_STRINGS[lang]
    buttons = f'<button class="cat-nav-btn active" data-cat="all" onclick="filterCategory(\'all\')">{escape(s["all_categories"])}</button>'

    for cat_id, cat_info in CATEGORIES.items():
        count = cat_counts.get(cat_id, 0)
        if count == 0:
            continue
        color = cat_info["color"]
        emoji = cat_info["emoji"]
        name = cat_info.get(lang, cat_info.get("en", cat_id))
        buttons += f'<button class="cat-nav-btn" data-cat="{cat_id}" onclick="filterCategory(\'{cat_id}\')" style="--cat-color:{color}">{emoji} {escape(name)} <span class="cat-nav-count">{count}</span></button>'

    return f'''<nav class="cat-nav" id="cat-nav">
  <div class="cat-nav-inner">
    {buttons}
  </div>
</nav>'''


def render_sidebar(meta, cat_counts, source_counts, lang, week_num):
    s = UI_STRINGS[lang]
    total = meta["total"]

    # Stats block
    top_source_name, top_source_count = source_counts.most_common(1)[0]
    stats_html = f'''<div class="sidebar-block">
  <div class="sidebar-block-title">📊 {escape(s["stats_title"])}</div>
  <div class="stat-row"><span class="stat-num">{total}</span> <span class="stat-label">{escape(s["stats_articles"])}</span></div>
  <div class="stat-row"><span class="stat-num">{meta["num_sources"]}</span> <span class="stat-label">{escape(s["stats_sources"])}</span></div>
  <div class="stat-top-source">{escape(s["stats_top_source"])}: <strong>{escape(top_source_name)}</strong> ({top_source_count})</div>
</div>'''

    # Category distribution bars
    max_count = max(cat_counts.values()) if cat_counts else 1
    bars_html = '<div class="sidebar-block"><div class="sidebar-block-title">📊 ' + escape(s["dist_title"]) + '</div><div class="cat-bars">'
    for cat_id, cat_info in CATEGORIES.items():
        count = cat_counts.get(cat_id, 0)
        if count == 0:
            continue
        pct = round(count / total * 100)
        bar_width = round(count / max_count * 100)
        color = cat_info["color"]
        emoji = cat_info["emoji"]
        name = cat_info.get(lang, cat_info.get("en", cat_id))
        bars_html += f'''<div class="cat-bar-row" onclick="filterCategory('{cat_id}')">
  <div class="cat-bar-label"><span>{emoji}</span><span class="cat-bar-name">{escape(name)}</span></div>
  <div class="cat-bar-track"><div class="cat-bar-fill" style="width:{bar_width}%;background:{color}" data-width="{bar_width}"></div></div>
  <div class="cat-bar-count">{count} <span class="cat-bar-pct">({pct}%)</span></div>
</div>'''
    bars_html += '</div></div>'

    # Top sources
    top_src_html = f'<div class="sidebar-block"><div class="sidebar-block-title">📰 {escape(s["top_sources_title"])}</div><ol class="top-sources-list">'
    for i, (src, cnt) in enumerate(source_counts.most_common(8), 1):
        top_src_html += f'<li><span class="src-rank">{i}</span><span class="src-name">{escape(src)}</span><span class="src-count">{cnt}</span></li>'
    top_src_html += '</ol></div>'

    # Archive nav
    archive_html = f'''<div class="sidebar-block">
  <div class="sidebar-block-title">📁 {escape(s["archive_title"])}</div>
  <div class="archive-nav">
    <a href="archive/W{week_num - 1}/ru.html" class="arch-link">← W{week_num - 1}</a>
    <span class="arch-current">W{week_num}</span>
    <span class="arch-link disabled">W{week_num + 1} →</span>
  </div>
  <a href="archive/" class="arch-all-link">Все недели →</a>
</div>'''

    return f'''<aside class="sidebar" id="sidebar">
  {stats_html}
  {bars_html}
  {top_src_html}
  {archive_html}
</aside>'''


# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────

def get_css(lang):
    rtl = lang == "he"
    dir_prop = "rtl" if rtl else "ltr"
    body_font = "'Heebo', 'DM Sans', sans-serif" if rtl else "'DM Sans', sans-serif"
    heading_font = "'Heebo', sans-serif" if rtl else "'DM Serif Display', Georgia, serif"

    return f"""
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}

:root{{
  --navy:#0F172A;
  --navy2:#1E293B;
  --navy3:#334155;
  --slate:#64748B;
  --muted:#94A3B8;
  --border:#E2E8F0;
  --bg:#F8FAFC;
  --white:#FFFFFF;
  --text:#0F172A;
  --text2:#334155;
  --text3:#64748B;
  --accent:#3B82F6;
  --header-h:60px;
  --nav-h:52px;
  --sidebar-w:280px;
  --radius:10px;
  --radius-lg:14px;
  --shadow:0 1px 3px rgba(0,0,0,.08),0 4px 12px rgba(0,0,0,.05);
  --shadow-hover:0 4px 12px rgba(0,0,0,.12),0 12px 32px rgba(0,0,0,.08);
  --transition:0.18s cubic-bezier(.4,0,.2,1);
}}

html{{scroll-behavior:smooth}}
body{{
  font-family:{body_font};
  font-size:15px;
  line-height:1.6;
  color:var(--text);
  background:var(--bg);
  direction:{dir_prop};
}}

a{{color:inherit;text-decoration:none}}
a:hover{{text-decoration:none}}
img{{max-width:100%}}

/* ── HEADER ── */
.site-header{{
  position:sticky;
  top:0;
  z-index:200;
  background:var(--navy);
  color:#fff;
  height:var(--header-h);
  box-shadow:0 2px 8px rgba(0,0,0,.25);
}}
.header-inner{{
  max-width:1400px;
  margin:0 auto;
  padding:0 20px;
  height:100%;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:16px;
}}
.header-brand{{display:flex;align-items:center;gap:10px;min-width:0}}
.brand-icon{{font-size:22px;flex-shrink:0}}
.brand-text{{display:flex;flex-direction:column;min-width:0}}
.brand-name{{font-family:{heading_font};font-size:18px;font-weight:{'600' if rtl else '400'};letter-spacing:.01em;white-space:nowrap;color:#fff}}
.brand-meta{{font-size:11px;color:#94A3B8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.header-nav{{display:flex;align-items:center;gap:12px;flex-shrink:0}}
.nav-link{{font-size:13px;color:#94A3B8;padding:6px 10px;border-radius:6px;transition:color var(--transition),background var(--transition);white-space:nowrap}}
.nav-link:hover{{color:#fff;background:rgba(255,255,255,.08)}}
.lang-switcher{{display:flex;gap:3px;background:rgba(255,255,255,.07);border-radius:8px;padding:3px}}
.lang-btn{{display:flex;align-items:center;padding:4px 10px;border-radius:6px;font-size:12px;font-weight:500;color:#94A3B8;cursor:pointer;transition:all var(--transition);border:none;background:none;font-family:inherit}}
.lang-btn:hover{{color:#fff}}
.lang-btn.active{{background:rgba(255,255,255,.15);color:#fff}}
a.lang-btn{{cursor:pointer}}

/* ── CATEGORY NAV ── */
.cat-nav{{
  position:sticky;
  top:var(--header-h);
  z-index:190;
  background:var(--white);
  border-bottom:1px solid var(--border);
  box-shadow:0 2px 6px rgba(0,0,0,.04);
  height:var(--nav-h);
  overflow:hidden;
}}
.cat-nav-inner{{
  max-width:1400px;
  margin:0 auto;
  padding:8px 20px;
  display:flex;
  gap:6px;
  overflow-x:auto;
  scrollbar-width:none;
  align-items:center;
  height:100%;
}}
.cat-nav-inner::-webkit-scrollbar{{display:none}}
.cat-nav-btn{{
  flex-shrink:0;
  padding:5px 12px;
  border-radius:20px;
  border:1.5px solid var(--border);
  background:var(--white);
  font-size:13px;
  font-weight:500;
  color:var(--text3);
  cursor:pointer;
  transition:all var(--transition);
  display:flex;
  align-items:center;
  gap:4px;
  font-family:inherit;
  white-space:nowrap;
}}
.cat-nav-btn:hover{{border-color:var(--cat-color,var(--accent));color:var(--cat-color,var(--accent))}}
.cat-nav-btn.active{{background:var(--cat-color,var(--accent));border-color:var(--cat-color,var(--accent));color:#fff}}
.cat-nav-count{{font-size:11px;opacity:.75}}

/* ── LAYOUT ── */
.page-layout{{
  max-width:1400px;
  margin:0 auto;
  padding:28px 20px;
  display:grid;
  grid-template-columns:1fr var(--sidebar-w);
  gap:28px;
  align-items:start;
}}
.main-content{{min-width:0}}

/* ── SECTIONS ── */
.digest-section{{margin-bottom:40px}}
.section-header{{margin-bottom:20px;padding-bottom:12px;border-bottom:2px solid var(--border);display:flex;align-items:center;justify-content:space-between}}
.section-title{{font-family:{heading_font};font-size:{'20px' if rtl else '22px'};font-weight:{'600' if rtl else '400'};color:var(--navy);display:flex;align-items:center;gap:8px}}
.section-title .trophy,.section-title .pin{{font-size:20px}}

/* ── CARDS ── */
.cards-grid{{display:grid;gap:16px}}
.cards-l1{{grid-template-columns:repeat(2,1fr)}}
.cards-l2{{grid-template-columns:repeat(3,1fr)}}

.card{{
  background:var(--white);
  border-radius:var(--radius-lg);
  box-shadow:var(--shadow);
  transition:transform var(--transition),box-shadow var(--transition);
  display:flex;
  overflow:hidden;
  position:relative;
}}
.card:hover{{transform:translateY(-2px);box-shadow:var(--shadow-hover)}}

.card-accent{{
  width:4px;
  background:var(--cat-color,#374151);
  flex-shrink:0;
}}
.card-l1 .card-accent{{width:5px}}

.card-inner{{flex:1;padding:16px;min-width:0;display:flex;flex-direction:column;gap:8px}}
.card-l1 .card-inner{{padding:18px 18px 16px}}

.card-header{{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}}
.cat-badge{{
  display:inline-flex;align-items:center;gap:4px;
  padding:3px 8px;border-radius:12px;
  font-size:11px;font-weight:600;letter-spacing:.02em;text-transform:uppercase;
}}
.cat-badge.small{{font-size:10px;padding:2px 6px}}
.score-badge{{
  font-size:11px;font-weight:600;color:var(--slate);
  background:var(--bg);border-radius:10px;padding:2px 7px;
  border:1px solid var(--border);flex-shrink:0;
}}
.score-badge.small{{font-size:10px;padding:2px 6px}}

.card-title{{
  font-family:{heading_font};
  font-size:{'15px' if rtl else '17px'};
  font-weight:{'600' if rtl else '400'};
  line-height:1.35;
  color:var(--navy);
}}
.card-l2 .card-title{{font-size:{'14px' if rtl else '15px'}}}
.card-title a{{color:inherit}}
.card-title a:hover{{color:var(--cat-color,var(--accent))}}

.card-summary{{
  font-size:13.5px;
  color:var(--text2);
  line-height:1.55;
  flex:1;
}}
.card-l2 .card-summary{{font-size:13px}}

.card-footer{{
  display:flex;align-items:center;justify-content:space-between;
  gap:8px;margin-top:auto;padding-top:10px;
  border-top:1px solid var(--border);
}}
.card-meta{{font-size:12px;color:var(--muted)}}
.read-btn{{
  font-size:12px;font-weight:600;
  color:var(--cat-color,var(--accent));
  padding:4px 10px;border-radius:6px;
  border:1.5px solid var(--cat-color,var(--accent));
  transition:all var(--transition);flex-shrink:0;
  white-space:nowrap;
}}
.read-btn:hover{{background:var(--cat-color,var(--accent));color:#fff}}
.read-btn.small{{font-size:11px;padding:3px 8px}}

/* ── LEVEL 2 GROUPS ── */
.l2-category-group{{margin-bottom:28px}}
.l2-cat-header{{display:flex;align-items:center;gap:8px;margin-bottom:12px}}
.l2-cat-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
.l2-cat-name{{font-size:14px;font-weight:600}}
.l2-cat-count{{font-size:13px;color:var(--muted)}}
.show-more-btn{{
  margin-top:10px;
  padding:7px 16px;
  border-radius:8px;
  border:1.5px solid;
  background:transparent;
  font-size:13px;font-weight:500;
  cursor:pointer;font-family:inherit;
  transition:all var(--transition);
}}
.show-more-btn:hover{{opacity:.75}}

/* ── LEVEL 3 ── */
.l3-controls{{
  position:sticky;
  top:calc(var(--header-h) + var(--nav-h));
  z-index:100;
  background:var(--bg);
  padding:12px 0 10px;
  display:flex;
  flex-direction:column;
  gap:8px;
  margin-bottom:16px;
}}
.search-wrap{{position:relative}}
#l3-search{{
  width:100%;
  padding:10px 16px 10px 40px;
  border:1.5px solid var(--border);
  border-radius:10px;
  font-size:14px;font-family:inherit;
  background:var(--white);
  color:var(--text);
  transition:border-color var(--transition),box-shadow var(--transition);
  outline:none;
}}
.search-wrap::before{{
  content:"🔍";
  position:absolute;
  {'right' if rtl else 'left'}:12px;
  top:50%;transform:translateY(-50%);
  font-size:14px;pointer-events:none;
}}
#l3-search{{{'padding-right:40px;padding-left:14px' if rtl else 'padding-left:40px'}}}
#l3-search:focus{{border-color:var(--accent);box-shadow:0 0 0 3px rgba(59,130,246,.1)}}
.search-count{{
  position:absolute;
  {'left' if rtl else 'right'}:12px;
  top:50%;transform:translateY(-50%);
  font-size:11px;color:var(--muted);
  font-weight:500;
}}
.l3-filters{{display:flex;gap:8px;flex-wrap:wrap}}
.l3-filters select{{
  padding:6px 10px;
  border:1.5px solid var(--border);
  border-radius:8px;
  font-size:13px;font-family:inherit;
  background:var(--white);color:var(--text);
  cursor:pointer;outline:none;
  transition:border-color var(--transition);
}}
.l3-filters select:focus{{border-color:var(--accent)}}

/* L3 grouped */
.l3-group{{margin-bottom:20px}}
.l3-group-header{{
  display:flex;align-items:center;gap:8px;
  padding:8px 12px;
  background:var(--white);
  border:1px solid var(--border);
  border-radius:8px;
  cursor:pointer;
  margin-bottom:6px;
}}
.l3-group-header:hover{{background:var(--bg)}}
.l3-group-toggle{{font-size:11px;color:var(--muted);margin-{'right' if rtl else 'left'}:auto}}
.l3-group-count{{font-size:12px;color:var(--muted)}}
.l3-items{{display:flex;flex-direction:column;gap:2px}}
.l3-item{{
  display:grid;
  grid-template-columns:1.4rem 1fr auto auto;
  align-items:baseline;
  gap:0 10px;
  padding:6px 10px;
  border-radius:7px;
  background:var(--white);
  border:1px solid transparent;
  transition:background var(--transition),border-color var(--transition);
  cursor:pointer;
}}
.l3-item:hover{{background:#F1F5F9;border-color:var(--border)}}
.l3-item-emoji{{font-size:13px;flex-shrink:0;line-height:1.4}}
.l3-item-title{{
  font-size:13px;color:var(--text);
  line-height:1.4;
  white-space:normal;word-break:break-word;
}}
.l3-item-meta{{font-size:11.5px;color:var(--muted);flex-shrink:0;white-space:nowrap}}
.l3-item-link{{
  font-size:11px;font-weight:600;
  color:var(--accent);flex-shrink:0;
  padding:2px 8px;border-radius:5px;
  border:1px solid transparent;
  transition:all var(--transition);
  white-space:nowrap;
}}
.l3-item-link:hover{{border-color:var(--accent);background:rgba(59,130,246,.05)}}
.l3-item mark{{background:#FEF08A;color:var(--text);border-radius:2px;padding:0 1px}}
.l3-no-results{{text-align:center;padding:40px;color:var(--muted);font-size:14px}}

/* ── SIDEBAR ── */
.sidebar{{
  position:sticky;
  top:calc(var(--header-h) + var(--nav-h) + 10px);
  display:flex;
  flex-direction:column;
  gap:12px;
  max-height:calc(100vh - var(--header-h) - var(--nav-h) - 20px);
  overflow-y:auto;
  scrollbar-width:thin;
  scrollbar-color:var(--border) transparent;
}}
.sidebar-block{{
  background:var(--white);
  border-radius:var(--radius);
  border:1px solid var(--border);
  padding:14px;
}}
.sidebar-block-title{{
  font-size:12px;font-weight:700;text-transform:uppercase;
  letter-spacing:.06em;color:var(--muted);
  margin-bottom:10px;padding-bottom:8px;
  border-bottom:1px solid var(--border);
}}
.stat-row{{display:flex;align-items:baseline;gap:5px;margin-bottom:4px}}
.stat-num{{font-size:22px;font-weight:700;color:var(--navy);font-family:{heading_font}}}
.stat-label{{font-size:12px;color:var(--text3)}}
.stat-top-source{{font-size:12px;color:var(--text3);margin-top:6px;padding-top:6px;border-top:1px solid var(--border)}}

.cat-bars{{display:flex;flex-direction:column;gap:7px}}
.cat-bar-row{{display:flex;align-items:center;gap:6px;cursor:pointer;padding:2px 4px;border-radius:5px;transition:background var(--transition)}}
.cat-bar-row:hover{{background:var(--bg)}}
.cat-bar-label{{display:flex;align-items:center;gap:4px;width:95px;flex-shrink:0}}
.cat-bar-name{{font-size:12px;color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.cat-bar-track{{flex:1;height:6px;background:var(--border);border-radius:3px;overflow:hidden}}
.cat-bar-fill{{height:100%;border-radius:3px;width:0;transition:width 0.6s cubic-bezier(.4,0,.2,1)}}
.cat-bar-count{{font-size:11px;color:var(--muted);text-align:{'right' if not rtl else 'left'};width:52px;flex-shrink:0}}
.cat-bar-pct{{color:var(--border)}}

.top-sources-list{{list-style:none;display:flex;flex-direction:column;gap:5px}}
.top-sources-list li{{display:flex;align-items:center;gap:6px;font-size:12px}}
.src-rank{{width:18px;font-weight:700;color:var(--muted);flex-shrink:0;text-align:center}}
.src-name{{flex:1;color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.src-count{{font-size:11px;color:var(--muted);flex-shrink:0}}

.archive-nav{{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}}
.arch-link{{font-size:12px;color:var(--accent);padding:3px 8px;border-radius:5px;border:1px solid var(--border);transition:all var(--transition)}}
.arch-link:hover{{background:var(--bg)}}
.arch-link.disabled{{color:var(--muted);cursor:default;pointer-events:none}}
.arch-current{{font-size:13px;font-weight:600;color:var(--navy)}}
.arch-all-link{{font-size:12px;color:var(--accent)}}
.arch-all-link:hover{{text-decoration:underline}}

/* ── BACK TO TOP ── */
#back-to-top{{
  display:none;
  position:fixed;
  bottom:24px;
  {'left' if rtl else 'right'}:24px;
  z-index:300;
  width:42px;height:42px;
  background:var(--navy);color:#fff;
  border:none;border-radius:50%;
  font-size:16px;cursor:pointer;
  box-shadow:0 4px 12px rgba(0,0,0,.25);
  transition:all var(--transition);
  align-items:center;justify-content:center;
}}
#back-to-top:hover{{background:var(--navy2);transform:translateY(-2px)}}

/* ── RESPONSIVE ── */
@media(max-width:1100px){{
  .page-layout{{grid-template-columns:1fr;}}
  .sidebar{{position:static;max-height:none;display:grid;grid-template-columns:1fr 1fr;gap:12px}}
}}
@media(max-width:768px){{
  :root{{--header-h:56px;--nav-h:44px;--sidebar-w:100%}}
  .cards-l1,.cards-l2{{grid-template-columns:1fr}}
  .brand-meta{{display:none}}
  .nav-link{{display:none}}
  .sidebar{{grid-template-columns:1fr}}
  .page-layout{{padding:16px 12px}}
  .section-title{{font-size:{'17px' if rtl else '19px'}}}
  .l3-filters{{flex-direction:column}}
  .l3-item{{grid-template-columns:1.4rem 1fr auto;gap:0 8px}}
  .l3-item-meta{{display:none}}
}}
@media(max-width:480px){{
  .cards-l2{{grid-template-columns:1fr}}
  .cat-bar-label{{width:70px}}
  .l3-item-link{{padding:2px 6px;font-size:10px}}
}}

/* ── UTILITY ── */
.hidden{{display:none!important}}
.fade-in{{animation:fadeIn .3s ease forwards}}
@keyframes fadeIn{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:none}}}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# JAVASCRIPT
# ─────────────────────────────────────────────────────────────────────────────

def get_js(lang, l3_articles):
    s = UI_STRINGS[lang]
    rtl = lang == "he"

    # Prepare L3 data as minimal JS array
    l3_data = []
    for a in l3_articles:
        title = get_title(a, lang)
        cat = a.get("category", "general")
        cat_info = CATEGORIES.get(cat, CATEGORIES["general"])
        l3_data.append({
            "id": a.get("id", ""),
            "t": title,
            "u": a.get("url", "#"),
            "s": a.get("source_name", ""),
            "d": format_date(a.get("date", ""), lang),
            "c": cat,
            "e": cat_info["emoji"],
            "sc": a.get("score", 0),
            "lv": a.get("level", 3),
        })

    l3_json = json.dumps(l3_data, ensure_ascii=False, separators=(',', ':'))

    # Build source list for filter dropdown
    sources = sorted(set(a["s"] for a in l3_data if a["s"]))

    read_label = escape(s["read_article"])
    no_results = escape(s["no_results"])
    results_tpl = s["results_count"]
    show_more_tpl = escape(s["show_more"])

    return f"""
// ── Data ──
const L3_DATA = {l3_json};
const LANG = '{lang}';
const RTL = {str(rtl).lower()};
const SOURCES = {json.dumps(sources, ensure_ascii=False)};

// ── State ──
let currentCat = 'all';
let currentSource = '';
let currentSort = 'score';
let currentGroup = 'category';
let searchQuery = '';
let searchTimer = null;

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {{
  populateSourceFilter();
  renderL3();
  animateBars();
  setupBackToTop();
  document.getElementById('l3-search').addEventListener('input', e => {{
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {{
      searchQuery = e.target.value.trim().toLowerCase();
      renderL3();
    }}, 200);
  }});
  document.getElementById('l3-source-filter').addEventListener('change', e => {{
    currentSource = e.target.value;
    renderL3();
  }});
  document.getElementById('l3-sort').addEventListener('change', e => {{
    currentSort = e.target.value;
    renderL3();
  }});
  document.getElementById('l3-group').addEventListener('change', e => {{
    currentGroup = e.target.value;
    renderL3();
  }});
}});

// ── Category filter ──
function filterCategory(catId) {{
  currentCat = catId;
  // Update nav buttons
  document.querySelectorAll('.cat-nav-btn').forEach(btn => {{
    btn.classList.toggle('active', btn.dataset.cat === catId);
  }});
  // Filter L1 cards
  document.querySelectorAll('.card-l1').forEach(card => {{
    card.style.display = (catId === 'all' || card.dataset.category === catId) ? '' : 'none';
  }});
  // Filter L2 groups
  document.querySelectorAll('.l2-category-group').forEach(grp => {{
    grp.style.display = (catId === 'all' || grp.dataset.category === catId) ? '' : 'none';
  }});
  // Rerender L3 with new filter
  renderL3();
  // Scroll to section if specific category
  if (catId !== 'all') {{
    const sec = document.getElementById('level1');
    if (sec) {{ sec.scrollIntoView({{behavior:'smooth', block:'start'}}); }}
  }}
}}

// ── Show more L2 ──
function showMoreL2(catId) {{
  const hidden = document.getElementById('l2-hidden-' + catId);
  if (hidden) {{
    hidden.style.display = '';
    const btn = hidden.nextElementSibling;
    if (btn && btn.classList.contains('show-more-btn')) btn.style.display = 'none';
    Array.from(hidden.children).forEach((el, i) => {{
      el.style.animationDelay = (i * 0.04) + 's';
      el.classList.add('fade-in');
    }});
  }}
}}

// ── Populate source filter ──
function populateSourceFilter() {{
  const sel = document.getElementById('l3-source-filter');
  SOURCES.forEach(src => {{
    const opt = document.createElement('option');
    opt.value = src;
    opt.textContent = src;
    sel.appendChild(opt);
  }});
}}

// ── Highlight text ──
function highlight(text, query) {{
  if (!query) return esc(text);
  const safe = esc(text);
  const re = new RegExp('(' + query.replace(/[.*+?^${{}}()|[\\]\\\\]/g,'\\\\$&') + ')', 'gi');
  return safe.replace(re, '<mark>$1</mark>');
}}

function esc(str) {{
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

// ── Render L3 ──
function renderL3() {{
  let items = L3_DATA.slice();
  // Category filter
  if (currentCat !== 'all') items = items.filter(a => a.c === currentCat);
  // Source filter
  if (currentSource) items = items.filter(a => a.s === currentSource);
  // Search
  if (searchQuery) items = items.filter(a => a.t.toLowerCase().includes(searchQuery));
  // Sort
  if (currentSort === 'score') items.sort((a,b) => b.sc - a.sc);
  else if (currentSort === 'date') items.sort((a,b) => b.d.localeCompare(a.d));
  else if (currentSort === 'source') items.sort((a,b) => a.s.localeCompare(b.s));
  // Count
  const countEl = document.getElementById('search-count');
  if (searchQuery || currentCat !== 'all' || currentSource) {{
    const tpl = '{results_tpl}';
    countEl.textContent = tpl.replace('{{n}}', items.length);
  }} else {{
    countEl.textContent = '';
  }}
  const container = document.getElementById('l3-list');
  if (items.length === 0) {{
    container.innerHTML = '<div class="l3-no-results">{no_results}</div>';
    return;
  }}
  if (currentGroup === 'flat') {{
    container.innerHTML = '<div class="l3-items">' + items.map(a => renderL3Item(a)).join('') + '</div>';
  }} else {{
    // Group by category
    const groups = {{}};
    const catOrder = ['ai_it','astronomy','biology','medicine','physics','general','chemistry','climate'];
    items.forEach(a => {{ (groups[a.c] = groups[a.c] || []).push(a); }});
    let html = '';
    catOrder.forEach(cat => {{
      if (!groups[cat]) return;
      const arts = groups[cat];
      const catColors = {json.dumps({k: v['color'] for k,v in CATEGORIES.items()}, ensure_ascii=False)};
      const catEmojis = {json.dumps({k: v['emoji'] for k,v in CATEGORIES.items()}, ensure_ascii=False)};
      const catNames = {json.dumps({k: v[lang] for k,v in CATEGORIES.items()}, ensure_ascii=False)};
      const color = catColors[cat] || '#374151';
      const emoji = catEmojis[cat] || '🔬';
      const name = catNames[cat] || cat;
      html += `<div class="l3-group">
        <div class="l3-group-header" onclick="toggleL3Group('lg-${{cat}}')">
          <span style="color:${{color}};font-size:14px">${{emoji}} <strong>${{name}}</strong></span>
          <span class="l3-group-count">${{arts.length}}</span>
          <span class="l3-group-toggle" id="lg-${{cat}}-arrow">▾</span>
        </div>
        <div class="l3-items" id="lg-${{cat}}">${{arts.map(a => renderL3Item(a)).join('')}}</div>
      </div>`;
    }});
    container.innerHTML = html;
  }}
}}

function toggleL3Group(id) {{
  const el = document.getElementById(id);
  if (!el) return;
  const arrow = document.getElementById(id + '-arrow');
  if (el.style.display === 'none') {{
    el.style.display = '';
    if (arrow) arrow.textContent = '▾';
  }} else {{
    el.style.display = 'none';
    if (arrow) arrow.textContent = '▸';
  }}
}}

function renderL3Item(a) {{
  const t = highlight(a.t, searchQuery);
  const cat = a.c;
  const catColors = {json.dumps({k: v['color'] for k,v in CATEGORIES.items()}, ensure_ascii=False)};
  const color = catColors[cat] || '#374151';
  const border = a.lv === 1 ? `border-left:3px solid ${{color}};padding-left:8px` : (a.lv === 2 ? `border-left:2px solid rgba(${{hexToRgb(color)}},0.4);padding-left:8px` : '');
  const safeUrl = /^https?:\/\//i.test(a.u) ? a.u : '#';
  return `<div class="l3-item" style="${{border}}" onclick="window.open('${{esc(safeUrl)}}','_blank')">
    <span class="l3-item-emoji">${{a.e}}</span>
    <span class="l3-item-title">${{t}}</span>
    <span class="l3-item-meta">${{esc(a.s)}} · ${{esc(a.d)}}</span>
    <a href="${{esc(a.u)}}" target="_blank" rel="noopener noreferrer" class="l3-item-link" onclick="event.stopPropagation()">{read_label}</a>
  </div>`;
}}

function hexToRgb(hex) {{
  const r = parseInt(hex.slice(1,3),16);
  const g = parseInt(hex.slice(3,5),16);
  const b = parseInt(hex.slice(5,7),16);
  return r+','+g+','+b;
}}

// ── Animate sidebar bars ──
function animateBars() {{
  const bars = document.querySelectorAll('.cat-bar-fill');
  setTimeout(() => {{
    bars.forEach(bar => {{ bar.style.width = bar.dataset.width + '%'; }});
  }}, 300);
}}

// ── Back to top ──
function setupBackToTop() {{
  const btn = document.getElementById('back-to-top');
  if (!btn) return;
  window.addEventListener('scroll', () => {{
    btn.style.display = window.scrollY > 500 ? 'flex' : 'none';
  }}, {{passive:true}});
  btn.addEventListener('click', () => window.scrollTo({{top:0,behavior:'smooth'}}));
}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RENDERER
# ─────────────────────────────────────────────────────────────────────────────

def render_html(articles, lang, week_num, mode="weekly"):
    s = UI_STRINGS[lang]
    l1, l2, l3, cat_counts, source_counts = process_data(articles, lang)
    num_sources = len(source_counts)

    meta = {
        "total": len(articles),
        "num_sources": num_sources,
        "week_num": week_num,
    }

    lang_code = {"ru": "ru", "en": "en", "he": "he"}.get(lang, "en")
    dir_attr = 'dir="rtl"' if lang == "he" else 'dir="ltr"'
    week_label = get_week_label(week_num, lang)
    week_dates = get_week_dates(week_num, lang)

    # Path to local fonts.css relative to the HTML file being generated
    fonts_depth = "../" if lang in ("en", "he") else ""
    fonts_css_path = f"{fonts_depth}assets/fonts/fonts.css"
    local_fonts_link = f'<link rel="stylesheet" href="{fonts_css_path}">'
    # CSP: fully self-hosted, no external font origin needed
    csp = (
        "default-src \'self\'; "
        "style-src \'self\' \'unsafe-inline\'; "
        "font-src \'self\'; "
        "script-src \'self\' \'unsafe-inline\'; "
        "connect-src \'none\'; "
        "img-src \'self\' data:; "
        "frame-src \'none\'; "
        "object-src \'none\'; "
        "base-uri \'self\'"
    )

    header_html = render_header(meta, lang, week_num)
    cat_nav_html = render_category_nav(cat_counts, lang)
    l1_html = render_level1_section(l1, lang)
    l2_html = render_level2_section(l2, lang)
    l3_html = render_level3_section(lang)
    sidebar_html = render_sidebar(meta, cat_counts, source_counts, lang, week_num)
    css = get_css(lang)
    js = get_js(lang, l3)

    back_to_top_label = s["back_to_top"]

    html = f"""<!DOCTYPE html>
<html lang="{lang_code}" {dir_attr}>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(week_label)} — Science Digest</title>
  <meta name="description" content="Science Digest {escape(week_label)}: {escape(week_dates)} · {meta['total']} articles">
  <meta http-equiv="Content-Security-Policy" content="{csp}">
  <meta http-equiv="X-Content-Type-Options" content="nosniff">
  <meta http-equiv="X-Frame-Options" content="DENY">
  <meta name="referrer" content="strict-origin">
  {local_fonts_link}
  <style>
{css}
  </style>
</head>
<body>
{header_html}
{cat_nav_html}
<div class="page-layout">
  <main class="main-content">
    {l1_html}
    {l2_html}
    {l3_html}
  </main>
  {sidebar_html}
</div>
<button id="back-to-top" aria-label="Back to top">{back_to_top_label}</button>
<script>
{js}
</script>
</body>
</html>"""

    return html


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Science Digest HTML renderer")
    parser.add_argument("--mode", choices=["weekly", "daily"], default="weekly")
    parser.add_argument("--week", type=int, default=11)
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--lang", choices=["ru", "en", "he"], default="ru")
    parser.add_argument("--data", type=str, default=None)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    # Resolve data path
    if args.data:
        data_path = args.data
    else:
        # Auto-detect: look in data/ or project root
        candidates = [
            f"data/W{args.week}_translated.json",
            f"W{args.week}_translated.json",
            f"data/W{args.week:02d}_translated.json",
        ]
        data_path = None
        for c in candidates:
            if os.path.exists(c):
                data_path = c
                break
        if not data_path:
            print(f"Error: could not find W{args.week}_translated.json. Use --data to specify path.", file=sys.stderr)
            sys.exit(1)

    # Load data
    with open(data_path, encoding="utf-8") as f:
        articles = json.load(f)
    print(f"Loaded {len(articles)} articles from {data_path}", file=sys.stderr)

    # Render
    html = render_html(articles, args.lang, args.week, args.mode)

    # Resolve output path
    if args.out:
        out_path = args.out
    else:
        if args.mode == "weekly":
            if args.lang == "ru":
                out_path = "docs/index.html"
            elif args.lang == "en":
                out_path = "docs/en/index.html"
            else:
                out_path = "docs/he/index.html"
        else:
            out_path = f"docs/daily.html"

    os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = len(html.encode("utf-8")) / 1024
    print(f"Rendered: {out_path} ({size_kb:.0f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
