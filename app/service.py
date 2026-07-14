import asyncio
from datetime import datetime, timedelta, timezone
import httpx
from app.collectors.html import collect_html
from app.collectors.rss import collect_rss
from app.config import settings
from app.dedup import cluster_articles
from app.models import Article, NewsCluster, RadarResponse
from app.sources import SOURCES
from app.text import matches_query
from app.tv import analyze_tv


async def run_radar(query: str, hours: int, limit: int) -> RadarResponse:
    headers = {"User-Agent": "Radar-Oylut/3.0 (+telejornalismo; contato editorial)"}
    errors: list[str] = []
    collected: list[Article] = []
    async with httpx.AsyncClient(timeout=settings.request_timeout, headers=headers, follow_redirects=True) as client:
        tasks = []
        for source in SOURCES:
            collector = collect_rss if source.kind == "rss" else collect_html
            tasks.append((source, asyncio.create_task(collector(client, source, settings.max_items_per_source))))
        for source, task in tasks:
            try:
                collected.extend(await task)
            except Exception as exc:
                errors.append(f"{source.name}: {type(exc).__name__}")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    selected = []
    for article in collected:
        searchable = f"{article.title} {article.summary or ''}"
        if not matches_query(searchable, query):
            continue
        # Sem data confiável, o item não entra no recorte estrito de 24h.
        if article.published_at is None:
            continue
        published = article.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if published >= cutoff:
            selected.append(article)

    selected.sort(key=lambda x: x.published_at or cutoff, reverse=True)
    groups = cluster_articles(selected, settings.similarity_threshold)
    clusters: list[NewsCluster] = []
    for group in groups[:limit]:
        lead = max(group, key=lambda x: len(x.summary or ""))
        analysis = analyze_tv(group)
        summary = lead.summary or lead.title
        text = (lead.title + " " + summary).lower()
        municipality = "João Pessoa" if "joão pessoa" in text else None
        clusters.append(NewsCluster(
            headline=lead.title,
            published_at=max((a.published_at for a in group if a.published_at), default=None),
            sources=sorted({a.source for a in group}),
            links=[a.url for a in group],
            summary=summary[:700], municipality=municipality, analysis=analysis,
        ))
    return RadarResponse(
        query=query, period_hours=hours, generated_at=now,
        total_collected=len(collected), total_selected=len(selected),
        clusters=clusters, source_errors=errors,
    )
