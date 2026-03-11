#!/usr/bin/env python3
"""
render.py — Generate HTML digest for one language from translated JSON.

Usage:
    python pipeline/render.py --mode daily --date 2026-03-17 --lang ru
    python pipeline/render.py --mode weekly --week 13 --lang he
    python pipeline/render.py --mode weekly --week 13 --lang en
"""

import argparse
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    load_categories, week_number,
    daily_path, weekly_path, suffix_path,
    setup_logging, load_json, DOCS_DIR, DATA_DIR
)

log = setup_logging("render")

# ── String tables ─────────────────────────────────────────────────────────────

UI = {
    "ru": {
        "site_title": "Научный Дайджест",
        "daily": "Ежедневный дайджест",
        "weekly": "Еженедельный дайджест",
        "level1_title": "Главные открытия",
        "level2_title": "Важные новости",
        "level3_title": "Полный каталог",
        "level1_desc": "Самые значимые научные открытия периода",
        "level2_desc": "Заметные исследования и события",
        "level3_desc": "Все статьи за период",
        "source_link": "→ Источник",
        "all_categories": "Все категории",
        "articles": "статей",
        "sources": "источников",
        "categories_label": "категорий",
        "score_label": "Балл",
        "search_placeholder": "Поиск по заголовку…",
        "no_results": "Ничего не найдено",
        "lang_ru": "RU", "lang_en": "EN", "lang_he": "עב",
        "dir": "ltr",
        "font_family": "'Inter', 'Segoe UI', Arial, sans-serif",
        "day_filter_label": "Скрыть дни, которые вы уже читали:",
        "day_filter_hint": "Нажмите на день — все его статьи скроются. Нажмите снова — вернутся.",
        "day_names": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
    },
    "en": {
        "site_title": "Science Digest",
        "daily": "Daily Digest",
        "weekly": "Weekly Digest",
        "level1_title": "Top Discoveries",
        "level2_title": "Notable News",
        "level3_title": "Full Catalog",
        "level1_desc": "The most significant scientific findings of the period",
        "level2_desc": "Noteworthy research and developments",
        "level3_desc": "All articles for the period",
        "source_link": "→ Source",
        "all_categories": "All Categories",
        "articles": "articles",
        "sources": "sources",
        "categories_label": "categories",
        "score_label": "Score",
        "search_placeholder": "Search by title…",
        "no_results": "No results found",
        "lang_ru": "RU", "lang_en": "EN", "lang_he": "עב",
        "dir": "ltr",
        "font_family": "'Inter', 'Segoe UI', Arial, sans-serif",
        "day_filter_label": "Hide days you've already read:",
        "day_filter_hint": "Click a day to hide its articles. Click again to show them.",
        "day_names": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    },
    "he": {
        "site_title": "תקציר מדעי",
        "daily": "תקציר יומי",
        "weekly": "תקציר שבועי",
        "level1_title": "תגליות מרכזיות",
        "level2_title": "חדשות חשובות",
        "level3_title": "קטלוג מלא",
        "level1_desc": "הממצאים המדעיים החשובים ביותר של התקופה",
        "level2_desc": "מחקרים ואירועים ראויים לציון",
        "level3_desc": "כל המאמרים של התקופה",
        "source_link": "מקור ←",
        "all_categories": "כל הקטגוריות",
        "articles": "מאמרים",
        "sources": "מקורות",
        "categories_label": "קטגוריות",
        "score_label": "ציון",
        "search_placeholder": "חיפוש לפי כותרת…",
        "no_results": "לא נמצאו תוצאות",
        "lang_ru": "RU", "lang_en": "EN", "lang_he": "עב",
        "dir": "rtl",
        "font_family": "'Heebo', 'David', 'Arial Hebrew', Arial, sans-serif",
        "day_filter_label": "הסתר ימים שכבר קראת:",
        "day_filter_hint": "לחץ על יום להסתרת המאמרים שלו. לחץ שוב להצגתם.",
        "day_names": ["ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "ש׳", "א׳"],
    },
}


def get_text(article: dict, field: str, lang: str) -> str:
    trans = article.get("translations", {})
    if lang != "en" and lang in trans and field in trans[lang]:
        val = trans[lang][field]
        if val and not val.startswith(f"[{lang.upper()}]"):
            return val
    return article.get(field, "")


def get_category_label(cat: str, lang: str, categories: dict) -> str:
    return categories.get(cat, {}).get(lang, cat.title())


# ── Mark daily appearances ────────────────────────────────────────────────────

def mark_daily_appearances(articles: list[dict], week: int, year: int) -> list[dict]:
    """
    Tag each weekly article with the date of the daily digest it appeared in.
    Adds field 'daily_date': 'YYYY-MM-DD' or None.
    Only checks Mon–Fri of the given ISO week.
    """
    monday = datetime.fromisocalendar(year, week, 1).replace(tzinfo=timezone.utc)
    daily_url_to_date: dict[str, str] = {}

    for day_offset in range(5):
        day = monday + timedelta(days=day_offset)
        date_str = day.strftime("%Y-%m-%d")

        path = None
        for suffix in ("_translated.json", "_scored.json", "_raw.json"):
            candidate = DATA_DIR / "daily" / f"{date_str}{suffix}"
            if candidate.exists():
                path = candidate
                break
        if not path:
            continue

        daily_articles = load_json(path) or []
        for da in daily_articles:
            url = da.get("url", "")
            if url and url not in daily_url_to_date:
                daily_url_to_date[url] = date_str
        log.info(f"  Daily {date_str}: {len(daily_articles)} articles")

    tagged = 0
    for a in articles:
        dd = daily_url_to_date.get(a.get("url", ""))
        a["daily_date"] = dd
        if dd:
            tagged += 1

    log.info(f"Overlap with daily digests: {tagged}/{len(articles)}")
    return articles


# ── CSS ───────────────────────────────────────────────────────────────────────

def build_css(lang: str, ui: dict) -> str:
    is_rtl = lang == "he"
    card_border = ("border-right: 4px solid var(--cat-color); border-left: none;"
                   if is_rtl else "border-left: 4px solid var(--cat-color);")
    layout_dir = "row-reverse" if is_rtl else "row"
    text_align = "right" if is_rtl else "left"

    return f"""
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{font-size:16px;scroll-behavior:smooth}}
body{{font-family:{ui["font_family"]};direction:{ui["dir"]};background:#F3F4F6;color:#1F2937;line-height:1.6}}
.layout{{display:flex;flex-direction:{layout_dir};max-width:1280px;margin:0 auto;padding:0 1rem;gap:1.5rem;align-items:flex-start}}
.main-content{{flex:1;min-width:0;padding:1.5rem 0}}
.sidebar{{width:280px;flex-shrink:0;position:sticky;top:80px;padding:1.5rem 0}}
.site-header{{background:#111827;color:white;padding:0.75rem 0;position:sticky;top:0;z-index:100;box-shadow:0 2px 4px rgba(0,0,0,.3)}}
.header-inner{{max-width:1280px;margin:0 auto;padding:0 1rem;display:flex;align-items:center;justify-content:space-between;flex-direction:{"row-reverse" if is_rtl else "row"}}}
.site-title{{font-size:1.2rem;font-weight:700;letter-spacing:-.02em}}
.site-subtitle{{font-size:.8rem;color:#9CA3AF;margin-top:2px}}
.lang-switcher{{display:flex;gap:.5rem}}
.lang-switcher a{{color:#9CA3AF;text-decoration:none;padding:.25rem .6rem;border-radius:4px;font-size:.85rem;font-weight:600;transition:all .15s}}
.lang-switcher a:hover{{color:white;background:rgba(255,255,255,.1)}}
.lang-switcher a.active{{color:white;background:#374151}}
.cat-nav{{background:white;border-bottom:1px solid #E5E7EB;position:sticky;top:52px;z-index:99}}
.cat-nav-inner{{max-width:1280px;margin:0 auto;padding:0 1rem;display:flex;flex-direction:{"row-reverse" if is_rtl else "row"};gap:.25rem;overflow-x:auto;scrollbar-width:none}}
.cat-nav-inner::-webkit-scrollbar{{display:none}}
.cat-btn{{padding:.6rem .9rem;border:none;background:none;cursor:pointer;font-size:.82rem;font-weight:500;color:#6B7280;white-space:nowrap;border-bottom:2px solid transparent;transition:all .15s;font-family:inherit}}
.cat-btn:hover{{color:#111827}}
.cat-btn.active{{color:#111827;border-bottom-color:#111827;font-weight:600}}

/* ── Day filter panel ── */
.day-filter-panel{{background:white;border-radius:12px;padding:1rem 1.25rem;margin-bottom:1.25rem;border:1px solid #E5E7EB}}
.day-filter-label{{font-size:.82rem;font-weight:600;color:#374151;margin-bottom:.6rem;display:flex;align-items:center;gap:.4rem}}
.day-filter-buttons{{display:flex;flex-direction:{"row-reverse" if is_rtl else "row"};gap:.5rem;flex-wrap:wrap;margin-bottom:.4rem}}
.day-btn{{display:flex;flex-direction:column;align-items:center;gap:.1rem;padding:.45rem .8rem;border:1.5px solid #E5E7EB;border-radius:8px;background:white;cursor:pointer;font-family:inherit;transition:all .15s;min-width:60px}}
.day-btn:hover{{border-color:#9CA3AF;background:#F9FAFB}}
.day-btn.hidden-day{{background:#1F2937;border-color:#1F2937;color:white}}
.day-btn.hidden-day .day-name{{color:white}}
.day-btn.hidden-day .day-date,.day-btn.hidden-day .day-count{{color:#6B7280}}
.day-name{{font-size:.82rem;font-weight:700;color:#1F2937}}
.day-date{{font-size:.7rem;color:#6B7280;direction:ltr}}
.day-count{{font-size:.68rem;color:#9CA3AF}}
.day-filter-hint{{font-size:.71rem;color:#9CA3AF}}

/* ── Sections ── */
.level-section{{margin-bottom:2.5rem}}
.level-header{{background:white;border-radius:12px 12px 0 0;padding:1.25rem 1.5rem 1rem;border-bottom:1px solid #E5E7EB}}
.level-title{{font-size:1.3rem;font-weight:700;color:#111827}}
.level-desc{{font-size:.85rem;color:#6B7280;margin-top:.2rem}}
.level-badge{{display:inline-flex;align-items:center;gap:.3rem;padding:.2rem .7rem;border-radius:99px;font-size:.75rem;font-weight:600;margin-{"right" if not is_rtl else "left"}:.75rem}}
.badge-l1{{background:#FEF3C7;color:#92400E}}
.badge-l2{{background:#DBEAFE;color:#1E40AF}}
.badge-l3{{background:#F3F4F6;color:#374151}}
.cards-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:1rem;padding:1rem;background:white;border-radius:0 0 12px 12px}}
.card{{background:var(--cat-bg,#F9FAFB);border-radius:10px;padding:1.1rem 1.25rem;{card_border};transition:box-shadow .15s,opacity .2s}}
.card:hover{{box-shadow:0 4px 12px rgba(0,0,0,.08)}}
.card-header{{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:.6rem;gap:.5rem}}
.card-title{{font-size:.95rem;font-weight:600;color:#111827;line-height:1.4}}
.card-title a{{color:inherit;text-decoration:none}}
.card-title a:hover{{text-decoration:underline}}
.card-summary{{font-size:.85rem;color:#4B5563;line-height:1.55;margin:.5rem 0}}
.card-footer{{display:flex;align-items:center;flex-direction:{"row-reverse" if is_rtl else "row"};justify-content:space-between;margin-top:.75rem;font-size:.78rem;color:#9CA3AF;flex-wrap:wrap;gap:.4rem}}
.card-source-link{{color:var(--cat-color);text-decoration:none;font-weight:500}}
.card-source-link:hover{{text-decoration:underline}}
.card-meta{{display:flex;gap:.6rem;align-items:center;direction:ltr;flex-wrap:wrap}}
.daily-badge{{display:inline-flex;align-items:center;padding:.1rem .4rem;border-radius:99px;font-size:.67rem;font-weight:600;background:#F3F4F6;color:#6B7280;border:1px dashed #D1D5DB;white-space:nowrap;direction:ltr}}
.cat-badge{{display:inline-flex;align-items:center;gap:.25rem;padding:.15rem .55rem;border-radius:99px;font-size:.7rem;font-weight:600;background:var(--cat-bg);color:var(--cat-color);border:1px solid var(--cat-color);white-space:nowrap}}
.score-badge{{display:inline-block;padding:.15rem .5rem;border-radius:4px;font-size:.7rem;font-weight:700;background:#F3F4F6;color:#374151;direction:ltr}}
.l3-table{{width:100%;border-collapse:collapse;background:white;border-radius:0 0 12px 12px;overflow:hidden}}
.l3-table th{{background:#F9FAFB;padding:.6rem 1rem;text-align:{text_align};font-size:.75rem;font-weight:600;color:#6B7280;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #E5E7EB}}
.l3-table td{{padding:.65rem 1rem;border-bottom:1px solid #F3F4F6;font-size:.85rem;vertical-align:middle}}
.l3-table tr:hover td{{background:#F9FAFB}}
.l3-title{{font-weight:500}}
.l3-title a{{color:#1F2937;text-decoration:none}}
.l3-title a:hover{{text-decoration:underline}}
.l3-meta{{white-space:nowrap;color:#9CA3AF;font-size:.78rem;direction:ltr}}
.search-wrap{{padding:1rem 1rem 0;background:white}}
.search-input{{width:100%;padding:.6rem 1rem;border:1px solid #E5E7EB;border-radius:8px;font-size:.9rem;font-family:inherit;direction:{ui["dir"]};outline:none;transition:border-color .15s}}
.search-input:focus{{border-color:#6B7280}}
.sidebar-card{{background:white;border-radius:12px;padding:1.1rem;margin-bottom:1rem}}
.sidebar-title{{font-size:.85rem;font-weight:700;color:#111827;margin-bottom:.75rem}}
.sidebar-stat{{display:flex;flex-direction:{"row-reverse" if is_rtl else "row"};justify-content:space-between;padding:.3rem 0;font-size:.83rem;border-bottom:1px solid #F3F4F6}}
.sidebar-stat:last-child{{border-bottom:none}}
.stat-num{{font-weight:700;color:#111827;direction:ltr}}
.stats-bar{{background:white;border-radius:12px;padding:1rem 1.5rem;margin-bottom:1.25rem;display:flex;flex-direction:{"row-reverse" if is_rtl else "row"};gap:2rem;flex-wrap:wrap}}
.stat-item{{text-align:center}}
.stat-value{{font-size:1.5rem;font-weight:800;color:#111827;direction:ltr}}
.stat-label{{font-size:.75rem;color:#9CA3AF;text-transform:uppercase;letter-spacing:.04em}}
.filter-bar{{padding:.75rem 1rem;background:#F9FAFB;display:flex;flex-direction:{"row-reverse" if is_rtl else "row"};flex-wrap:wrap;gap:.4rem;border-bottom:1px solid #E5E7EB}}
.filter-btn{{padding:.25rem .7rem;border:1px solid #E5E7EB;background:white;border-radius:99px;font-size:.78rem;cursor:pointer;font-family:inherit;transition:all .15s;color:#374151}}
.filter-btn:hover,.filter-btn.active{{background:#111827;color:white;border-color:#111827}}
@media(max-width:900px){{.sidebar{{display:none}}.cards-grid{{grid-template-columns:1fr}}}}
@media(max-width:600px){{.stats-bar{{gap:1rem}}.day-filter-buttons{{gap:.3rem}}.day-btn{{min-width:50px;padding:.35rem .5rem}}}}
"""


# ── JavaScript ────────────────────────────────────────────────────────────────

def build_js(lang: str, ui: dict) -> str:
    storage_key = f"hidden_days_{lang}"
    return f"""
let activeCategory = 'all';

function filterCategory(cat) {{
  activeCategory = cat;
  document.querySelectorAll('.cat-btn').forEach(b => b.classList.toggle('active', b.dataset.cat === cat));
  document.querySelectorAll('[data-cat]').forEach(el => {{
    if (el.classList.contains('cat-btn')) return;
    el.style.display = (cat === 'all' || el.dataset.cat === cat) ? '' : 'none';
  }});
  applyDayFilter();
  filterL3();
}}

function filterL2(cat) {{
  document.querySelectorAll('.l2-filter-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.cat === cat || (cat==='all' && b.dataset.cat==='all')));
  document.querySelectorAll('.card[data-section="l2"]').forEach(card => {{
    const catOk = cat === 'all' || card.dataset.cat === cat;
    const dayOk = !hiddenDays.has(card.dataset.daily || '');
    card.style.display = (catOk && dayOk) ? '' : 'none';
  }});
}}

function filterL3() {{
  const q = (document.getElementById('l3-search')?.value || '').toLowerCase();
  document.querySelectorAll('.l3-row').forEach(row => {{
    const catOk = activeCategory === 'all' || row.dataset.cat === activeCategory;
    const txtOk = !q || row.dataset.title.toLowerCase().includes(q);
    const dayOk = !hiddenDays.has(row.dataset.daily || '');
    row.style.display = (catOk && txtOk && dayOk) ? '' : 'none';
  }});
}}

// ── Day filter ────────────────────────────────────────────────────────────
const STORAGE_KEY = '{storage_key}';
let hiddenDays = new Set(JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'));

function toggleDay(date) {{
  hiddenDays.has(date) ? hiddenDays.delete(date) : hiddenDays.add(date);
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...hiddenDays]));
  document.querySelectorAll(`.day-btn[data-date="${{date}}"]`).forEach(btn =>
    btn.classList.toggle('hidden-day', hiddenDays.has(date)));
  applyDayFilter();
  filterL3();
}}

function applyDayFilter() {{
  document.querySelectorAll('.card').forEach(card => {{
    const catOk = activeCategory === 'all' || card.dataset.cat === activeCategory;
    const dayHidden = card.dataset.daily && hiddenDays.has(card.dataset.daily);
    card.style.display = (catOk && !dayHidden) ? '' : 'none';
  }});
}}

document.addEventListener('DOMContentLoaded', () => {{
  hiddenDays.forEach(date =>
    document.querySelectorAll(`.day-btn[data-date="${{date}}"]`).forEach(b => b.classList.add('hidden-day')));
  if (hiddenDays.size > 0) {{ applyDayFilter(); filterL3(); }}
}});
"""


# ── Card / row HTML ───────────────────────────────────────────────────────────

def cat_vars(cat: str, categories: dict) -> str:
    info = categories.get(cat, {})
    return f'style="--cat-color:{info.get("color","#374151")};--cat-bg:{info.get("bg","#F9FAFB")};"'


def daily_badge_html(daily_date: str, ui: dict) -> str:
    if not daily_date:
        return ""
    try:
        dt = datetime.strptime(daily_date, "%Y-%m-%d")
        day_name = ui["day_names"][dt.weekday()]
        return f'<span class="daily-badge">📅 {day_name} {dt.strftime("%d.%m")}</span>'
    except ValueError:
        return ""


def card_html(article: dict, lang: str, ui: dict, categories: dict, section: str = "l1") -> str:
    title = get_text(article, "title", lang)
    summary = get_text(article, "summary", lang) if article.get("level") in (1, 2) else ""
    url = article.get("url", "#")
    cat = article.get("category", "general")
    emoji = categories.get(cat, {}).get("emoji", "🔬")
    cat_label = get_category_label(cat, lang, categories)
    score = article.get("score", 0)
    date = article.get("date", "")
    source_name = article.get("source_name", "")
    daily_date = article.get("daily_date") or ""
    daily_attr = f' data-daily="{daily_date}"' if daily_date else ""
    badge = daily_badge_html(daily_date, ui) if daily_date else ""
    sum_html = f'<p class="card-summary">{summary}</p>' if summary else ""

    return (f'<div class="card" data-cat="{cat}" data-section="{section}"{daily_attr} {cat_vars(cat, categories)}>'
            f'<div class="card-header">'
            f'<h3 class="card-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>'
            f'<span class="cat-badge">{emoji} {cat_label}</span>'
            f'</div>'
            f'{sum_html}'
            f'<div class="card-footer">'
            f'<a class="card-source-link" href="{url}" target="_blank" rel="noopener">{ui["source_link"]}</a>'
            f'<span class="card-meta">{badge}'
            f'<span class="score-badge">{score}</span>'
            f'<span>{source_name}</span>'
            f'<span>{date}</span>'
            f'</span></div></div>')


def l3_row_html(article: dict, lang: str, ui: dict, categories: dict) -> str:
    title = get_text(article, "title", lang)
    url = article.get("url", "#")
    cat = article.get("category", "general")
    info = categories.get(cat, {})
    emoji = info.get("emoji", "🔬")
    cat_label = get_category_label(cat, lang, categories)
    color = info.get("color", "#374151")
    bg = info.get("bg", "#F9FAFB")
    source = article.get("source_name", "")
    date = article.get("date", "")
    daily_date = article.get("daily_date") or ""
    daily_attr = f' data-daily="{daily_date}"' if daily_date else ""
    badge = daily_badge_html(daily_date, ui) if daily_date else ""

    return (f'<tr class="l3-row" data-cat="{cat}" data-title="{title.replace(chr(34), "&quot;")}"{daily_attr}>'
            f'<td class="l3-title"><a href="{url}" target="_blank" rel="noopener">{title}</a>{badge}</td>'
            f'<td><span style="background:{bg};color:{color};padding:.15rem .5rem;border-radius:99px;'
            f'font-size:.72rem;font-weight:600;white-space:nowrap;">{emoji} {cat_label}</span></td>'
            f'<td class="l3-meta">{source}</td>'
            f'<td class="l3-meta">{date}</td>'
            f'</tr>')


# ── Day filter panel ──────────────────────────────────────────────────────────

def build_day_filter_panel(articles: list[dict], lang: str, ui: dict) -> str:
    counts = Counter(a.get("daily_date") for a in articles if a.get("daily_date"))
    if not counts:
        return ""

    is_rtl = lang == "he"
    buttons = []
    for date_str in sorted(counts.keys()):
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            day_name = ui["day_names"][dt.weekday()]
            short_date = dt.strftime("%d.%m")
            n = counts[date_str]
        except ValueError:
            continue
        buttons.append(
            f'<button class="day-btn" data-date="{date_str}" onclick="toggleDay(\'{date_str}\')">'
            f'<span class="day-name">{day_name}</span>'
            f'<span class="day-date">{short_date}</span>'
            f'<span class="day-count">{n}</span>'
            f'</button>'
        )

    return (f'<div class="day-filter-panel">'
            f'<div class="day-filter-label">📅 {ui["day_filter_label"]}</div>'
            f'<div class="day-filter-buttons">{"".join(buttons)}</div>'
            f'<div class="day-filter-hint">{ui["day_filter_hint"]}</div>'
            f'</div>')


# ── Main render ───────────────────────────────────────────────────────────────

def render(articles: list[dict], lang: str, mode: str, label: str,
           categories: dict, cat_order: list) -> str:
    ui = UI[lang]
    is_rtl = lang == "he"

    l1 = [a for a in articles if a.get("level") == 1]
    l2 = [a for a in articles if a.get("level") == 2]
    l3 = [a for a in articles if a.get("level") == 3]

    n_articles = len(articles)
    n_sources = len(set(a.get("source_id") for a in articles))
    n_cats = len(set(a.get("category") for a in articles))

    # Lang switcher
    base = "/science-digest"
    lang_links = {"ru": f"{base}/", "en": f"{base}/en/", "he": f"{base}/he/"}
    if mode == "daily":
        lang_links = {k: v + "daily.html" for k, v in lang_links.items()}
    lang_sw = "".join(
        f'<a href="{lang_links[l]}" class="{"active" if l == lang else ""}">{ui[f"lang_{l}"]}</a>'
        for l in ("ru", "en", "he")
    )

    mode_label = ui["daily"] if mode == "daily" else ui["weekly"]
    subtitle = f"{mode_label} · {label}"

    # Category nav
    cats_present = set(a.get("category") for a in articles)
    nav_btns = f'<button class="cat-btn active" data-cat="all" onclick="filterCategory(\'all\')">{ui["all_categories"]}</button>'
    for cat in cat_order:
        if cat not in cats_present:
            continue
        info = categories.get(cat, {})
        lbl = get_category_label(cat, lang, categories)
        nav_btns += (f'<button class="cat-btn" data-cat="{cat}" onclick="filterCategory(\'{cat}\')">'
                     f'{info.get("emoji","")} {lbl}</button>')

    # Stats bar
    stats_bar = (f'<div class="stats-bar">'
                 f'<div class="stat-item"><div class="stat-value">{n_articles}</div><div class="stat-label">{ui["articles"]}</div></div>'
                 f'<div class="stat-item"><div class="stat-value">{n_sources}</div><div class="stat-label">{ui["sources"]}</div></div>'
                 f'<div class="stat-item"><div class="stat-value">{n_cats}</div><div class="stat-label">{ui["categories_label"]}</div></div>'
                 f'<div class="stat-item"><div class="stat-value">{len(l1)}</div><div class="stat-label">Level 1</div></div>'
                 f'<div class="stat-item"><div class="stat-value">{len(l2)}</div><div class="stat-label">Level 2</div></div>'
                 f'</div>')

    # Day filter panel (weekly only)
    day_filter = build_day_filter_panel(articles, lang, ui) if mode == "weekly" else ""

    # Level 1
    l1_cards = "\n".join(card_html(a, lang, ui, categories, "l1") for a in l1)
    sec1 = (f'<section class="level-section" id="level1">'
            f'<div class="level-header"><span class="level-badge badge-l1">Level 1</span>'
            f'<span class="level-title">{ui["level1_title"]}</span>'
            f'<div class="level-desc">{ui["level1_desc"]}</div></div>'
            f'<div class="cards-grid">{l1_cards}</div></section>')

    # Level 2 with filter bar
    l2_cats = sorted(set(a.get("category") for a in l2),
                     key=lambda c: cat_order.index(c) if c in cat_order else 99)
    l2_fbar = (f'<div class="filter-bar">'
               f'<button class="filter-btn l2-filter-btn active" data-cat="all" onclick="filterL2(\'all\')">{ui["all_categories"]}</button>')
    for cat in l2_cats:
        info = categories.get(cat, {})
        lbl = f'{info.get("emoji","")} {get_category_label(cat, lang, categories)}'
        l2_fbar += f'<button class="filter-btn l2-filter-btn" data-cat="{cat}" onclick="filterL2(\'{cat}\')">{lbl}</button>'
    l2_fbar += "</div>"
    l2_cards = "\n".join(card_html(a, lang, ui, categories, "l2") for a in l2)
    sec2 = (f'<section class="level-section" id="level2">'
            f'<div class="level-header"><span class="level-badge badge-l2">Level 2</span>'
            f'<span class="level-title">{ui["level2_title"]}</span>'
            f'<div class="level-desc">{ui["level2_desc"]}</div></div>'
            f'{l2_fbar}<div class="cards-grid">{l2_cards}</div></section>')

    # Level 3
    l3_rows = "\n".join(l3_row_html(a, lang, ui, categories) for a in l3)
    th_align = 'style="text-align:right;"' if is_rtl else ""
    sec3 = (f'<section class="level-section" id="level3">'
            f'<div class="level-header"><span class="level-badge badge-l3">Level 3</span>'
            f'<span class="level-title">{ui["level3_title"]}</span>'
            f'<div class="level-desc">{ui["level3_desc"]}</div></div>'
            f'<div class="search-wrap"><input id="l3-search" class="search-input" type="search" '
            f'placeholder="{ui["search_placeholder"]}" oninput="filterL3()"></div>'
            f'<table class="l3-table"><thead><tr>'
            f'<th {th_align}>Title</th><th {th_align}>Category</th>'
            f'<th {th_align}>Source</th><th {th_align}>Date</th>'
            f'</tr></thead><tbody>{l3_rows}</tbody></table></section>')

    # Sidebar
    src_counts = Counter(a.get("source_name") for a in articles)
    src_rows = "".join(
        f'<div class="sidebar-stat"><span>{s}</span><span class="stat-num">{n}</span></div>'
        for s, n in src_counts.most_common(8)
    )
    cat_counts = Counter(a.get("category") for a in articles)
    cat_rows = ""
    for cat in cat_order:
        n = cat_counts.get(cat, 0)
        if not n:
            continue
        info = categories.get(cat, {})
        lbl = f'{info.get("emoji","")} {get_category_label(cat, lang, categories)}'
        cat_rows += f'<div class="sidebar-stat"><span>{lbl}</span><span class="stat-num">{n}</span></div>'

    by_cat_label = "По категориям" if lang == "ru" else "By Category" if lang == "en" else "לפי קטגוריה"
    top_src_label = "Топ источников" if lang == "ru" else "Top Sources" if lang == "en" else "מקורות מובילים"
    sidebar = (f'<aside class="sidebar">'
               f'<div class="sidebar-card"><div class="sidebar-title">📊 {by_cat_label}</div>{cat_rows}</div>'
               f'<div class="sidebar-card"><div class="sidebar-title">📰 {top_src_label}</div>{src_rows}</div>'
               f'</aside>')

    gfonts = ('<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;700&display=swap" rel="stylesheet">'
              if lang == "he" else
              '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">')

    return f"""<!DOCTYPE html>
<html lang="{lang}" dir="{ui['dir']}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{ui['site_title']} · {label}</title>
{gfonts}
<style>{build_css(lang, ui)}</style>
</head>
<body>
<header class="site-header">
  <div class="header-inner">
    <div><div class="site-title">{ui['site_title']}</div><div class="site-subtitle">{subtitle}</div></div>
    <nav class="lang-switcher">{lang_sw}</nav>
  </div>
</header>
<nav class="cat-nav"><div class="cat-nav-inner">{nav_btns}</div></nav>
<div class="layout">
  <main class="main-content">
    {stats_bar}
    {day_filter}
    {sec1}
    {sec2}
    {sec3}
  </main>
  {sidebar}
</div>
<script>{build_js(lang, ui)}</script>
</body>
</html>"""


# ── Output paths ──────────────────────────────────────────────────────────────

def output_path(lang: str, mode: str) -> Path:
    fname = "daily.html" if mode == "daily" else "index.html"
    return DOCS_DIR / fname if lang == "ru" else DOCS_DIR / lang / fname


def archive_daily_path(lang: str, date_str: str) -> Path:
    return DOCS_DIR / "archive" / "daily" / f"{date_str}_{lang}.html"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daily", "weekly"], required=True)
    parser.add_argument("--date")
    parser.add_argument("--week", type=int)
    parser.add_argument("--lang", choices=["ru", "en", "he"], required=True)
    args = parser.parse_args()

    now = datetime.now(timezone.utc)

    if args.mode == "daily":
        ref = (datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
               if args.date else now.replace(hour=0, minute=0, second=0, microsecond=0))
        raw_base = daily_path(ref.strftime("%Y-%m-%d"))
        label = ref.strftime("%d.%m.%Y")
        date_str = ref.strftime("%Y-%m-%d")
        wnum = None
    else:
        wnum = args.week or week_number(now)
        raw_base = weekly_path(wnum)
        label = f"W{wnum:02d} 2026"
        date_str = None

    translated_path = suffix_path(raw_base, "_translated")
    log.info(f"Loading {translated_path}")
    articles = load_json(translated_path)
    if not articles:
        log.error(f"No articles at {translated_path}")
        sys.exit(1)

    log.info(f"{len(articles)} articles | lang={args.lang} mode={args.mode}")
    categories, cat_order, _ = load_categories()

    if args.mode == "weekly":
        articles = mark_daily_appearances(articles, wnum, now.year)

    html = render(articles, args.lang, args.mode, label, categories, cat_order)

    # Write primary output
    out = output_path(args.lang, args.mode)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    log.info(f"→ {out}  ({len(html)//1024} KB)")

    # Archive daily
    if args.mode == "daily" and date_str:
        arc = archive_daily_path(args.lang, date_str)
        arc.parent.mkdir(parents=True, exist_ok=True)
        arc.write_text(html, encoding="utf-8")
        log.info(f"→ archive {arc}")


if __name__ == "__main__":
    main()
