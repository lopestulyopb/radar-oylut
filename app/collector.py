import asyncio
import json
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urldefrag, urljoin, urlparse
from zoneinfo import ZoneInfo

import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser


JORNAL_FEED = "https://jornaldaparaiba.com.br/feed"
CLICKPB_LATEST = "https://www.clickpb.com.br/ultimas-noticias"
MAISPB_LATEST = "https://www.maispb.com.br/ultimas-noticias?cat=22498"
PORTAL_CORREIO_LATEST = "https://portalcorreio.com.br/noticias/"

LOCAL_TIMEZONE = ZoneInfo("America/Fortaleza")

# O Radar coleta mais candidatos do que o resultado final,
# porque várias matérias podem ser descartadas pelo filtro de tempo.
HTML_CANDIDATE_LIMIT = 25


def parse_datetime(value):
    """
    Converte diferentes formatos de data para UTC.

    Quando a página informa data sem fuso horário,
    assume-se o horário local da Paraíba.
    """
    if not value:
        return None

    try:
        dt = date_parser.parse(str(value), dayfirst=True)
    except (ValueError, TypeError, OverflowError):
        try:
            dt = parsedate_to_datetime(str(value))
        except (ValueError, TypeError, OverflowError):
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TIMEZONE)

    return dt.astimezone(timezone.utc)


def normalize_url(base_url, href):
    """
    Converte links relativos em absolutos e remove parâmetros,
    fragmentos e barras finais desnecessárias.
    """
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

    # Padrão esperado:
    # /841092/titulo-da-noticia.html
    if len(parts) != 2:
        return False

    article_id, slug = parts

    return (
        article_id.isdigit()
        and len(article_id) >= 5
        and slug.endswith(".html")
    )


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

    # As matérias do Portal Correio ficam normalmente na raiz:
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
        "dino",
        "fale-conosco",
        "politica-de-privacidade",
    }

    if slug in blocked:
        return False

    if slug.startswith(("page-", "tag-", "author-")):
        return False

    return len(slug.split("-")) >= 4


async def fetch(client, url):
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response
    except Exception as error:
        print(f"Erro ao acessar {url}: {error}")
        return None


def extract_dates_from_json_ld(data):
    """
    Procura datas de publicação em estruturas JSON-LD.
    """
    dates = []

    if isinstance(data, dict):
        for key in (
            "datePublished",
            "dateCreated",
            "uploadDate",
            "dateModified",
        ):
            value = data.get(key)

            if value:
                dates.append(value)

        for value in data.values():
            dates.extend(extract_dates_from_json_ld(value))

    elif isinstance(data, list):
        for item in data:
            dates.extend(extract_dates_from_json_ld(item))

    return dates


def extract_publication_datetime(html):
    """
    Extrai a data de publicação da página da matéria.

    Ordem de prioridade:
    1. metatags de publicação;
    2. JSON-LD;
    3. elementos <time>;
    4. textos visíveis em padrões comuns.
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    meta_selectors = [
        ('meta[property="article:published_time"]', "content"),
        ('meta[name="article:published_time"]', "content"),
        ('meta[property="og:published_time"]', "content"),
        ('meta[name="publication_date"]', "content"),
        ('meta[name="publish-date"]', "content"),
        ('meta[name="pubdate"]', "content"),
        ('meta[itemprop="datePublished"]', "content"),
        ('meta[itemprop="dateCreated"]', "content"),
        ('meta[name="date"]', "content"),
    ]

    for selector, attribute in meta_selectors:
        element = soup.select_one(selector)

        if element:
            value = element.get(attribute)

            if value:
                candidates.append(value)

    for script in soup.select('script[type="application/ld+json"]'):
        content = script.string or script.get_text(strip=True)

        if not content:
            continue

        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            continue

        candidates.extend(extract_dates_from_json_ld(data))

    for time_element in soup.select("time"):
        value = (
            time_element.get("datetime")
            or time_element.get("content")
            or time_element.get_text(" ", strip=True)
        )

        if value:
            candidates.append(value)

    # Alguns portais imprimem a data diretamente em classes específicas.
    visible_date_selectors = [
        '[class*="date"]',
        '[class*="data"]',
        '[class*="publish"]',
        '[class*="posted"]',
        '[class*="time"]',
    ]

    for selector in visible_date_selectors:
        for element in soup.select(selector)[:20]:
            text = element.get_text(" ", strip=True)

            if text:
                candidates.append(text)

    valid_dates = []

    for candidate in candidates:
        dt = parse_datetime(candidate)

        if dt:
            valid_dates.append(dt)

    if not valid_dates:
        return None

    now = datetime.now(timezone.utc)

    # Evita usar datas futuras ou datas antigas de atualização do site.
    plausible_dates = [
        dt
        for dt in valid_dates
        if dt <= now + timedelta(minutes=15)
    ]

    if not plausible_dates:
        return None

    # Normalmente a menor data representa a publicação original,
    # enquanto datas maiores podem representar atualizações.
    return min(plausible_dates)


async def collect_html_candidates(
    client,
    page_url,
    validator,
    limit=HTML_CANDIDATE_LIMIT,
):
    response = await fetch(client, page_url)

    if response is None:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    links = []
    seen = set()

    selectors = [
        "main article a[href]",
        "main h1 a[href]",
        "main h2 a[href]",
        "main h3 a[href]",
        "article a[href]",
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


async def filter_html_links_by_hours(
    client,
    links,
    hours,
    concurrency=8,
):
    """
    Abre as matérias e mantém somente as publicadas
    dentro da janela solicitada.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    semaphore = asyncio.Semaphore(concurrency)

    async def inspect(url):
        async with semaphore:
            response = await fetch(client, url)

        if response is None:
            return None

        published_at = extract_publication_datetime(response.text)

        if published_at is None:
            print(f"Data não encontrada: {url}")
            return None

        if cutoff <= published_at <= now + timedelta(minutes=15):
            return url

        return None

    checked = await asyncio.gather(
        *(inspect(url) for url in links)
    )

    return [url for url in checked if url]


async def collect_clickpb(client, hours):
    candidates = await collect_html_candidates(
        client=client,
        page_url=CLICKPB_LATEST,
        validator=is_clickpb_article,
    )

    return await filter_html_links_by_hours(
        client=client,
        links=candidates,
        hours=hours,
    )


async def collect_maispb(client, hours):
    candidates = await collect_html_candidates(
        client=client,
        page_url=MAISPB_LATEST,
        validator=is_maispb_article,
    )

    return await filter_html_links_by_hours(
        client=client,
        links=candidates,
        hours=hours,
    )


async def collect_portal_correio(client, hours):
    candidates = await collect_html_candidates(
        client=client,
        page_url=PORTAL_CORREIO_LATEST,
        validator=is_portal_correio_article,
    )

    return await filter_html_links_by_hours(
        client=client,
        links=candidates,
        hours=hours,
    )


async def collect_jornal(client, hours):
    """
    O Jornal da Paraíba continua sendo filtrado pelo RSS.
    """
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
    """
    Coleta links publicados no período solicitado
    nas quatro fontes monitoradas.
    """
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
        timeout=25,
        limits=httpx.Limits(
            max_connections=12,
            max_keepalive_connections=8,
        ),
    ) as client:
        (
            clickpb,
            jornal,
            maispb,
            portal_correio,
        ) = await asyncio.gather(
            collect_clickpb(client, hours),
            collect_jornal(client, hours),
            collect_maispb(client, hours),
            collect_portal_correio(client, hours),
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
