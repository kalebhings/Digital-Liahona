from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup, Tag

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TG_INDEX_URL = "https://www.churchofjesuschrist.org/study/scriptures/tg?lang=eng"
BD_INDEX_URL = "https://www.churchofjesuschrist.org/study/scriptures/bd?lang=eng"
BASE = "https://www.churchofjesuschrist.org"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

SCRIPTURE_PATH_RE = re.compile(r"/study/scriptures/([^/]+)/([^/]+)/([^/?#]+)")
VERSE_RE = re.compile(r"p(\d+)")

# ---------------------------------------------------------------------------
# Networking helpers
# ---------------------------------------------------------------------------
class RetrySession(requests.Session):
    def __init__(self, retries: int = 4, backoff: float = 2.0):
        super().__init__()
        self.retries = retries
        self.backoff = backoff
        self.headers.update(HEADERS)

    def get(self, url: str, **kw):  # type: ignore[override]
        for attempt in range(1, self.retries + 1):
            try:
                r = super().get(url, timeout=30, **kw)
                if r.status_code >= 500 or r.status_code in {429}:
                    raise requests.HTTPError(str(r.status_code))
                return r
            except (requests.RequestException, requests.HTTPError):
                if attempt == self.retries:
                    raise
                time.sleep(self.backoff * attempt)
        raise RuntimeError("unreachable")

SESSION = RetrySession()

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
SPECIAL_BOOKS = {
    'bofm': 'Book of Mormon',
    'ot': 'Old Testament',
    'nt': 'New Testament',
    'dc-testament': 'Doctrine and Covenants',
    'pgp': 'Pearl of Great Price',
    'gen': 'Genesis', 'ex': 'Exodus', 'lev': 'Leviticus', 'num': 'Numbers', 'deut': 'Deuteronomy',
    'josh': 'Joshua', 'judg': 'Judges', 'ruth': 'Ruth', '1-sam': '1 Samuel', '2-sam': '2 Samuel',
    '1-kgs': '1 Kings', '2-kgs': '2 Kings', '1-chr': '1 Chronicles', '2-chr': '2 Chronicles',
    'ezra': 'Ezra', 'neh': 'Nehemiah', 'esth': 'Esther', 'job': 'Job', 'ps': 'Psalms',
    'prov': 'Proverbs', 'eccl': 'Ecclesiastes', 'song': 'Song of Solomon', 'isa': 'Isaiah',
    'jer': 'Jeremiah', 'lam': 'Lamentations', 'ezek': 'Ezekiel', 'dan': 'Daniel', 'hosea': 'Hosea',
    'joel': 'Joel', 'amos': 'Amos', 'obad': 'Obadiah', 'jonah': 'Jonah', 'micah': 'Micah',
    'nahum': 'Nahum', 'hab': 'Habakkuk', 'zeph': 'Zephaniah', 'hag': 'Haggai', 'zech': 'Zechariah',
    'mal': 'Malachi',
    'matt': 'Matthew', 'mark': 'Mark', 'luke': 'Luke', 'john': 'John', 'acts': 'Acts', 'rom': 'Romans',
    '1-cor': '1 Corinthians', '2-cor': '2 Corinthians', 'gal': 'Galatians', 'eph': 'Ephesians',
    'philip': 'Philippians', 'col': 'Colossians', '1-thes': '1 Thessalonians', '2-thes': '2 Thessalonians',
    '1-tim': '1 Timothy', '2-tim': '2 Timothy', 'titus': 'Titus', 'philem': 'Philemon', 'heb': 'Hebrews',
    'james': 'James', '1-pet': '1 Peter', '2-pet': '2 Peter', '1-jn': '1 John', '2-jn': '2 John',
    '3-jn': '3 John', 'jude': 'Jude', 'rev': 'Revelation',
    '1-ne': '1 Nephi', '2-ne': '2 Nephi', 'jacob': 'Jacob', 'enos': 'Enos', 'jarom': 'Jarom',
    'omni': 'Omni', 'w-of-m': 'Words of Mormon', 'mosiah': 'Mosiah', 'alma': 'Alma', 'hel': 'Helaman',
    '3-ne': '3 Nephi', '4-ne': '4 Nephi', 'morm': 'Mormon', 'ether': 'Ether', 'moro': 'Moroni',
    'dc': 'Doctrine and Covenants', 'js-h': 'Joseph Smith—History', 'js-m': 'Joseph Smith—Matthew',
    'a-of-f': 'Articles of Faith', 'abr': 'Abraham', 'fac': 'Facsimile'
}

def slug_to_book(slug: str) -> str:
    return SPECIAL_BOOKS.get(slug, slug.replace("-", " ").title())

def parse_scripture_uri(href: str) -> Optional[str]:
    """Return e.g. "Ezek 21:26" or None."""
    m = SCRIPTURE_PATH_RE.match(urlparse(href).path)
    if not m:
        return None
    _canon, book_slug, chapter = m.groups()
    book = slug_to_book(book_slug)

    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    qv = qs.get("id", [""])[0]
    verse_match = VERSE_RE.search(qv) or VERSE_RE.search(parsed.fragment)
    verse = verse_match.group(1).lstrip("0") if verse_match else None
    return f"{book} {chapter}:{verse}" if verse else f"{book} {chapter}"

# ---------------------------------------------------------------------------
# Scraping routines
# ---------------------------------------------------------------------------

def soup(url: str) -> BeautifulSoup:
    r = SESSION.get(url)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")


def collect_links(index_url: str, prefix: str, max_n: Optional[int]) -> List[Dict[str, str]]:
    page = soup(index_url)
    links: list[dict[str, str]] = []
    seen: Set[str] = set()
    for a in page.select(f"a[href^='{prefix}']"):
        href = urljoin(BASE, a.get("href", ""))
        if href in seen:
            continue
        seen.add(href)
        text = a.get_text(strip=True)
        if text:
            links.append({"entry": text, "entry_url": href})
        if max_n and len(links) >= max_n:
            break
    return links


PARA_ID_RE = re.compile(r"p(\d+)")

def scrape_entry(url: str) -> List[dict]:
    doc = soup(url)
    art = doc.find("article")
    if not art:
        return []

    # 1) see / see‑also blocks (shared by TG & BD)
    blocks: List[Tag] = art.select("nav.index p.title, nav.index p.entry")
    # 2) main body paragraphs (BD & some TG)
    body_ps = art.select("p[id^='p']")
    blocks.extend(body_ps)

    paragraphs: list[dict] = []
    seen_para_ids: Set[str] = set()

    for blk in blocks:
        pid = blk.get("id") or blk.get("data-aid") or ""  # anchor to dedupe
        if pid and pid in seen_para_ids:
            continue
        if pid:
            seen_para_ids.add(pid)

        text = blk.get_text(" ", strip=True).replace("\u00a0", " ")
        if not text:
            continue

        para: dict = {
            "paragraph_number": len(paragraphs) + 1,
            "text": text,
        }

        # scripture refs (any <a> into /study/scriptures/)
        refs = []
        for a in blk.select("a[href^='/study/scriptures/']"):
            ref = parse_scripture_uri(a.get("href", ""))
            if ref:
                refs.append(ref)
        if refs:
            para["scripture_references"] = refs

        # cross‑refs (TG/BD links) in see‑blocks
        if "title" in blk.get("class", []):
            para["type"] = "see"
            linked = []
            for a in blk.select("a[href*='/tg/'], a[href*='/bd/']"):
                linked.append({
                    "entry": a.get_text(strip=True),
                    "href": urljoin(BASE, a.get("href", ""))
                })
            if linked:
                para["linked_entries"] = linked

        paragraphs.append(para)
    return paragraphs


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def ensure_data_dir() -> Path:
    p = Path("data")
    p.mkdir(exist_ok=True)
    return p

def dump(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=4), encoding="utf-8")


def scrape_collection(label: str, index_url: str, prefix: str, max_n: Optional[int]):
    links = collect_links(index_url, prefix, max_n)
    total = len(links)
    out = []
    for i, link in enumerate(links, 1):
        try:
            paras = scrape_entry(link["entry_url"])
            out.append({**link, "paragraphs": paras})
            print(f"{label}: {i}/{total} ✓ {link['entry']}")
        except Exception as e:  # pylint: disable=broad-except
            print(f"{label}: {i}/{total} ✗ {link['entry']} — {e}")
            out.append({**link, "paragraphs": [], "error": str(e)})
    return out


def main():
    ap = argparse.ArgumentParser(description="Scrape Topical Guide & Bible Dictionary")
    ap.add_argument("--max", type=int, default=None, help="Only first N entries per collection")
    args = ap.parse_args()

    ddir = ensure_data_dir()

    tg_data = scrape_collection("TG", TG_INDEX_URL, "/study/scriptures/tg/", args.max)
    dump(ddir / "topical_guide_entries.json", tg_data)

    bd_data = scrape_collection("BD", BD_INDEX_URL, "/study/scriptures/bd/", args.max)
    dump(ddir / "bible_dictionary_entries.json", bd_data)

    print("\n[✓] Done — files written to", ddir)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
