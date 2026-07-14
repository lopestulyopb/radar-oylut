from rapidfuzz.fuzz import token_set_ratio
from app.models import Article


def cluster_articles(articles: list[Article], threshold: int) -> list[list[Article]]:
    clusters: list[list[Article]] = []
    for article in articles:
        placed = False
        for cluster in clusters:
            if token_set_ratio(article.title, cluster[0].title) >= threshold:
                cluster.append(article)
                placed = True
                break
        if not placed:
            clusters.append([article])
    return clusters
