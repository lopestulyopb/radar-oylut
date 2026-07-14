from app.dedup import cluster_articles
from app.models import Article
from app.text import matches_query
from app.tv import analyze_tv


def test_query_normalization():
    assert matches_query("Notícia em João Pessoa", "Joao Pessoa")


def test_dedup_similar_titles():
    items = [
        Article(title="Operação apreende armas em João Pessoa", url="https://a", source="A"),
        Article(title="Armas são apreendidas durante operação em João Pessoa", url="https://b", source="B"),
    ]
    assert len(cluster_articles(items, 65)) == 1


def test_tv_score():
    items = [Article(title="Operação causa interdição e afeta moradores de João Pessoa", url="https://a", source="A")]
    analysis = analyze_tv(items)
    assert analysis.tv_score >= 45
