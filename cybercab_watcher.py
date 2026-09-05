#!/usr/bin/env python3
"""
Robotaxi / Cybercab news watcher — feeds robotaxi-watch.html

- Pulls fresh articles from Google News RSS for a set of keywords
- Writes them to news.json (title, link, source, category, published, fetched_at)
- robotaxi-watch.html fetches news.json directly — no Telegram needed for that
- Optionally ALSO posts to Telegram if you fill in TELEGRAM_TOKEN / CHAT_ID below
- Keeps a rolling window of the most recent MAX_ITEMS articles

Designed to run both locally (python3 cybercab_watcher.py) and inside the
included GitHub Action (.github/workflows/update-news.yml), which runs this
on a schedule and commits the updated news.json automatically.

Local setup:
    pip3 install feedparser requests --break-system-packages
    python3 cybercab_watcher.py
"""

import feedparser
import requests
import json
import os
from datetime import datetime, timezone

# --- OPTIONAL: fill these in if you also want a Telegram post per new item ---
TELEGRAM_TOKEN = ""   # leave empty to skip Telegram entirely
CHAT_ID = ""

KEYWORDS = [
    "Tesla Cybercab",
    "Tesla Robotaxi",
    "Waymo robotaxi",
    "Zoox robotaxi",
    "robotaxi in-car advertising",
    "robotaxi monetization",
]

MONETIZATION_KEYWORDS = ("ad", "monetiz")

HERE = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(HERE, "seen_links.json")
NEWS_FILE = os.path.join(HERE, "news.json")
MAX_ITEMS = 30


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_news(keyword):
    query = keyword.replace(" ", "+")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    return feedparser.parse(url).entries


def send_telegram(text):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
    r = requests.post(url, data=payload, timeout=15)
    if not r.ok:
        print("Telegram error:", r.text)


def main():
    seen = set(load_json(SEEN_FILE, []))
    news = load_json(NEWS_FILE, [])
    new_count = 0

    for kw in KEYWORDS:
        category = "MONETIZATION" if any(k in kw.lower() for k in MONETIZATION_KEYWORDS) else "CYBERCAB"
        for entry in fetch_news(kw):
            link = entry.link
            if link in seen:
                continue
            seen.add(link)
            new_count += 1

            item = {
                "title": entry.title,
                "link": link,
                "source": entry.get("source", {}).get("title", ""),
                "category": category,
                "published": entry.get("published", ""),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            news.insert(0, item)

            tag = "MONETIZATION" if category == "MONETIZATION" else "CYBERCAB"
            send_telegram(f"[{tag}] <b>{item['title']}</b>\n{item['source']}\n{link}")
            print("New:", item["title"])

    news = news[:MAX_ITEMS]
    save_json(NEWS_FILE, news)
    save_json(SEEN_FILE, list(seen))
    print(f"Done. {new_count} new item(s). {len(news)} total in news.json.")


if __name__ == "__main__":
    main()
