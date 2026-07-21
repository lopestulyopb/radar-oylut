import asyncio
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from urllib.parse import urldefrag, urljoin, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser


JORNAL_FEED = "https://jornaldaparaiba.com.br/feed"
CLICKPB_LATEST = "https://www.clickpb.com.br/ultimas-noticias"

EDITORIA_LABELS = {
    "policial": "Segurança",
    "seguranca": "Segurança",
    "cotidiano": "Cotidiano",
    "paraiba": "Paraíba",
    "politica": "Política",
    "economia": "Economia",
    "emprego": "Serviço",
    "concursos": "Serviço",
    "educacao": "Educação",
    "saude": "Saúde",
    "esporte": "Esportes",
    "esportes": "Esportes",
    "cultura": "Cultura",
    "entretenimento": "Entretenimento",
    "qualaboa": "Cultura e entretenimento",
    "brasil": "Brasil",
    "mundo": "Mundo",
}

GRAVIDADE_KEYWORDS = {
    "morre": 5,
    "morte": 5,
    "homicidio": 5,
    "assassin": 5,
    "acidente": 4,
    "atropel": 4,
    "desaparecid": 4,
    "preso": 3,
    "prisao": 3,
    "estupro": 5,
    "tiroteio": 5,
    "incendio": 4,
    "explosao": 5,
    "alagamento": 3,
    "interdicao": 3,
    "suspensao": 2,
    "sem agua": 3,
    "falta de agua": 3,
    "vagas": 2,
    "concurso": 2,
    "alerta": 2,
}

EDITORIA_BASE = {
    "Segurança": 8,
    "Cotidiano": 7,
    "Paraíba": 7,
    "Saúde": 6,
    "Serviço": 6,
    "Brasil": 5,
    "Economia": 5,
    "Política": 4,
    "Mundo": 4,
    "Educação": 4,
    "Esportes": 2,
    "Cultura": 1,
    "Entretenimento": 1,
    "Cultura e entretenimento": 1,
    "Geral": 3,
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

    return parsed._replace(query="", fragment="").geturl().rstrip("/")


def normalize_text(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-zA-Z0-9\s]", " ", value).lower()
    return re.sub(r"\s+", " ", value).strip()


def clean_text(value, limit=None):
    text = BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


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


def infer_source(url):
    host = urlparse(url).netloc.lower()
    if "clickpb" in host:
        return "ClickPB"
    if "jornaldaparaiba" in host:
        return "Jornal da Paraíba"
    return host.replace("www.", "")


def infer_editoria(url, title=""):
    parts = [part for part in urlparse(url).path.lower().split("/") if part]
    for part in parts:
        if part in EDITORIA_LABELS:
            return EDITORIA_LABELS[part]

    normalized = normalize_text(title)
    if any(word in normalized for word in ("preso", "policia", "homicidio", "crime", "assassin")):
        return "Segurança"
    if any(word in normalized for word in ("vaga", "concurso", "inscricao", "abastecimento")):
        return "Serviço"
    return "Geral"


def calculate_weight(title, summary, editoria, published_at):
    text = normalize_text(f"{title} {summary}")
    score = EDITORIA_BASE.get(editoria, 3)

    for keyword, points in GRAVIDADE_KEYWORDS.items():
        if keyword in text:
            score += points

    if published_at:
        age_hours = max(0, (datetime.now(timezone.utc) - published_at).total_seconds() / 3600)
        if age_hours <= 1:
            score += 3
        elif age_hours <= 2:
            score += 2
        elif age_hours <= 6:
            score += 1

    return min(score, 20)


def meta_content(soup, selectors):
    for attrs in selectors:
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


async def collect_clickpb_candidates(client):
    response = await fetch(client, CLICKPB_LATEST)
    if response is None:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []
    seen = set()

    for anchor in soup.select("a[href]"):
        url = normalize_url(CLICKPB_LATEST, anchor.get("href"))
        if not url or not is_clickpb_article(url) or url in seen:
            continue

        seen.add(url)
        candidates.append({"url": url})
        if len(candidates) == 20:
            break

    return candidates


async def collect_jornal_candidates(client, hours):
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    response = await fetch(client, JORNAL_FEED)
    if response is None:
        return []

    feed = feedparser.parse(response.content)
    candidates = []
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

        if dt and not (cutoff <= dt <= now + timedelta(minutes=15)):
            continue

        seen.add(url)
        candidates.append(
            {
                "url": url,
                "title": clean_text(entry.get("title", "")),
                "summary": clean_text(entry.get("summary", ""), 240),
                "published_at": dt,
            }
        )

    return candidates


async def enrich_article(client, candidate, hours, semaphore):
    async with semaphore:
        response = await fetch(client, candidate["url"])

    title = candidate.get("title", "")
    summary = candidate.get("summary", "")
    published_at = candidate.get("published_at")

    if response is not None:
        soup = BeautifulSoup(response.text, "html.parser")
        title = meta_content(
            soup,
            [
                {"property": "og:title"},
                {"name": "twitter:title"},
            ],
        ) or (clean_text(soup.title.string) if soup.title and soup.title.string else title)

        summary = meta_content(
            soup,
            [
                {"property": "og:description"},
                {"name": "description"},
                {"name": "twitter:description"},
            ],
        ) or summary

        date_value = meta_content(
            soup,
            [
                {"property": "article:published_time"},
                {"name": "datePublished"},
                {"itemprop": "datePublished"},
            ],
        )
        published_at = parse_datetime(date_value) or published_at

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    if published_at and not (cutoff <= published_at <= now + timedelta(minutes=15)):
        return None

    title = clean_text(title, 180)
    summary = clean_text(summary, 240)
    if not title:
        slug = urlparse(candidate["url"]).path.rstrip("/").split("/")[-1]
        title = slug.replace(".html", "").replace("-", " ").strip().title()

    editoria = infer_editoria(candidate["url"], title)
    weight = calculate_weight(title, summary, editoria, published_at)

    return {
        "titulo": title,
        "link": candidate["url"],
        "editoria": editoria,
        "resumo": summary or "Resumo não disponível na fonte.",
        "peso": weight,
        "fonte": infer_source(candidate["url"]),
        "publicado_em": published_at.isoformat() if published_at else None,
    }


def remove_duplicates(items):
    unique = []
    for item in sorted(items, key=lambda value: value["peso"], reverse=True):
        current = normalize_text(item["titulo"])
        duplicate = False

        for saved in unique:
            previous = normalize_text(saved["titulo"])
            similarity = SequenceMatcher(None, current, previous).ratio()
            current_words = set(current.split())
            previous_words = set(previous.split())
            overlap = len(current_words & previous_words) / max(1, min(len(current_words), len(previous_words)))

            if similarity >= 0.72 or overlap >= 0.78:
                duplicate = True
                break

        if not duplicate:
            unique.append(item)

    return unique


async def collect_news(hours=24):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/xml",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20) as client:
        clickpb, jornal = await asyncio.gather(
            collect_clickpb_candidates(client),
            collect_jornal_candidates(client, hours),
        )

        candidates = []
        seen = set()
        for candidate in clickpb + jornal:
            if candidate["url"] not in seen:
                seen.add(candidate["url"])
                candidates.append(candidate)

        semaphore = asyncio.Semaphore(8)
        tasks = [enrich_article(client, candidate, hours, semaphore) for candidate in candidates]
        enriched = await asyncio.gather(*tasks)

    items = [item for item in enriched if item]
    items = remove_duplicates(items)
    return sorted(items, key=lambda item: (-item["peso"], item["titulo"].lower()))
