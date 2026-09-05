#!/usr/bin/env python3
"""
Robotaxi / Cybercab news watcher — feeds robotaxi-watch.html

- Pulls fresh articles from Google News RSS for a set of keywords
- Writes them to news.json (title, link, source, category, published, fetched_at)
- Scans new Tesla/Cybercab articles for a fleet-size mention (e.g. "59 vehicles")
  and appends a candidate point to fleet-history.json for the trend chart —
  candidates are marked confirmed:false until a human checks and flips the flag
- robotaxi-watch.html fetches both JSON files directly — no Telegram needed
- Optionally ALSO posts to Telegram if you fill in TELEGRAM_TOKEN / CHAT_ID below
- Keeps a rolling window of the most recent MAX_ITEMS articles

Designed to run both locally (python3 cybercab_watcher.py) and inside the
included GitHub Action (.github/workflows/update-news.yml), which runs this
on a schedule and commits the updated JSON files automatically.

Local setup:
    pip3 install feedparser requests --break-system-packages
    python3 cybercab_watcher.py
"""

import feedparser
import requests
import json
import os
import re
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

# Matches things like "59 vehicles", "a fleet of 25 robotaxis", "25 Model Y robotaxis"
FLEET_SIZE_PATTERN = re.compile(
    r"(?:fleet of\s+)?(\d{1,4})\s+(?:Model [YS3]\s+)?(?:vehicles|robotaxis|cars)",
    re.IGNORECASE
)

HERE = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(HERE, "seen_links.json")
NEWS_FILE = os.path.join(HERE, "news.json")
FLEET_FILE = os.path.join(HERE, "fleet-history.json")
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


def try_extract_fleet_size(title, link, fleet_history):
    """If a Tesla/Cybercab headline mentions a vehicle count, queue it as an
    unconfirmed candidate point for the fleet-size trend chart."""
    match = FLEET_SIZE_PATTERN.search(title)
    if not match:
        return
    count = int(match.group(1))
    # Sanity check: ignore obviously unrelated numbers (too small/huge to be a fleet size)
    if count < 3 or count > 5000:
        return
    now = datetime.now(timezone.utc)
    entry = {
        "date": now.strftime("%Y-%m"),
        "label": now.strftime("%b %Y"),
        "count": count,
        "confirmed": False,
        "source": title,
        "link": link,
    }
    fleet_history.append(entry)
    print("Fleet-size candidate found:", count, "->", title)


def main():
    seen = set(load_json(SEEN_FILE, []))
    news = load_json(NEWS_FILE, [])
    fleet_history = load_json(FLEET_FILE, [])
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

            if category == "CYBERCAB" and "tesla" in kw.lower():
                try_extract_fleet_size(item["title"], link, fleet_history)

            tag = "MONETIZATION" if category == "MONETIZATION" else "CYBERCAB"
            send_telegram(f"[{tag}] <b>{item['title']}</b>\n{item['source']}\n{link}")
            print("New:", item["title"])

    news = news[:MAX_ITEMS]
    save_json(NEWS_FILE, news)
    save_json(SEEN_FILE, list(seen))
    save_json(FLEET_FILE, fleet_history)
    print(f"Done. {new_count} new item(s). {len(news)} total in news.json. {len(fleet_history)} points in fleet-history.json.")


if __name__ == "__main__":
    main()
