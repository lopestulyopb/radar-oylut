import asyncio
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse, urldefrag

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser


BLOCKED_PARTS = {
    "author",
    "autor",
    "authors",
    "colunistas",
    "blogs",
    "blog",
    "feed",
    "tag",
    "tags",
    "categoria",
    "category",
    "termos-de-uso",
    "politica-de-privacidade",
    "expediente",
    "comercial",
    "fale-conosco",
    "sobre",
    "contato",
    "mais-lidas",
    "ultimas",
    "ultimas-noticias",
    "series",
    "guia-qualaboa",
    "cdn-cgi",
}

BLOCKED_EXACT_PATHS = {
    "",
    "/",
    "/paraiba",
    "/politica",
    "/brasil",
    "/policial",
    "/mundo",
    "/esporte",
    "/esportes",
    "/cotidiano",
    "/economia",
    "/saude",
    "/educacao",
    "/cultura",
    "/tecnologia",
    "/meio-ambiente",
    "/comunidade",
    "/entretenimento",
    "/blogs",
    "/bichos",
    "/vamos-trabalhar",
    "/joao-pessoa",
}


def normalize_url(base_url: str, href: str) -> str | None:
    if not href:
        return None

    href = href.strip()
    if href.startswith(("mailto:", "tel:", "javascript:", "#")):
        return None

    absolute = urljoin(base_url, href)
    absolute, _ = urldefrag(absolute)
    parsed = urlparse(absolute)

    if parsed.scheme not in {"http", "https"}:
        return None

    clean_path = parsed.path.rstrip("/")
    return parsed._replace(path=clean_path, query="", fragment="").geturl()


def is_candidate_article(url: str, allowed_hosts: set[str]) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    lower_path = path.lower()

    if host not in allowed_hosts:
        return False

    if lower_path in BLOCKED_EXACT_PATHS:
        return False

    if any(f"/{part}/" in f"{lower_path}/" for part in BLOCKED_PARTS):
        return False

    if lower_path.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".xml")):
        return False

    segments = [segment for segment in lower_path.split("/") if segment]

    # ClickPB normalmente usa /editoria/titulo.html.
    if host.endswith("clickpb.com.br"):
        return len(segments) >= 2 and lower_path.endswith(".html")

    # TH+ e Jornal da Paraíba normalmente usam categoria + slug.
    return len(segments) >= 2


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = date_parser.parse(value)
    except (ValueError, TypeError, OverflowError):
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def dates_from_json_ld(soup: BeautifulSoup) -> list[datetime]:
    dates: list[datetime] = []

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"datePublished", "dateCreated", "uploadDate"}:
                    parsed = parse_date(str(item))
                    if parsed:
                        dates.append(parsed)
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text()
        if not raw.strip():
            continue

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        walk(data)

    return dates


def extract_published_at(html: str) -> datetime | None:
    soup = BeautifulSoup(html, "html.parser")
    values: list[str] = []

    selectors = [
        ('meta[property="article:published_time"]', "content"),
        ('meta[property="og:published_time"]', "content"),
        ('meta[name="article:published_time"]', "content"),
        ('meta[name="date"]', "content"),
        ('meta[name="datePublished"]', "content"),
        ('meta[itemprop="datePublished"]', "content"),
        ('time[datetime]', "datetime"),
    ]

    for selector, attribute in selectors:
        for element in soup.select(selector):
            value = element.get(attribute)
            if value:
                values.append(value)

    parsed_dates = [date for value in values if (date := parse_date(value))]
    parsed_dates.extend(dates_from_json_ld(soup))

    if not parsed_dates:
        return None

    # Em caso de múltiplas datas, a mais antiga costuma ser a publicação;
    # atualizações posteriores não devem transformar matéria antiga em recente.
    return min(parsed_dates)


async def fetch_text(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
    except (httpx.HTTPError, httpx.TimeoutException):
        return None


async def collect_candidates(
    client: httpx.AsyncClient,
    source: dict,
) -> set[str]:
    candidates: set[str] = set()

    for list_page in source["list_pages"]:
        html = await fetch_text(client, list_page)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")

        for anchor in soup.select("a[href]"):
            url = normalize_url(list_page, anchor.get("href", ""))

            if url and is_candidate_article(url, source["hosts"]):
                candidates.add(url)

    return candidates


async def published_within_period(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    url: str,
    cutoff: datetime,
    now: datetime,
) -> str | None:
    async with semaphore:
        html = await fetch_text(client, url)

    if not html:
        return None

    published_at = extract_published_at(html)

    if published_at is None:
        return None

    # Tolerância de 10 minutos para relógios divergentes do portal.
    if cutoff <= published_at <= now + timedelta(minutes=10):
        return url

    return None


async def collect_recent_links(sources: list[dict], hours: int = 24) -> list[str]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }

    limits = httpx.Limits(
        max_connections=12,
        max_keepalive_connections=6,
    )

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=20,
        limits=limits,
    ) as client:
        all_candidates: set[str] = set()

        for source in sources:
            all_candidates.update(
                await collect_candidates(client, source)
            )

        semaphore = asyncio.Semaphore(8)

        tasks = [
            published_within_period(
                client=client,
                semaphore=semaphore,
                url=url,
                cutoff=cutoff,
                now=now,
            )
            for url in sorted(all_candidates)
        ]

        results = await asyncio.gather(*tasks)

    return sorted(url for url in results if url)
