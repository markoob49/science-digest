#!/usr/bin/env python3
import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    load_categories, week_number,
    daily_path, weekly_path, suffix_path,
    setup_logging, load_json, DOCS_DIR, DATA_DIR
)

log = setup_logging("render")

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
        "articles": "статей", "sources": "источников", "categories_label": "категорий",
        "search_placeholder": "Поиск по заголовку…",
        "lang_ru": "RU", "lang_en": "EN", "lang_he": "עב",
        "dir": "ltr",
        "font_family": "'Inter', 'Segoe UI', Arial, sans-serif",
        "day_filter_label": "Скрыть дни, которые вы уже читали:",
        "day_filter_hint": "Нажмите на день — все его статьи скроются. Нажмите снова — вернутся.",
        "day_names": ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"],
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
        "articles": "articles", "sources": "sources", "categories_label": "categories",
        "search_placeholder": "Search by title…",
        "lang_ru": "RU", "lang_en": "EN", "lang_he": "עב",
        "dir": "ltr",
        "font_family": "'Inter', 'Segoe UI', Arial, sans-serif",
        "day_filter_label": "Hide days you've already read:",
        "day_filter_hint": "Click a day to hide its articles. Click again to show them.",
        "day_names": ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],
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
        "articles": "מאמרים", "sources": "מקורות", "categories_label": "קטגוריות",
        "search_placeholder": "חיפוש לפי כותרת…",
        "lang_ru": "RU", "lang_en": "EN", "lang_he": "עב",
        "dir": "rtl",
        "font_family": "'Heebo', 'David', 'Arial Hebrew', Arial, sans-serif",
        "day_filter_label": "הסתר ימים שכבר קראת:",
        "day_filter_hint": "לחץ על יום להסתרת המאמרים שלו. לחץ שוב להצגתם.",
        "day_names": ["ב׳","ג׳","ד׳","ה׳","ו׳","ש׳","א׳"],
    },
}


def get_text(article, field, lang):
    trans = article.get("translations", {})
    if lang != "en" and lang in trans and field in trans[lang]:
        val = trans[lang][field]
        if val and not val.startswith(f"[{lang.upper()}]"):
            return val
    return article.get(field, "")


def get_cat_label(cat, lang, categories):
    return categories.get(cat, {}).get(lang, cat.title())


def mark_daily_appearances(articles, week, year):
    monday = datetime.fromisocalendar(year, week, 1).replace(tzinfo=timezone.utc)
    url_to_date = {}
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
        daily = load_json(path) or []
        for da in daily:
            url = da.get("url", "")
            if url and url not in url_to_date:
                url_to_date[url] = date_str
        log.info(f"  Daily {date_str}: {len(daily)} articles")
    tagged = 0
    for a in articles:
        dd = url_to_date.get(a.get("url", ""))
        a["daily_date"] = dd
        if dd:
            tagged += 1
    log.info(f"Overlap with daily: {tagged}/{len(articles)}")
    return articles


def build_css(lang, ui):
    r = lang == "he"
    cb = "border-right:4px solid var(--cat-color);border-left:none;" if r else "border-left:4px solid var(--cat-color);"
    ld = "row-reverse" if r else "row"
    ta = "right" if r else "left"
    return f"""
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html{{font-size:16px;scroll-behavior:smooth}}
body{{font-family:{ui["font_family"]};direction:{ui["dir"]};background:#F3F4F6;color:#1F2937;line-height:1.6}}
.layout{{display:flex;flex-direction:{ld};max-width:1280px;margin:0 auto;padding:0 1rem;gap:1.5rem;align-items:flex-start}}
.main-content{{flex:1;min-width:0;padding:1.5rem 0}}
.sidebar{{width:280px;flex-shrink:0;position:sticky;top:80px;padding:1.5rem 0}}
.site-header{{background:#111827;color:white;padding:.75rem 0;position:sticky;top:0;z-index:100;box-shadow:0 2px 4px rgba(0,0,0,.3)}}
.header-inner{{max-width:1280px;margin:0 auto;padding:0 1rem;display:flex;align-items:center;justify-content:space-between;flex-direction:{"row-reverse" if r else "row"}}}
.site-title{{font-size:1.2rem;font-weight:700}}
.site-subtitle{{font-size:.8rem;color:#9CA3AF;margin-top:2px}}
.lang-switcher{{display:flex;gap:.5rem}}
.lang-switcher a{{color:#9CA3AF;text-decoration:none;padding:.25rem .6rem;border-radius:4px;font-size:.85rem;font-weight:600;transition:all .15s}}
.lang-switcher a:hover{{color:white;background:rgba(255,255,255,.1)}}
.lang-switcher a.active{{color:white;background:#374151}}
.cat-nav{{background:white;border-bottom:1px solid #E5E7EB;position:sticky;top:52px;z-index:99}}
.cat-nav-inner{{max-width:1280px;margin:0 auto;padding:0 1rem;display:flex;flex-direction:{"row-reverse" if r else "row"};gap:.25rem;overflow-x:auto;scrollbar-width:none}}
.cat-nav-inner::-webkit-scrollbar{{display:none}}
.cat-btn{{padding:.6rem .9rem;border:none;background:none;cursor:pointer;font-size:.82rem;font-weight:500;color:#6B7280;white-space:nowrap;border-bottom:2px solid transparent;transition:all .15s;font-family:inherit}}
.cat-btn:hover{{color:#111827}}.cat-btn.active{{color:#111827;border-bottom-color:#111827;font-weight:600}}
.day-filter-panel{{background:white;border-radius:12px;padding:1rem 1.25rem;margin-bottom:1.25rem;border:1px solid #E5E7EB}}
.day-filter-label{{font-size:.82rem;font-weight:600;color:#374151;margin-bottom:.6rem}}
.day-filter-buttons{{display:flex;flex-direction:{"row-reverse" if r else "row"};gap:.5rem;flex-wrap:wrap;margin-bottom:.4rem}}
.day-btn{{display:flex;flex-direction:column;align-items:center;gap:.1rem;padding:.45rem .8rem;border:1.5px solid #E5E7EB;border-radius:8px;background:white;cursor:pointer;font-family:inherit;transition:all .15s;min-width:60px}}
.day-btn:hover{{border-color:#9CA3AF;background:#F9FAFB}}
.day-btn.hidden-day{{background:#1F2937;border-color:#1F2937}}
.day-btn.hidden-day .day-name{{color:white}}
.day-btn.hidden-day .day-date,.day-btn.hidden-day .day-count{{color:#6B7280}}
.day-name{{font-size:.82rem;font-weight:700;color:#1F2937}}
.day-date{{font-size:.7rem;color:#6B7280;direction:ltr}}
.day-count{{font-size:.68rem;color:#9CA3AF}}
.day-filter-hint{{font-size:.71rem;color:#9CA3AF}}
.level-section{{margin-bottom:2.5rem}}
.level-header{{background:white;border-radius:12px 12px 0 0;padding:1.25rem 1.5rem 1rem;border-bottom:1px solid #E5E7EB}}
.level-title{{font-size:1.3rem;font-weight:700;color:#111827}}
.level-desc{{font-size:.85rem;color:#6B7280;margin-top:.2rem}}
.level-badge{{display:inline-flex;align-items:center;padding:.2rem .7rem;border-radius:99px;font-size:.75rem;font-weight:600;margin-{"right" if not r else "left"}:.75rem}}
.badge-l1{{background:#FEF3C7;color:#92400E}}.badge-l2{{background:#DBEAFE;color:#1E40AF}}.badge-l3{{background:#F3F4F6;color:#374151}}
.cards-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:1rem;padding:1rem;background:white;border-radius:0 0 12px 12px}}
.card{{background:var(--cat-bg,#F9FAFB);border-radius:10px;padding:1.1rem 1.25rem;{cb};transition:box-shadow .15s}}
.card:hover{{box-shadow:0 4px 12px rgba(0,0,0,.08)}}
.card-header{{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:.6rem;gap:.5rem}}
.card-title{{font-size:.95rem;font-weight:600;color:#111827;line-height:1.4}}
.card-title a{{color:inherit;text-decoration:none}}.card-title a:hover{{text-decoration:underline}}
.card-summary{{font-size:.85rem;color:#4B5563;line-height:1.55;margin:.5rem 0}}
.card-footer{{display:flex;align-items:center;flex-direction:{"row-reverse" if r else "row"};justify-content:space-between;margin-top:.75rem;font-size:.78rem;color:#9CA3AF;flex-wrap:wrap;gap:.4rem}}
.card-source-link{{color:var(--cat-color);text-decoration:none;font-weight:500}}.card-source-link:hover{{text-decoration:underline}}
.card-meta{{display:flex;gap:.6rem;align-items:center;direction:ltr;flex-wrap:wrap}}
.daily-badge{{display:inline-flex;align-items:center;padding:.1rem .4rem;border-radius:99px;font-size:.67rem;font-weight:600;background:#F3F4F6;color:#6B7280;border:1px dashed #D1D5DB;white-space:nowrap;direction:ltr}}
.cat-badge{{display:inline-flex;align-items:center;gap:.25rem;padding:.15rem .55rem;border-radius:99px;font-size:.7rem;font-weight:600;background:var(--cat-bg);color:var(--cat-color);border:1px solid var(--cat-color);white-space:nowrap}}
.score-badge{{display:inline-block;padding:.15rem .5rem;border-radius:4px;font-size:.7rem;font-weight:700;background:#F3F4F6;color:#374151;direction:ltr}}
.l3-table{{width:100%;border-collapse:collapse;background:white;border-radius:0 0 12px 12px;overflow:hidden}}
.l3-table th{{background:#F9FAFB;padding:.6rem 1rem;text-align:{ta};font-size:.75rem;font-weight:600;color:#6B7280;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #E5E7EB}}
.l3-table td{{padding:.65rem 1rem;border-bottom:1px solid #F3F4F6;font-size:.85rem;vertical-align:middle}}
.l3-table tr:hover td{{background:#F9FAFB}}
.l3-title a{{color:#1F2937;text-decoration:none;font-weight:500}}.l3-title a:hover{{text-decoration:underline}}
.l3-meta{{white-space:nowrap;color:#9CA3AF;font-size:.78rem;direction:ltr}}
.search-wrap{{padding:1rem 1rem 0;background:white}}
.search-input{{width:100%;padding:.6rem 1rem;border:1px solid #E5E7EB;border-radius:8px;font-size:.9rem;font-family:inherit;direction:{ui["dir"]};outline:none;transition:border-color .15s}}
.search-input:focus{{border-color:#6B7280}}
.sidebar-card{{background:white;border-radius:12px;padding:1.1rem;margin-bottom:1rem}}
.sidebar-title{{font-size:.85rem;font-weight:700;color:#111827;margin-bottom:.75rem}}
.sidebar-stat{{display:flex;flex-direction:{"row-reverse" if r else "row"};justify-content:space-between;padding:.3rem 0;font-size:.83rem;border-bottom:1px solid #F3F4F6}}
.sidebar-stat:last-child{{border-bottom:none}}
.stat-num{{font-weight:700;color:#111827;direction:ltr}}
.stats-bar{{background:white;border-radius:12px;padding:1rem 1.5rem;margin-bottom:1.25rem;display:flex;flex-direction:{"row-reverse" if r else "row"};gap:2rem;flex-wrap:wrap}}
.stat-item{{text-align:center}}
.stat-value{{font-size:1.5rem;font-weight:800;color:#111827;direction:ltr}}
.stat-label{{font-size:.75rem;color:#9CA3AF;text-transform:uppercase;letter-spacing:.04em}}
.filter-bar{{padding:.75rem 1rem;background:#F9FAFB;display:flex;flex-direction:{"row-reverse" if r else "row"};flex-wrap:wrap;gap:.4rem;border-bottom:1px solid #E5E7EB}}
.filter-btn{{padding:.25rem .7rem;border:1px solid #E5E7EB;background:white;border-radius:99px;font-size:.78rem;cursor:pointer;font-family:inherit;transition:all .15s;color:#374151}}
.filter-btn:hover,.filter-btn.active{{background:#111827;color:white;border-color:#111827}}
@media(max-width:900px){{.sidebar{{display:none}}.cards-grid{{grid-template-columns:1fr}}}}
@media(max-width:600px){{.stats-bar{{gap:1rem}}.day-btn{{min-width:50px;padding:.35rem .5rem}}}}
"""


def build_js(lang):
    sk = f"hidden_days_{lang}"
    return f"""
let activeCategory='all';
function filterCategory(cat){{
  activeCategory=cat;
  document.querySelectorAll('.cat-btn').forEach(b=>b.classList.toggle('active',b.dataset.cat===cat));
  document.querySelectorAll('[data-cat]').forEach(el=>{{
    if(el.classList.contains('cat-btn'))return;
    el.style.display=(cat==='all'||el.dataset.cat===cat)?'':'none';
  }});
  applyDayFilter();filterL3();
}}
function filterL2(cat){{
  document.querySelectorAll('.l2-filter-btn').forEach(b=>b.classList.toggle('active',b.dataset.cat===cat||(cat==='all'&&b.dataset.cat==='all')));
  document.querySelectorAll('.card[data-section="l2"]').forEach(card=>{{
    const ok=cat==='all'||card.dataset.cat===cat;
    const dayOk=!hiddenDays.has(card.dataset.daily||'');
    card.style.display=(ok&&dayOk)?'':'none';
  }});
}}
function filterL3(){{
  const q=(document.getElementById('l3-search')?.value||'').toLowerCase();
  document.querySelectorAll('.l3-row').forEach(row=>{{
    const catOk=activeCategory==='all'||row.dataset.cat===activeCategory;
    const txtOk=!q||row.dataset.title.toLowerCase().includes(q);
    const dayOk=!hiddenDays.has(row.dataset.daily||'');
    row.style.display=(catOk&&txtOk&&dayOk)?'':'none';
  }});
}}
const STORAGE_KEY='{sk}';
let hiddenDays=new Set(JSON.parse(localStorage.getItem(STORAGE_KEY)||'[]'));
function toggleDay(date){{
  hiddenDays.has(date)?hiddenDays.delete(date):hiddenDays.add(date);
  localStorage.setItem(STORAGE_KEY,JSON.stringify([...hiddenDays]));
  document.querySelectorAll(`.day-btn[data-date="${{date}}"]`).forEach(b=>b.classList.toggle('hidden-day',hiddenDays.has(date)));
  applyDayFilter();filterL3();
}}
function applyDayFilter(){{
  document.querySelectorAll('.card').forEach(card=>{{
    const catOk=activeCategory==='all'||card.dataset.cat===activeCategory;
    const dayHidden=card.dataset.daily&&hiddenDays.has(card.dataset.daily);
    card.style.display=(catOk&&!dayHidden)?'':'none';
  }});
}}
document.addEventListener('DOMContentLoaded',()=>{{
  hiddenDays.forEach(date=>document.querySelectorAll(`.day-btn[data-date="${{date}}"]`).forEach(b=>b.classList.add('hidden-day')));
  if(hiddenDays.size>0){{applyDayFilter();filterL3();}}
}});
"""


def cv(cat, categories):
    info = categories.get(cat, {})
    return f'style="--cat-color:{info.get("color","#374151")};--cat-bg:{info.get("bg","#F9FAFB")};"'


def daily_badge(daily_date, ui):
    if not daily_date:
        return ""
    try:
        dt = datetime.strptime(daily_date, "%Y-%m-%d")
        return f'<span class="daily-badge">📅 {ui["day_names"][dt.weekday()]} {dt.strftime("%d.%m")}</span>'
    except ValueError:
        return ""


def card_html(a, lang, ui, categories, section):
    title = get_text(a, "title", lang)
    summary = get_text(a, "summary", lang) if a.get("level") in (1, 2) else ""
    url = a.get("url", "#")
    cat = a.get("category", "general")
    emoji = categories.get(cat, {}).get("emoji", "🔬")
    dd = a.get("daily_date") or ""
    da = f' data-daily="{dd}"' if dd else ""
    sum_html = f'<p class="card-summary">{summary}</p>' if summary else ""
    return (f'<div class="card" data-cat="{cat}" data-section="{section}"{da} {cv(cat,categories)}>'
            f'<div class="card-header"><h3 class="card-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>'
            f'<span class="cat-badge">{emoji} {get_cat_label(cat,lang,categories)}</span></div>'
            f'{sum_html}'
            f'<div class="card-footer"><a class="card-source-link" href="{url}" target="_blank" rel="noopener">{ui["source_link"]}</a>'
            f'<span class="card-meta">{daily_badge(dd,ui)}'
            f'<span class="score-badge">{a.get("score",0)}</span>'
            f'<span>{a.get("source_name","")}</span><span>{a.get("date","")}</span>'
            f'</span></div></div>')


def l3_row(a, lang, ui, categories):
    title = get_text(a, "title", lang)
    url = a.get("url", "#")
    cat = a.get("category", "general")
    info = categories.get(cat, {})
    dd = a.get("daily_date") or ""
    da = f' data-daily="{dd}"' if dd else ""
    badge = daily_badge(dd, ui) if dd else ""
    return (f'<tr class="l3-row" data-cat="{cat}" data-title="{title.replace(chr(34),"&quot;")}"{da}>'
            f'<td class="l3-title"><a href="{url}" target="_blank" rel="noopener">{title}</a>{badge}</td>'
            f'<td><span style="background:{info.get("bg","#F9FAFB")};color:{info.get("color","#374151")};'
            f'padding:.15rem .5rem;border-radius:99px;font-size:.72rem;font-weight:600;white-space:nowrap;">'
            f'{info.get("emoji","🔬")} {get_cat_label(cat,lang,categories)}</span></td>'
            f'<td class="l3-meta">{a.get("source_name","")}</td>'
            f'<td class="l3-meta">{a.get("date","")}</td></tr>')


def day_filter_panel(articles, lang, ui):
    counts = Counter(a.get("daily_date") for a in articles if a.get("daily_date"))
    if not counts:
        return ""
    r = lang == "he"
    buttons = []
    for ds in sorted(counts.keys()):
        try:
            dt = datetime.strptime(ds, "%Y-%m-%d")
            buttons.append(f'<button class="day-btn" data-date="{ds}" onclick="toggleDay(\'{ds}\')">'
                           f'<span class="day-name">{ui["day_names"][dt.weekday()]}</span>'
                           f'<span class="day-date">{dt.strftime("%d.%m")}</span>'
                           f'<span class="day-count">{counts[ds]}</span></button>')
        except ValueError:
            continue
    return (f'<div class="day-filter-panel">'
            f'<div class="day-filter-label">📅 {ui["day_filter_label"]}</div>'
            f'<div class="day-filter-buttons">{"".join(buttons)}</div>'
            f'<div class="day-filter-hint">{ui["day_filter_hint"]}</div></div>')


def render(articles, lang, mode, label, categories, cat_order):
    ui = UI[lang]
    r = lang == "he"
    l1 = [a for a in articles if a.get("level") == 1]
    l2 = [a for a in articles if a.get("level") == 2]
    l3 = [a for a in articles if a.get("level") == 3]

    base = "/science-digest"
    ll = {"ru": f"{base}/", "en": f"{base}/en/", "he": f"{base}/he/"}
    if mode == "daily":
        ll = {k: v + "daily.html" for k, v in ll.items()}
    lang_sw = "".join(f'<a href="{ll[l]}" class="{"active" if l==lang else ""}">{ui[f"lang_{l}"]}</a>' for l in ("ru","en","he"))

    cats_present = set(a.get("category") for a in articles)
    nav = f'<button class="cat-btn active" data-cat="all" onclick="filterCategory(\'all\')">{ui["all_categories"]}</button>'
    for cat in cat_order:
        if cat not in cats_present:
            continue
        info = categories.get(cat, {})
        nav += f'<button class="cat-btn" data-cat="{cat}" onclick="filterCategory(\'{cat}\')">{info.get("emoji","")} {get_cat_label(cat,lang,categories)}</button>'

    stats = (f'<div class="stats-bar">'
             f'<div class="stat-item"><div class="stat-value">{len(articles)}</div><div class="stat-label">{ui["articles"]}</div></div>'
             f'<div class="stat-item"><div class="stat-value">{len(set(a.get("source_id") for a in articles))}</div><div class="stat-label">{ui["sources"]}</div></div>'
             f'<div class="stat-item"><div class="stat-value">{len(set(a.get("category") for a in articles))}</div><div class="stat-label">{ui["categories_label"]}</div></div>'
             f'<div class="stat-item"><div class="stat-value">{len(l1)}</div><div class="stat-label">Level 1</div></div>'
             f'<div class="stat-item"><div class="stat-value">{len(l2)}</div><div class="stat-label">Level 2</div></div></div>')

    df = day_filter_panel(articles, lang, ui) if mode == "weekly" else ""

    sec1 = (f'<section class="level-section" id="level1">'
            f'<div class="level-header"><span class="level-badge badge-l1">Level 1</span>'
            f'<span class="level-title">{ui["level1_title"]}</span>'
            f'<div class="level-desc">{ui["level1_desc"]}</div></div>'
            f'<div class="cards-grid">{"".join(card_html(a,lang,ui,categories,"l1") for a in l1)}</div></section>')

    l2_cats = sorted(set(a.get("category") for a in l2), key=lambda c: cat_order.index(c) if c in cat_order else 99)
    l2fb = f'<div class="filter-bar"><button class="filter-btn l2-filter-btn active" data-cat="all" onclick="filterL2(\'all\')">{ui["all_categories"]}</button>'
    for cat in l2_cats:
        info = categories.get(cat, {})
        l2fb += f'<button class="filter-btn l2-filter-btn" data-cat="{cat}" onclick="filterL2(\'{cat}\')">{info.get("emoji","")} {get_cat_label(cat,lang,categories)}</button>'
    l2fb += "</div>"
    sec2 = (f'<section class="level-section" id="level2">'
            f'<div class="level-header"><span class="level-badge badge-l2">Level 2</span>'
            f'<span class="level-title">{ui["level2_title"]}</span>'
            f'<div class="level-desc">{ui["level2_desc"]}</div></div>'
            f'{l2fb}<div class="cards-grid">{"".join(card_html(a,lang,ui,categories,"l2") for a in l2)}</div></section>')

    tha = 'style="text-align:right;"' if r else ""
    sec3 = (f'<section class="level-section" id="level3">'
            f'<div class="level-header"><span class="level-badge badge-l3">Level 3</span>'
            f'<span class="level-title">{ui["level3_title"]}</span>'
            f'<div class="level-desc">{ui["level3_desc"]}</div></div>'
            f'<div class="search-wrap"><input id="l3-search" class="search-input" type="search" placeholder="{ui["search_placeholder"]}" oninput="filterL3()"></div>'
            f'<table class="l3-table"><thead><tr>'
            f'<th {tha}>Title</th><th {tha}>Category</th><th {tha}>Source</th><th {tha}>Date</th>'
            f'</tr></thead><tbody>{"".join(l3_row(a,lang,ui,categories) for a in l3)}</tbody></table></section>')

    src_counts = Counter(a.get("source_name") for a in articles)
    cat_counts = Counter(a.get("category") for a in articles)
    src_rows = "".join(f'<div class="sidebar-stat"><span>{s}</span><span class="stat-num">{n}</span></div>' for s,n in src_counts.most_common(8))
    cat_rows = "".join(f'<div class="sidebar-stat"><span>{categories.get(c,{}).get("emoji","")} {get_cat_label(c,lang,categories)}</span><span class="stat-num">{cat_counts[c]}</span></div>' for c in cat_order if cat_counts.get(c))
    by_cat = "По категориям" if lang=="ru" else "By Category" if lang=="en" else "לפי קטגוריה"
    top_src = "Топ источников" if lang=="ru" else "Top Sources" if lang=="en" else "מקורות מובילים"
    sidebar = (f'<aside class="sidebar">'
               f'<div class="sidebar-card"><div class="sidebar-title">📊 {by_cat}</div>{cat_rows}</div>'
               f'<div class="sidebar-card"><div class="sidebar-title">📰 {top_src}</div>{src_rows}</div></aside>')

    gfonts = ('<link href="https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;700&display=swap" rel="stylesheet">'
              if lang=="he" else
              '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">')

    mode_label = ui["daily"] if mode=="daily" else ui["weekly"]
    return f"""<!DOCTYPE html>
<html lang="{lang}" dir="{ui['dir']}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{ui['site_title']} · {label}</title>
{gfonts}
<style>{build_css(lang,ui)}</style>
</head>
<body>
<header class="site-header">
  <div class="header-inner">
    <div><div class="site-title">{ui['site_title']}</div><div class="site-subtitle">{mode_label} · {label}</div></div>
    <nav class="lang-switcher">{lang_sw}</nav>
  </div>
</header>
<nav class="cat-nav"><div class="cat-nav-inner">{nav}</div></nav>
<div class="layout">
  <main class="main-content">{stats}{df}{sec1}{sec2}{sec3}</main>
  {sidebar}
</div>
<script>{build_js(lang)}</script>
</body>
</html>"""


def output_path(lang, mode):
    fname = "daily.html" if mode=="daily" else "index.html"
    return DOCS_DIR / fname if lang=="ru" else DOCS_DIR / lang / fname


def archive_daily_path(lang, date_str):
    return DOCS_DIR / "archive" / "daily" / f"{date_str}_{lang}.html"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["daily","weekly"], required=True)
    parser.add_argument("--date")
    parser.add_argument("--week", type=int)
    parser.add_argument("--lang", choices=["ru","en","he"], required=True)
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
    articles = load_json(translated_path)
    if not articles:
        log.error(f"No articles at {translated_path}")
        sys.exit(1)

    log.info(f"{len(articles)} articles | lang={args.lang} mode={args.mode}")
    categories, cat_order, _ = load_categories()

    if args.mode == "weekly":
        articles = mark_daily_appearances(articles, wnum, now.year)

    html = render(articles, args.lang, args.mode, label, categories, cat_order)

    out = output_path(args.lang, args.mode)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    log.info(f"→ {out}")

    if args.mode == "daily" and date_str:
        arc = archive_daily_path(args.lang, date_str)
        arc.parent.mkdir(parents=True, exist_ok=True)
        arc.write_text(html, encoding="utf-8")
        log.info(f"→ archive {arc}")


if __name__ == "__main__":
    main()
