from datetime import datetime
from urllib.parse import urljoin
import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from app.models import Article, Source

DATE_KEYS = ("article:published_time", "datePublished", "date", "pubdate", "timestamp")


def parse_date(tag) -> datetime | None:
    candidates = [tag.get("datetime"), tag.get("content")]
    for value in candidates:
        if not value:
            continue
        try:
            return date_parser.parse(value)
        except (ValueError, TypeError, OverflowError):
            pass
    return None


async def collect_html(client: httpx.AsyncClient, source: Source, limit: int) -> list[Article]:
    response = await client.get(str(source.url))
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    articles: list[Article] = []
    seen: set[str] = set()
    for anchor in soup.select("article a[href], h2 a[href], h3 a[href], a[rel='bookmark']"):
        title = anchor.get_text(" ", strip=True)
        if not 20 <= len(title) <= 220:
            continue
        link = urljoin(str(source.url), anchor.get("href", ""))
        if not link.startswith("http") or link in seen:
            continue
        seen.add(link)
        container = anchor.find_parent("article") or anchor.parent
        date_tag = container.find("time") if container else None
        published = parse_date(date_tag) if date_tag else None
        summary_tag = container.find("p") if container else None
        summary = summary_tag.get_text(" ", strip=True) if summary_tag else None
        articles.append(Article(
            title=title, url=link, source=source.name,
            published_at=published, summary=summary
        ))
        if len(articles) >= limit:
            break
    return articles
