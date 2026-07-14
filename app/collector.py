import asyncio
import json
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse, urldefrag

import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser


BLOCKED = {
    "author", "autor", "colunistas", "blogs", "blog", "feed", "tag",
    "categoria", "category", "termos-de-uso", "politica-de-privacidade",
    "expediente", "comercial", "fale-conosco", "sobre", "contato",
    "mais-lidas", "ultimas", "ultimas-noticias", "series", "cdn-cgi",
}

CATEGORY_PATHS = {
    "", "/", "/paraiba", "/politica", "/brasil", "/policial", "/mundo",
    "/esporte", "/esportes", "/cotidiano", "/economia", "/saude",
    "/educacao", "/cultura", "/tecnologia", "/meio-ambiente",
    "/comunidade", "/entretenimento", "/blogs", "/bichos",
    "/vamos-trabalhar", "/joao-pessoa",
}


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

    path = parsed.path.rstrip("/")
    return parsed._replace(path=path, query="", fragment="").geturl()


def is_article_url(url, hosts):
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    lower = path.lower()

    if host not in hosts or lower in CATEGORY_PATHS:
        return False

    if any(f"/{item}/" in f"{lower}/" for item in BLOCKED):
        return False

    if lower.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".xml")):
        return False

    segments = [part for part in lower.split("/") if part]

    if host.endswith("clickpb.com.br"):
        return len(segments) >= 2 and lower.endswith(".html")

    return len(segments) >= 2


def extract_page_date(html):
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    selectors = [
        ('meta[property="article:published_time"]', "content"),
        ('meta[property="og:published_time"]', "content"),
        ('meta[name="article:published_time"]', "content"),
        ('meta[name="date"]', "content"),
        ('meta[name="datePublished"]', "content"),
        ('meta[itemprop="datePublished"]', "content"),
        ('time[datetime]', "datetime"),
    ]

    for selector, attr in selectors:
        for element in soup.select(selector):
            value = element.get(attr)
            dt = parse_datetime(value)
            if dt:
                candidates.append(dt)

    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text()
        if not raw.strip():
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        stack = [data]
        while stack:
            item = stack.pop()

            if isinstance(item, dict):
                for key, value in item.items():
                    if key in {"datePublished", "dateCreated"}:
                        dt = parse_datetime(value)
                        if dt:
                            candidates.append(dt)
                    elif isinstance(value, (dict, list)):
                        stack.append(value)

            elif isinstance(item, list):
                stack.extend(item)

    return min(candidates) if candidates else None


async def fetch(client, url):
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response
    except Exception:
        return None


async def collect_from_feed(client, source, cutoff, now):
    links = set()

    for feed_url in source["feeds"]:
        response = await fetch(client, feed_url)
        if response is None:
            continue

        parsed = feedparser.parse(response.content)
        if not parsed.entries:
            continue

        for entry in parsed.entries:
            url = normalize_url(feed_url, entry.get("link", ""))
            if not url or not is_article_url(url, source["hosts"]):
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
                links.add(url)

        # Se um feed válido foi encontrado, não é necessário testar os demais.
        if parsed.entries:
            break

    return links


async def collect_html_candidates(client, source):
    links = set()

    for page_url in source["pages"]:
        response = await fetch(client, page_url)
        if response is None:
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        for anchor in soup.select("a[href]"):
            url = normalize_url(page_url, anchor.get("href", ""))
            if url and is_article_url(url, source["hosts"]):
                links.add(url)

    return links


async def validate_html_article(client, semaphore, url, cutoff, now):
    async with semaphore:
        response = await fetch(client, url)

    if response is None:
        return None

    dt = extract_page_date(response.text)

    if dt and cutoff <= dt <= now + timedelta(minutes=15):
        return url

    return None


async def collect_recent_links(sources, hours=24):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/xml",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }

    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
    final_links = set()

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=15,
        limits=limits,
    ) as client:
        for source in sources:
            # Primeiro tenta RSS.
            feed_links = await collect_from_feed(client, source, cutoff, now)
            final_links.update(feed_links)

            # Fallback HTML caso RSS não produza resultado recente.
            if not feed_links:
                candidates = await collect_html_candidates(client, source)
                semaphore = asyncio.Semaphore(6)

                tasks = [
                    validate_html_article(client, semaphore, url, cutoff, now)
                    for url in sorted(candidates)
                ]

                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for result in results:
                        if isinstance(result, str):
                            final_links.add(result)

    return sorted(final_links)
