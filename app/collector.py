from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse, urldefrag

import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser


JORNAL_FEED = "https://jornaldaparaiba.com.br/feed"
CLICKPB_LATEST = "https://www.clickpb.com.br/ultimas-noticias"


def parse_datetime(value):
    if not value:
        return None

    try:
        dt = date_parser.parse(str(value))
    except (ValueError, TypeError, OverflowError):
        try:
            dt = parsedate_to_datetime(str(value))
        except (ValueError, TypeError, OverflowError):
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def normalize_url(base_url, href):
    if not href:
        return None

    href = href.strip()

    if href.startswith(("mailto:", "tel:", "javascript:", "#")):
        return None

    url = urljoin(base_url, href)
    url, _ = urldefrag(url)
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        return None

    return parsed._replace(query="", fragment="").geturl().rstrip("/")


def is_clickpb_article(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower().rstrip("/")
    parts = [part for part in path.split("/") if part]

    if host not in {"clickpb.com.br", "www.clickpb.com.br"}:
        return False

    blocked = {
        "author",
        "colunistas",
        "blogs",
        "termos-de-uso",
        "politica-de-privacidade",
        "ultimas-noticias",
    }

    if any(part in blocked for part in parts):
        return False

    return len(parts) >= 2 and path.endswith(".html")


async def fetch(client, url):
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response
    except Exception:
        return None


async def collect_clickpb_latest_20(client):
    response = await fetch(client, CLICKPB_LATEST)

    if response is None:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    links = []
    seen = set()

    for anchor in soup.select("a[href]"):
        url = normalize_url(CLICKPB_LATEST, anchor.get("href"))

        if not url or not is_clickpb_article(url):
            continue

        if url in seen:
            continue

        seen.add(url)
        links.append(url)

        if len(links) == 20:
            break

    return links


async def collect_jornal_last_24h(client, hours=24):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    response = await fetch(client, JORNAL_FEED)

    if response is None:
        return []

    feed = feedparser.parse(response.content)
    links = []
    seen = set()

    for entry in feed.entries:
        url = normalize_url(JORNAL_FEED, entry.get("link", ""))

        if not url or url in seen:
            continue

        dt = None

        for key in ("published", "updated", "created"):
            dt = parse_datetime(entry.get(key))
            if dt:
                break

        if dt is None:
            struct = entry.get("published_parsed") or entry.get("updated_parsed")
            if struct:
                try:
                    dt = datetime(*struct[:6], tzinfo=timezone.utc)
                except Exception:
                    dt = None

        if dt and cutoff <= dt <= now + timedelta(minutes=15):
            seen.add(url)
            links.append(url)

    return links


async def collect_links(hours=24):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/xml",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=20,
    ) as client:
        clickpb = await collect_clickpb_latest_20(client)
        jornal = await collect_jornal_last_24h(client, hours=hours)

    result = []
    seen = set()

    for url in clickpb + jornal:
        if url not in seen:
            seen.add(url)
            result.append(url)

    return result
