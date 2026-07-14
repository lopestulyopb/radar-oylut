from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl


class Source(BaseModel):
    name: str
    url: HttpUrl
    kind: str = Field(pattern="^(rss|html)$")


class Article(BaseModel):
    title: str
    url: str
    source: str
    published_at: datetime | None = None
    summary: str | None = None
    body: str | None = None


class TVAnalysis(BaseModel):
    section: str
    tv_score: int = Field(ge=0, le=100)
    tv_potential: str
    reasons: list[str]
    suggested_sources: list[str]
    suggested_character: str | None = None
    visual_needs: list[str]
    next_steps: list[str]


class NewsCluster(BaseModel):
    headline: str
    published_at: datetime | None
    sources: list[str]
    links: list[str]
    summary: str
    municipality: str | None
    analysis: TVAnalysis


class RadarResponse(BaseModel):
    query: str
    period_hours: int
    generated_at: datetime
    total_collected: int
    total_selected: int
    clusters: list[NewsCluster]
    source_errors: list[str]
