from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse, urldefrag

import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser


JORNAL_FEED = "https://jornaldaparaiba.com.br/feed"

CLICKPB_LATEST = "https://www.clickpb.com.br/ultimas-noticias"

MAISPB_LATEST = "https://www.maispb.com.br/ultimas-noticias?cat=22498"

PORTAL_CORREIO_LATEST = "https://portalcorreio.com.br/noticias/"


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

    return parsed._replace(
        query="",
        fragment="",
    ).geturl().rstrip("/")


def is_clickpb_article(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower().rstrip("/")
    parts = [part for part in path.split("/") if part]

    if host not in {
        "clickpb.com.br",
        "www.clickpb.com.br",
    }:
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


def is_maispb_article(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower().rstrip("/")
    parts = [part for part in path.split("/") if part]

    if host not in {
        "maispb.com.br",
        "www.maispb.com.br",
    }:
        return False

    # Formato esperado:
    # /840217/titulo-da-noticia.html
    if len(parts) != 2:
        return False

    article_id, slug = parts

    if not article_id.isdigit():
        return False

    if len(article_id) < 5:
        return False

    if not slug.endswith(".html"):
        return False

    return True


def is_portal_correio_article(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower().strip("/")
    parts = [part for part in path.split("/") if part]

    if host not in {
        "portalcorreio.com.br",
        "www.portalcorreio.com.br",
    }:
        return False

    # As matérias do Portal Correio ficam diretamente na raiz:
    # /titulo-da-noticia/
    if len(parts) != 1:
        return False

    slug = parts[0]

    blocked = {
        "noticias",
        "politica",
        "cotidiano",
        "economia",
        "saude",
        "esportes",
        "entretenimento",
        "editais",
        "busca",
        "fale-conosco",
        "politica-de-privacidade",
    }

    if slug in blocked:
        return False

    if slug.startswith(("page-", "tag-", "author-")):
        return False

    # Evita páginas institucionais e caminhos muito curtos.
    return len(slug.split("-")) >= 4


async def fetch(client, url):
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response
    except Exception as error:
        print(f"Erro ao acessar {url}: {error}")
        return None


async def collect_html_articles(
    client,
    page_url,
    validator,
    limit=20,
):
    response = await fetch(client, page_url)

    if response is None:
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    links = []
    seen = set()

    # Prioriza links que estejam em títulos de matérias.
    selectors = [
        "main h1 a[href]",
        "main h2 a[href]",
        "main h3 a[href]",
        "article h1 a[href]",
        "article h2 a[href]",
        "article h3 a[href]",
        "h1 a[href]",
        "h2 a[href]",
        "h3 a[href]",
        "a[href]",
    ]

    for selector in selectors:
        for anchor in soup.select(selector):
            url = normalize_url(
                page_url,
                anchor.get("href"),
            )

            if not url or not validator(url):
                continue

            if url in seen:
                continue

            seen.add(url)
            links.append(url)

            if len(links) >= limit:
                return links

    return links


async def collect_clickpb_latest_20(client):
    return await collect_html_articles(
        client=client,
        page_url=CLICKPB_LATEST,
        validator=is_clickpb_article,
        limit=20,
    )


async def collect_maispb_latest_20(client):
    return await collect_html_articles(
        client=client,
        page_url=MAISPB_LATEST,
        validator=is_maispb_article,
        limit=20,
    )


async def collect_portal_correio_latest_20(client):
    return await collect_html_articles(
        client=client,
        page_url=PORTAL_CORREIO_LATEST,
        validator=is_portal_correio_article,
        limit=20,
    )


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
        url = normalize_url(
            JORNAL_FEED,
            entry.get("link", ""),
        )

        if not url or url in seen:
            continue

        dt = None

        for key in (
            "published",
            "updated",
            "created",
        ):
            dt = parse_datetime(entry.get(key))

            if dt:
                break

        if dt is None:
            struct = (
                entry.get("published_parsed")
                or entry.get("updated_parsed")
            )

            if struct:
                try:
                    dt = datetime(
                        *struct[:6],
                        tzinfo=timezone.utc,
                    )
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
        "Accept": (
            "text/html,"
            "application/xhtml+xml,"
            "application/rss+xml,"
            "application/xml"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }

    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=20,
    ) as client:
        clickpb = await collect_clickpb_latest_20(client)

        jornal = await collect_jornal_last_24h(
            client,
            hours=hours,
        )

        maispb = await collect_maispb_latest_20(client)

        portal_correio = (
            await collect_portal_correio_latest_20(client)
        )

    result = []
    seen = set()

    all_links = (
        clickpb
        + jornal
        + maispb
        + portal_correio
    )

    for url in all_links:
        if url in seen:
            continue

        seen.add(url)
        result.append(url)

    return result
