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


async def run_radar(
    query: str,
    hours: int,
    limit: int,
) -> RadarResponse:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9",
    }

    errors: list[str] = []
    collected: list[Article] = []

    async with httpx.AsyncClient(
        timeout=settings.request_timeout,
        headers=headers,
        follow_redirects=True,
    ) as client:
        tasks = []

        for source in SOURCES:
            collector = (
                collect_rss
                if source.kind == "rss"
                else collect_html
            )

            tasks.append(
                (
                    source,
                    asyncio.create_task(
                        collector(
                            client,
                            source,
                            settings.max_items_per_source,
                        )
                    ),
                )
            )

        for source, task in tasks:
            try:
                collected.extend(await task)

            except httpx.HTTPStatusError as exc:
                errors.append(
                    f"{source.name}: HTTP {exc.response.status_code}"
                )

            except Exception as exc:
                errors.append(
                    f"{source.name}: {type(exc).__name__}"
                )

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    selected: list[Article] = []
    sem_data = 0
    fora_do_periodo = 0
    fora_da_consulta = 0

    for article in collected:
        searchable = (
            f"{article.title} "
            f"{article.summary or ''}"
        )

        if not matches_query(searchable, query):
            fora_da_consulta += 1
            continue

        if article.published_at is None:
            sem_data += 1

            # Inclui provisoriamente itens sem data para diagnóstico.
            # Eles serão marcados como sem data confiável.
            selected.append(article)
            continue

        published = article.published_at

        if published.tzinfo is None:
            published = published.replace(
                tzinfo=timezone.utc
            )

        if published < cutoff:
            fora_do_periodo += 1
            continue

        selected.append(article)

    selected.sort(
        key=lambda item: (
            item.published_at
            or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )

    groups = cluster_articles(
        selected,
        settings.similarity_threshold,
    )

    clusters: list[NewsCluster] = []

    for group in groups[:limit]:
        lead = max(
            group,
            key=lambda item: len(item.summary or ""),
        )

        analysis = analyze_tv(group)
        summary = lead.summary or lead.title
        text = f"{lead.title} {summary}".lower()

        municipality = (
            "João Pessoa"
            if "joão pessoa" in text
            else None
        )

        dates = [
            article.published_at
            for article in group
            if article.published_at is not None
        ]

        clusters.append(
            NewsCluster(
                headline=lead.title,
                published_at=max(dates) if dates else None,
                sources=sorted(
                    {article.source for article in group}
                ),
                links=[
                    article.url
                    for article in group
                ],
                summary=summary[:700],
                municipality=municipality,
                analysis=analysis,
            )
        )

    errors.append(
        "DIAGNÓSTICO: "
        f"{sem_data} itens sem data; "
        f"{fora_do_periodo} fora do período; "
        f"{fora_da_consulta} fora da consulta."
    )

    return RadarResponse(
        query=query,
        period_hours=hours,
        generated_at=now,
        total_collected=len(collected),
        total_selected=len(selected),
        clusters=clusters,
        source_errors=errors,
    )
