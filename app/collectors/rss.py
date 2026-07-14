from datetime import timezone
from email.utils import parsedate_to_datetime
import feedparser
import httpx
from app.models import Article, Source


async def collect_rss(client: httpx.AsyncClient, source: Source, limit: int) -> list[Article]:
    response = await client.get(str(source.url))
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    articles: list[Article] = []
    for entry in feed.entries[:limit]:
        raw_date = entry.get("published") or entry.get("updated")
        published = None
        if raw_date:
            try:
                published = parsedate_to_datetime(raw_date)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                published = None
        link = entry.get("link")
        title = entry.get("title")
        if title and link:
            articles.append(Article(
                title=title.strip(), url=link.strip(), source=source.name,
                published_at=published, summary=entry.get("summary")
            ))
    return articles
