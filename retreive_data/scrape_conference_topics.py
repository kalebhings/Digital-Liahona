from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://www.churchofjesuschrist.org"
TOPIC_OVERVIEW_URL = f"{BASE_URL}/study/general-conference/topics?lang=eng"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; scrape-topics/1.0)"}

def get_soup(url: str) -> BeautifulSoup:
    """Return a BeautifulSoup for *url* (retrying once on a transient error)."""
    for attempt in range(2):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser")
        except Exception as exc:
            if attempt == 0:
                time.sleep(3)
                continue
            raise RuntimeError(f"Failed fetching {url}: {exc}") from exc

def slug_to_title(slug: str) -> str:
    """Convert a URL slug like ``aaronic-priesthood`` into ``Aaronic Priesthood``."""
    slug = slug.split("?")[0]  # strip query params if any
    words = slug.replace("-", " ").split()
    return " ".join(w.capitalize() for w in words)

def scrape_topics_overview() -> list[str]:
    """Return *absolute* URLs for every topic page on the overview screen."""
    soup = get_soup(TOPIC_OVERVIEW_URL)

    # Every topic link contains this path fragment.
    selector = 'a[href*="/study/general-conference/topics/"]'
    links = {
        urljoin(BASE_URL, a["href"].split("?")[0])
        for a in soup.select(selector)
        if isinstance(a, Tag) and a.get("href")
    }

    # The first link on the page points back to the overview itself; drop it.
    links = [l for l in links if not l.rstrip("/").endswith("/topics")]
    links.sort()
    return links

def scrape_topic_data(topic_url: str) -> dict:
    """Scrape one *topic* page and return its data structure."""
    slug = topic_url.rstrip("/").split("/")[-1].split("?")[0]
    topic_name = slug_to_title(slug)

    soup = get_soup(topic_url)

    talks: list[dict] = []
    for a in soup.select('a[href*="/study/general-conference/"]'):
        href = a.get("href")
        if not href:
            continue
        full_url = urljoin(BASE_URL, href.split("?")[0])

        # Skip if the anchor is actually a link to a footnote or other section.
        if "/topics/" in full_url:
            continue

        # Pull the visible title (usually inside an <h4> tag).
        title_tag = a.find("h4")
        if not title_tag:
            continue  # not a talk card
        title = title_tag.get_text(strip=True)

        # Speaker line is the full anchor text minus the title (rough but OK).
        anchor_text = " ".join(a.stripped_strings)
        speaker = anchor_text.replace(title, "").strip()

        # Derive year and season from the URL.
        year_match = re.search(r"/(\d{4})/", full_url)
        year = year_match.group(1) if year_match else ""
        season = "April" if "/04/" in full_url else "October" if "/10/" in full_url else ""

        talks.append(
            {
                "title": title,
                "url": full_url,
                "speaker": speaker,
                "year": year,
                "season": season,
            }
        )

    return {
        "topic": topic_name,
        "topic_url": topic_url.split("?")[0],
        "talks": talks,
    }

def main() -> None:
    print("Fetching topic overview…")
    topic_links = scrape_topics_overview()
    print(f"Found {len(topic_links)} topics. Scraping each page…")

    all_topics = []
    for url in topic_links:
        try:
            data = scrape_topic_data(url)
            all_topics.append(data)
            print(f"  ✓ {data['topic']} ({len(data['talks'])} talks)")
        except Exception as exc:
            print(f"  ✗ Failed {url}: {exc}")
            continue
        time.sleep(0.5)

    # Save JSON
    out_dir = Path("data")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "topic_talk_mappings.json"
    with out_path.open("w", encoding="utf-8") as fp:
        json.dump(all_topics, fp, ensure_ascii=False, indent=4)

    print(f"\nSaved {len(all_topics)} topics to {out_path.relative_to(Path.cwd())}")

if __name__ == "__main__":
    main()
