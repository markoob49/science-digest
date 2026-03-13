#!/usr/bin/env python3
"""
generate_audio_review.py
Pipeline: URL → parse → Claude script → Silero TTS → MP3 → reviews.json
Usage: python scripts/generate_audio_review.py "$ARTICLE_URL"
"""

import os
import sys
import json
import re
import subprocess
import hashlib
from datetime import datetime
from pathlib import Path
import urllib.parse

# ── helpers ──────────────────────────────────────────────────────────────────

def slugify_url(url: str) -> str:
    """Turn a URL into a safe filename component."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.replace("www.", "").split(".")[0]  # e.g. arxiv, nature
    path = re.sub(r"[^a-zA-Z0-9]", "_", parsed.path.strip("/"))[:40]
    date = datetime.utcnow().strftime("%Y-%m-%d")
    return f"{date}_{host}_{path}"


def split_text_for_tts(text: str, max_chars: int = 900) -> list[str]:
    """
    Split text into chunks ≤ max_chars, preferring sentence boundaries.
    Silero V5 handles up to ~1000 chars reliably.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks, current = [], ""
    for sent in sentences:
        if len(current) + len(sent) + 1 > max_chars:
            if current:
                chunks.append(current.strip())
            # If a single sentence is too long, break it hard
            while len(sent) > max_chars:
                chunks.append(sent[:max_chars].strip())
                sent = sent[max_chars:]
            current = sent
        else:
            current = (current + " " + sent).strip() if current else sent
    if current:
        chunks.append(current.strip())
    return chunks


# ── article parsing ──────────────────────────────────────────────────────────

def fetch_arxiv(arxiv_id: str) -> dict:
    """Fetch metadata + abstract via arxiv library."""
    import arxiv
    client = arxiv.Client()
    results = list(client.results(arxiv.Search(id_list=[arxiv_id])))
    if not results:
        raise ValueError(f"arXiv paper not found: {arxiv_id}")
    paper = results[0]
    text = f"Title: {paper.title}\n\nAuthors: {', '.join(str(a) for a in paper.authors[:5])}\n\nAbstract:\n{paper.summary}"
    return {
        "title": paper.title,
        "source": "arXiv",
        "text": text,
    }


def fetch_generic(url: str) -> dict:
    """Fetch and parse article text via requests + BeautifulSoup."""
    import requests
    from bs4 import BeautifulSoup

    headers = {"User-Agent": "Mozilla/5.0 (science-digest-bot/1.0)"}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Title
    title = ""
    for sel in ["h1", "meta[property='og:title']", "title"]:
        tag = soup.select_one(sel)
        if tag:
            title = tag.get("content", "") or tag.get_text(strip=True)
            if title:
                break

    # Source / publisher
    source = urllib.parse.urlparse(url).netloc.replace("www.", "")

    # Main text — try common article containers first
    body_text = ""
    for sel in [
        "article", "[role='main']", "main",
        ".article-body", ".post-content", ".entry-content",
        "#article-body", "#main-content",
    ]:
        container = soup.select_one(sel)
        if container:
            paragraphs = container.find_all("p")
            body_text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 40)
            if len(body_text) > 300:
                break

    # Fallback: all <p> tags
    if len(body_text) < 300:
        paragraphs = soup.find_all("p")
        body_text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 40)

    if len(body_text) < 100:
        raise ValueError("Could not extract sufficient text from article page.")

    # Trim to ~8000 chars to stay within Claude context reasonably
    text = f"Title: {title}\nSource: {source}\n\nArticle text:\n{body_text[:8000]}"
    return {"title": title, "source": source, "text": text}


def parse_article(url: str) -> dict:
    """Route to the appropriate parser."""
    # arXiv: abs/XXXX.XXXXX or pdf/XXXX.XXXXX
    arxiv_match = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]+)", url)
    if arxiv_match:
        return fetch_arxiv(arxiv_match.group(1))
    return fetch_generic(url)


# ── Claude script generation ─────────────────────────────────────────────────

SYSTEM_PROMPT = """Ты — ведущий научного подкаста «Наука за неделю». 
Твоя задача — написать захватывающий сценарий для аудио-обзора научной статьи 
длительностью 5–6 минут (примерно 700–850 слов на русском языке).

Структура обзора:
1. Крючок и контекст: почему эта тема важна, какую проблему решает (30–40 сек)
2. Предыстория: зачем вообще изучали эту проблему, что было известно до (40–60 сек)
3. Методология: как именно проводили исследование (60–90 сек)
4. Ключевые результаты: главные находки с конкретными цифрами и фактами (60–90 сек)
5. Ограничения и открытые вопросы: что осталось неясным или спорным (30–40 сек)
6. Значение для науки и практики: почему это важно, что изменится (40–60 сек)
7. Заключение (15–20 сек)

Требования:
- Писать живым разговорным языком, избегать канцелярита
- Никаких скобок, звёздочек, markdown-разметки — только чистый текст для TTS
- Числа и аббревиатуры писать словами (например, «два миллиона» вместо «2 000 000»)
- Не называть себя и не упоминать, что это сгенерированный текст
- Начинать с сильного крючка, не с «Данная статья посвящена...»
- Не сокращать искусственно — лучше 850 слов насыщенного текста, чем 600 пустых
"""


def generate_script(article_text: str) -> str:
    """Call Claude API and return the TTS-ready script."""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY is not set.")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Напиши аудио-обзор для следующей статьи:\n\n{article_text}",
            }
        ],
    )
    return message.content[0].text.strip()


# ── TTS ───────────────────────────────────────────────────────────────────────

def synthesize_silero(script: str, wav_path: str) -> None:
    """Synthesize speech with Silero TTS V5, handling long texts."""
    import torch
    import soundfile as sf
    import numpy as np

    model_path = "/tmp/v5_2_ru.pt"
    if not os.path.isfile(model_path):
        print("Downloading Silero TTS model (~100 MB)…")
        torch.hub.download_url_to_file(
            "https://models.silero.ai/models/tts/ru/v5_2_ru.pt",
            model_path,
        )
    else:
        print("Using cached Silero TTS model.")
    model = torch.package.PackageImporter(model_path).load_pickle("tts_models", "model")
    model.to("cpu")

    chunks = split_text_for_tts(script, max_chars=900)
    print(f"Synthesizing {len(chunks)} chunk(s)…")

    audio_parts = []
    silence = np.zeros(int(48000 * 0.3), dtype=np.float32)  # 0.3 s pause between chunks

    for i, chunk in enumerate(chunks, 1):
        print(f"  Chunk {i}/{len(chunks)}: {len(chunk)} chars")
        audio = model.apply_tts(
            text=chunk,
            speaker="eugene",
            sample_rate=48000,
            put_accent=True,
            put_yo=True,
        )
        audio_parts.append(audio.numpy())
        if i < len(chunks):
            audio_parts.append(silence)

    combined = np.concatenate(audio_parts)
    sf.write(wav_path, combined, 48000)
    print(f"WAV saved: {wav_path} ({len(combined)/48000:.1f} s)")


def wav_to_mp3(wav_path: str, mp3_path: str) -> None:
    """Convert WAV to MP3 using ffmpeg (pre-installed on ubuntu-latest)."""
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "4", mp3_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr}")
    print(f"MP3 saved: {mp3_path}")


# ── metadata ──────────────────────────────────────────────────────────────────

def get_duration(mp3_path: str) -> float:
    """Get MP3 duration in seconds via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            mp3_path,
        ],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def load_reviews(reviews_path: Path) -> list:
    if reviews_path.exists():
        return json.loads(reviews_path.read_text(encoding="utf-8"))
    return []


def save_reviews(reviews_path: Path, reviews: list) -> None:
    reviews_path.write_text(json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: generate_audio_review.py <article_url>", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1].strip()
    repo_root = Path(__file__).parent.parent
    audio_dir = repo_root / "docs" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    reviews_path = audio_dir / "reviews.json"

    # ── idempotency check ─────────────────────────────────────────────────────
    reviews = load_reviews(reviews_path)
    if any(r["url"] == url for r in reviews):
        print(f"⚠️  Review already exists for: {url}  — skipping.")
        sys.exit(0)

    # ── parse article ─────────────────────────────────────────────────────────
    print(f"Fetching article: {url}")
    article = parse_article(url)
    print(f"Title: {article['title']}")
    print(f"Source: {article['source']}")

    # ── generate script ───────────────────────────────────────────────────────
    print("Generating script via Claude…")
    script = generate_script(article["text"])
    word_count = len(script.split())
    print(f"Script generated: {word_count} words")

    # Description = first 2 sentences
    sentences = re.split(r"(?<=[.!?])\s+", script)
    description = " ".join(sentences[:2])

    # ── synthesize ────────────────────────────────────────────────────────────
    slug = slugify_url(url)
    wav_path = f"/tmp/{slug}.wav"
    mp3_filename = f"{slug}.mp3"
    mp3_path = str(audio_dir / mp3_filename)

    synthesize_silero(script, wav_path)
    wav_to_mp3(wav_path, mp3_path)
    os.unlink(wav_path)

    # ── update reviews.json ───────────────────────────────────────────────────
    duration = get_duration(mp3_path)
    entry = {
        "url": url,
        "title": article["title"],
        "source": article["source"],
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "description": description,
        "mp3_filename": mp3_filename,
        "duration_seconds": round(duration),
    }
    reviews.insert(0, entry)  # newest first
    save_reviews(reviews_path, reviews)
    print(f"✅ Review saved to reviews.json: {mp3_filename}")


if __name__ == "__main__":
    main()
