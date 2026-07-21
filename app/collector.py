import asyncio
import json
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urldefrag, urljoin, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from app.editorial.categories import calculate_relevance, editorial_bucket, infer_editoria
from app.editorial.deduplication import merge_duplicate_events
from app.editorial.filters import is_excluded_content
from app.editorial.text import clean_text, normalize_text

JORNAL_FEED = "https://jornaldaparaiba.com.br/feed"
CLICKPB_LATEST = "https://www.clickpb.com.br/ultimas-noticias"
MAISPB_LATEST = "https://www.maispb.com.br/ultimas-noticias"
POLEMICA_FEED = "https://www.polemicaparaiba.com.br/feed/"
POLEMICA_LATEST = "https://www.polemicaparaiba.com.br/ultimas-noticias/"


def parse_datetime(value):
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
        dt = dt.replace(tzinfo=timezone(timedelta(hours=-3)))
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


async def fetch(client, url):
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response
    except Exception:
        return None


def meta_content(soup, selectors):
    for attrs in selectors:
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def jsonld_date(soup):
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if isinstance(node, dict) and isinstance(node.get("@graph"), list):
                nodes.extend(node["@graph"])
        for node in nodes:
            if not isinstance(node, dict):
                continue
            for key in ("datePublished", "dateCreated", "dateModified"):
                if node.get(key):
                    return str(node[key])
    return ""


def infer_source(url):
    host = urlparse(url).netloc.lower()
    if "clickpb" in host: return "ClickPB"
    if "jornaldaparaiba" in host: return "Jornal da Paraíba"
    if "maispb" in host: return "MaisPB"
    if "polemicaparaiba" in host: return "Polêmica Paraíba"
    return host.replace("www.", "")


def is_clickpb_article(url):
    parsed = urlparse(url)
    parts = [part for part in parsed.path.lower().rstrip("/").split("/") if part]
    blocked = {"author", "colunistas", "blogs", "termos-de-uso", "politica-de-privacidade", "ultimas-noticias"}
    return parsed.netloc.lower().replace("www.", "") == "clickpb.com.br" and not any(p in blocked for p in parts) and len(parts) >= 2 and parsed.path.lower().endswith(".html")


def is_maispb_article(url, anchor_text=""):
    parsed = urlparse(url)
    if parsed.netloc.lower().replace("www.", "") != "maispb.com.br": return False
    parts = [p for p in parsed.path.lower().strip("/").split("/") if p]
    blocked = {"ultimas-noticias", "categoria", "tag", "author", "sobre", "expediente", "anuncie", "contato", "page"}
    return bool(parts) and parts[0] not in blocked and len(clean_text(anchor_text)) >= 24 and len(parts[-1]) >= 15



def is_polemica_article(url, anchor_text=""):
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    parts = [p for p in parsed.path.lower().strip("/").split("/") if p]
    blocked = {"ultimas-noticias", "category", "tag", "author", "opiniao", "colunas", "ao-vivo", "feed", "page"}
    return host == "polemicaparaiba.com.br" and len(parts) >= 1 and not any(p in blocked for p in parts) and len(clean_text(anchor_text)) >= 24




async def collect_html_candidates(client, page_url, validator, limit=60):
    response = await fetch(client, page_url)
    if response is None: return []
    soup = BeautifulSoup(response.text, "html.parser")
    candidates, seen = [], set()
    for anchor in soup.select("article a[href], h2 a[href], h3 a[href], .entry-title a[href], .post-title a[href], a[href]"):
        text = clean_text(anchor.get_text(" ", strip=True), 200)
        url = normalize_url(page_url, anchor.get("href"))
        if not url or url in seen or not validator(url, text):
            continue
        seen.add(url)
        candidates.append({"url": url, "title": text})
        if len(candidates) >= limit: break
    return candidates


async def collect_feed_candidates(client, feed_url, hours, source_validator=None, limit=80):
    now, cutoff = datetime.now(timezone.utc), datetime.now(timezone.utc) - timedelta(hours=hours)
    response = await fetch(client, feed_url)
    if response is None: return []
    feed = feedparser.parse(response.content)
    candidates, seen = [], set()
    for entry in feed.entries:
        url = normalize_url(feed_url, entry.get("link", ""))
        if not url or url in seen or (source_validator and not source_validator(url, entry.get("title", ""))):
            continue
        dt = None
        for key in ("published", "updated", "created"):
            dt = parse_datetime(entry.get(key))
            if dt: break
        if dt and not (cutoff <= dt <= now + timedelta(minutes=20)):
            continue
        seen.add(url)
        candidates.append({
            "url": url,
            "title": clean_text(entry.get("title", "")),
            "summary": clean_text(entry.get("summary", ""), 320),
            "published_at": dt,
        })
        if len(candidates) >= limit: break
    return candidates


async def collect_clickpb_candidates(client):
    return await collect_html_candidates(client, CLICKPB_LATEST, lambda url, _text: is_clickpb_article(url), 60)


async def collect_maispb_candidates(client):
    return await collect_html_candidates(client, MAISPB_LATEST, is_maispb_article, 60)


async def collect_jornal_candidates(client, hours):
    return await collect_feed_candidates(client, JORNAL_FEED, hours, limit=80)



async def collect_polemica_candidates(client, hours):
    feed = await collect_feed_candidates(client, POLEMICA_FEED, hours, is_polemica_article, 80)
    if feed:
        return feed
    return await collect_html_candidates(client, POLEMICA_LATEST, is_polemica_article, 60)




EDITORIA_FILTERS = {
    "todas": None,
    "seguranca": {"Segurança", "Trânsito"},
    "servico": {"Serviço", "Saúde", "Educação", "Economia"},
    "esportes": {"Esportes"},
    "politica": {"Política", "Justiça"},
    "geral": {"Geral", "Cotidiano", "Paraíba", "Brasil", "Mundo", "Cultura", "Entretenimento"},
}


def matches_editoria_filter(editoria, selected):
    allowed = EDITORIA_FILTERS.get(selected)
    return allowed is None or editoria in allowed


def candidate_may_match(candidate, selected):
    if selected == "todas":
        return True
    preliminary = infer_editoria(candidate.get("url", ""), candidate.get("title", ""), candidate.get("summary", ""))
    return matches_editoria_filter(preliminary, selected)


async def enrich_article(client, candidate, hours, semaphore, editoria_filter="todas"):
    async with semaphore:
        response = await fetch(client, candidate["url"])
    title, summary, published_at = candidate.get("title", ""), candidate.get("summary", ""), candidate.get("published_at")
    if response is not None:
        soup = BeautifulSoup(response.text, "html.parser")
        title = meta_content(soup, [{"property": "og:title"}, {"name": "twitter:title"}]) or title or (clean_text(soup.title.string) if soup.title and soup.title.string else "")
        summary = meta_content(soup, [{"property": "og:description"}, {"name": "description"}, {"name": "twitter:description"}]) or summary
        date_value = meta_content(soup, [{"property": "article:published_time"}, {"name": "datePublished"}, {"itemprop": "datePublished"}, {"property": "og:updated_time"}])
        if not date_value:
            date_value = jsonld_date(soup)
        if not date_value:
            time_tag = soup.find("time", attrs={"datetime": True})
            date_value = time_tag.get("datetime") if time_tag else ""
        published_at = parse_datetime(date_value) or published_at
    now, cutoff = datetime.now(timezone.utc), datetime.now(timezone.utc) - timedelta(hours=hours)
    if published_at and not (cutoff <= published_at <= now + timedelta(minutes=20)):
        return None
    title, summary = clean_text(title, 190), clean_text(summary, 320)
    if not title or is_excluded_content(candidate["url"], title, summary): return None
    editoria = infer_editoria(candidate["url"], title, summary)
    if not matches_editoria_filter(editoria, editoria_filter):
        return None
    score = calculate_relevance(title, summary, editoria, published_at)
    source = infer_source(candidate["url"])
    return {
        "titulo": title,
        "resumo": summary or "Resumo não disponível na fonte.",
        "editoria_interna": editoria,
        "relevancia_interna": score,
        "publicado_em": published_at.isoformat() if published_at else None,
        "fontes": [{"nome": source, "link": candidate["url"]}],
    }


def public_item(item):
    return {
        "titulo": item["titulo"],
        "resumo": item["resumo"],
        "publicado_em": item.get("publicado_em"),
        "fontes": item["fontes"],
    }


async def collect_news(hours=24, editoria="todas"):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/xml",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=25) as client:
        clickpb, jornal, maispb, polemica = await asyncio.gather(
            collect_clickpb_candidates(client),
            collect_jornal_candidates(client, hours),
            collect_maispb_candidates(client),
            collect_polemica_candidates(client, hours),
        )
        candidates, seen = [], set()
        for candidate in clickpb + jornal + maispb + polemica:
            if candidate["url"] not in seen:
                seen.add(candidate["url"])
                if candidate_may_match(candidate, editoria):
                    candidates.append(candidate)
        semaphore = asyncio.Semaphore(10)
        enriched = await asyncio.gather(*(enrich_article(client, c, hours, semaphore, editoria) for c in candidates))
    events = merge_duplicate_events([item for item in enriched if item])
    events.sort(key=lambda x: (
        editorial_bucket(x),
        -x["relevancia_interna"],
        -(datetime.fromisoformat(x["publicado_em"]).timestamp() if x.get("publicado_em") else 0),
        x["titulo"].lower(),
    ))
    return [public_item(item) for item in events]
