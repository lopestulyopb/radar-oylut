import asyncio
import json
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
MAISPB_LATEST = "https://www.maispb.com.br/ultimas-noticias"
WSCOM_FEED = "https://wscom.com.br/feed/"
WSCOM_LATEST = "https://wscom.com.br/category/noticias/"
POLEMICA_FEED = "https://www.polemicaparaiba.com.br/feed/"
POLEMICA_LATEST = "https://www.polemicaparaiba.com.br/ultimas-noticias/"

EDITORIA_LABELS = {
    "policial": "Segurança", "seguranca": "Segurança", "cotidiano": "Cotidiano",
    "paraiba": "Paraíba", "politica": "Política", "economia": "Economia",
    "emprego": "Serviço", "concursos": "Serviço", "educacao": "Educação",
    "saude": "Saúde", "esporte": "Esportes", "esportes": "Esportes",
    "cultura": "Cultura", "entretenimento": "Entretenimento", "brasil": "Brasil",
    "mundo": "Mundo", "justica": "Justiça", "transito": "Trânsito",
    "noticias": "Geral", "cidades": "Paraíba",
}

EDITORIA_BASE = {
    "Segurança": 56, "Trânsito": 52, "Cotidiano": 45, "Paraíba": 43,
    "Saúde": 48, "Serviço": 47, "Economia": 39, "Justiça": 38,
    "Educação": 42, "Política": 35, "Brasil": 25, "Mundo": 18,
    "Cultura": 14, "Entretenimento": 10, "Geral": 28, "Esportes": 35,
}

IMPACT_KEYWORDS = {
    "morre": 26, "morte": 26, "homicidio": 25, "assassin": 25, "feminicidio": 27,
    "estupro": 27, "tiroteio": 24, "sequestro": 23, "desaparecid": 21,
    "acidente": 19, "atropel": 20, "capot": 18, "colisao": 17,
    "incendio": 19, "explosao": 23, "desabamento": 24, "alagamento": 17,
    "enchente": 20, "chuvas intensas": 16, "alerta": 11, "interdicao": 15,
    "sem agua": 18, "falta de agua": 18, "sem energia": 17, "apagao": 18,
    "suspende": 11, "cancelado": 10, "prazo": 8, "inscricao": 8,
    "vagas": 11, "concurso": 11, "emprego": 10, "beneficio": 9,
    "hospital": 10, "doenca": 9, "vacina": 10, "surto": 18,
    "golpe": 14, "fraude": 13, "preso": 13, "prisao": 13, "operacao": 9,
    "crianca": 7, "idoso": 6, "mulher": 4,
}

STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na",
    "nos", "nas", "um", "uma", "para", "por", "com", "que", "se", "ao", "aos", "apos",
    "sobre", "contra", "e", "sao", "ser", "tem", "mais", "pb", "paraiba", "joao",
    "pessoa", "diz", "segundo", "nesta", "neste", "durante", "novo", "nova", "confira",
    "veja", "saiba", "entenda", "caso", "portal", "jornal", "maispb", "clickpb", "wscom",
    "polemica", "homem", "mulher", "suspeito", "suspeita", "investigado", "investigada",
}

ACTION_GROUPS = {
    "morte": {"morre", "morreu", "morto", "morta", "morte", "mata", "matar", "assassinato", "homicidio"},
    "prisao": {"preso", "presa", "prende", "prisao", "captura", "detido", "detida"},
    "acidente": {"acidente", "colisao", "capotamento", "atropelamento", "atropela", "bate", "trem"},
    "denuncia": {"denuncia", "denunciado", "denunciada", "reu", "reus", "processo", "acusado", "acusada"},
    "absolvicao": {"absolve", "absolvido", "absolvida", "arquiva", "arquivado"},
    "alerta": {"alerta", "chuva", "temporal", "previsao", "inmet"},
    "vacina": {"vacina", "vacinacao", "influenza", "gripe", "imunizacao"},
    "golpe": {"golpe", "fraude", "falso", "whatsapp"},
    "operacao": {"operacao", "mandado", "apreende", "apreensao", "busca"},
    "servico": {"vagas", "inscricao", "prazo", "concurso", "curso", "beneficio", "fgts", "inss"},
    "politica": {"aprova", "ldo", "eleicao", "partido", "senado", "deputado", "prefeito", "governador"},
}


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


def normalize_text(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-zA-Z0-9\s]", " ", value).lower()
    return re.sub(r"\s+", " ", value).strip()


def clean_text(value, limit=None):
    text = BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(MaisPB|ClickPB|WSCOM|Polêmica Paraíba|Jornal da Paraíba)\s*[•|\-:]\s*", "", text, flags=re.I)
    text = re.sub(r"\s*[|\-]\s*(MaisPB|ClickPB|WSCOM|Polêmica Paraíba|Jornal da Paraíba)$", "", text, flags=re.I)
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


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
    if "wscom" in host: return "WSCOM"
    if "polemicaparaiba" in host: return "Polêmica Paraíba"
    return host.replace("www.", "")


def infer_editoria(url, title="", summary=""):
    parts = [part for part in urlparse(url).path.lower().split("/") if part]
    for part in parts:
        if part in EDITORIA_LABELS:
            return EDITORIA_LABELS[part]
    text = normalize_text(f"{title} {summary}")
    if any(word in text for word in ("preso", "policia", "homicidio", "crime", "assassin", "tiroteio", "estupro", "trafico")):
        return "Segurança"
    if any(word in text for word in ("acidente", "atropel", "rodovia", "transito", "interdita", "colisao", "capota")):
        return "Trânsito"
    if any(word in text for word in ("vaga", "concurso", "inscricao", "abastecimento", "prazo", "vacina", "alerta", "chuva", "beneficio")):
        return "Serviço"
    if any(word in text for word in ("futebol", "campeonato", "botafogo pb", "treze", "sousa", "serie c", "serie d", "copa")):
        return "Esportes"
    if any(word in text for word in ("prefeito", "governador", "deputado", "senador", "eleicao", "partido", "assembleia", "ldo")):
        return "Política"
    if any(word in text for word in ("justica", "tribunal", "ministerio publico", "juiz", "reu", "reus", "processo")):
        return "Justiça"
    return "Geral"


def calculate_relevance(title, summary, editoria, published_at):
    text = normalize_text(f"{title} {summary}")
    score = EDITORIA_BASE.get(editoria, 28)
    for keyword, points in IMPACT_KEYWORDS.items():
        if normalize_text(keyword) in text:
            score += points
    if re.search(r"\b\d+[\.,]?\d*\s*(mil|milhoes|pessoas|cidades|municipios|vagas)\b", text):
        score += 8
    if any(term in text for term in ("joao pessoa", "campina grande", "paraiba", "bayeux", "cabedelo", "santa rita")):
        score += 4
    if published_at:
        age_hours = max(0, (datetime.now(timezone.utc) - published_at).total_seconds() / 3600)
        if age_hours <= 1: score += 10
        elif age_hours <= 2: score += 8
        elif age_hours <= 6: score += 5
        elif age_hours <= 12: score += 2
    return score


def editorial_bucket(item):
    """Ordem definida pelo produto: policial, serviço, esporte, política/justiça, geral."""
    editoria = item.get("editoria_interna", "Geral")
    text = normalize_text(f"{item.get('titulo', '')} {item.get('resumo', '')}")
    if editoria in {"Segurança", "Trânsito"} or any(k in text for k in ("homicidio", "preso", "crime", "acidente", "atropel", "tiroteio")):
        return 0
    if editoria in {"Serviço", "Saúde", "Educação", "Economia"} or any(k in text for k in ("vaga", "prazo", "inscricao", "vacina", "alerta", "chuva", "fgts", "inss", "abastecimento")):
        return 1
    if editoria == "Esportes":
        return 2
    if editoria in {"Política", "Justiça"}:
        return 3
    return 4


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


def is_wscom_article(url, anchor_text=""):
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    parts = [p for p in parsed.path.lower().strip("/").split("/") if p]
    blocked = {"category", "tag", "author", "opiniao", "opinioes-e-blogs", "feed", "wp-content", "login", "newsletter"}
    return host == "wscom.com.br" and len(parts) >= 1 and not any(p in blocked for p in parts) and len(clean_text(anchor_text)) >= 24


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


async def collect_wscom_candidates(client, hours):
    feed = await collect_feed_candidates(client, WSCOM_FEED, hours, is_wscom_article, 80)
    if feed:
        return feed
    return await collect_html_candidates(client, WSCOM_LATEST, is_wscom_article, 60)


async def collect_polemica_candidates(client, hours):
    feed = await collect_feed_candidates(client, POLEMICA_FEED, hours, is_polemica_article, 80)
    if feed:
        return feed
    return await collect_html_candidates(client, POLEMICA_LATEST, is_polemica_article, 60)


async def enrich_article(client, candidate, hours, semaphore):
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
    if not title: return None
    editoria = infer_editoria(candidate["url"], title, summary)
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


def stem_token(word):
    for suffix in ("amento", "imento", "acoes", "acao", "mente", "ados", "adas", "ido", "ida", "ou", "aram", "eram", "es", "s"):
        if len(word) > len(suffix) + 4 and word.endswith(suffix):
            return word[:-len(suffix)]
    return word


def meaningful_words(text):
    return {stem_token(w) for w in normalize_text(text).split() if len(w) >= 4 and w not in STOPWORDS}


def extract_numbers(text):
    return set(re.findall(r"\b\d+(?:[\.,]\d+)?\b", normalize_text(text)))


def action_labels(text):
    words = set(normalize_text(text).split())
    labels = set()
    for label, variants in ACTION_GROUPS.items():
        if words & variants:
            labels.add(label)
    return labels


def event_signature(item):
    title = normalize_text(item.get("titulo", ""))
    summary = normalize_text(item.get("resumo", ""))
    title_words = meaningful_words(title)
    all_words = meaningful_words(f"{title} {summary}")
    generic = {"policia", "civil", "militar", "justica", "ministerio", "publico", "cidade", "estado", "programa"}
    entities = {w for w in title_words if w not in generic and len(w) >= 5}
    return {
        "title": title,
        "summary": summary,
        "title_words": title_words,
        "words": all_words,
        "entities": entities,
        "actions": action_labels(f"{title} {summary}"),
        "numbers": extract_numbers(f"{title} {summary}"),
        "editoria": item.get("editoria_interna", "Geral"),
        "bucket": editorial_bucket(item),
    }


def token_overlap(a, b):
    return len(a & b) / max(1, min(len(a), len(b)))


def jaccard(a, b):
    return len(a & b) / max(1, len(a | b))


def same_sports_event(sa, sb):
    similarity = SequenceMatcher(None, sa["title"], sb["title"]).ratio()
    overlap = token_overlap(sa["title_words"], sb["title_words"])
    # Esporte exige coincidência muito forte para não juntar partidas distintas.
    return similarity >= 0.88 or (overlap >= 0.84 and len(sa["title_words"] & sb["title_words"]) >= 5)


def same_event(a, b):
    sa, sb = event_signature(a), event_signature(b)
    if not sa["title_words"] or not sb["title_words"]:
        return False
    if sa["editoria"] == "Esportes" or sb["editoria"] == "Esportes":
        return sa["editoria"] == sb["editoria"] and same_sports_event(sa, sb)

    title_sim = SequenceMatcher(None, sa["title"], sb["title"]).ratio()
    title_overlap = token_overlap(sa["title_words"], sb["title_words"])
    all_jaccard = jaccard(sa["words"], sb["words"])
    common_entities = sa["entities"] & sb["entities"]
    common_actions = sa["actions"] & sb["actions"]
    common_numbers = sa["numbers"] & sb["numbers"]

    # Não une editorias muito distantes sem evidência excepcional.
    bucket_distance = abs(sa["bucket"] - sb["bucket"])
    if bucket_distance >= 3 and title_sim < 0.82:
        return False

    if title_sim >= 0.72:
        return True
    if title_overlap >= 0.60 and len(sa["title_words"] & sb["title_words"]) >= 3:
        return True
    if len(common_entities) >= 2 and common_actions and all_jaccard >= 0.18:
        return True
    if len(common_entities) >= 2 and all_jaccard >= 0.28:
        return True
    if len(common_entities) >= 1 and common_actions and common_numbers and all_jaccard >= 0.20:
        return True
    # Casos com nome/local distintivo e descrição muito próxima, mesmo que o verbo mude.
    if len(common_entities) >= 3 and all_jaccard >= 0.22:
        return True
    return False


def merge_duplicate_events(items):
    groups = []
    # Mais recentes e relevantes viram a referência do grupo.
    ordered = sorted(items, key=lambda x: (x.get("publicado_em") or "", x["relevancia_interna"]), reverse=True)
    for item in ordered:
        match = next((saved for saved in groups if same_event(item, saved)), None)
        if match is None:
            groups.append(item)
            continue
        existing_links = {source["link"] for source in match["fontes"]}
        for source in item["fontes"]:
            if source["link"] not in existing_links:
                match["fontes"].append(source)
        if len(item["titulo"]) > len(match["titulo"]):
            match["titulo"] = item["titulo"]
        if item["resumo"] != "Resumo não disponível na fonte." and len(item["resumo"]) > len(match["resumo"]):
            match["resumo"] = item["resumo"]
        match["relevancia_interna"] = max(match["relevancia_interna"], item["relevancia_interna"]) + min(8, 2 * (len(match["fontes"]) - 1))
        dates = [d for d in (match.get("publicado_em"), item.get("publicado_em")) if d]
        match["publicado_em"] = max(dates) if dates else None
        # Reclassifica após a fusão, caso o título mais completo mude a editoria.
        match["editoria_interna"] = infer_editoria(match["fontes"][0]["link"], match["titulo"], match["resumo"])
    return groups


def public_item(item):
    return {
        "titulo": item["titulo"],
        "resumo": item["resumo"],
        "publicado_em": item.get("publicado_em"),
        "fontes": item["fontes"],
    }


async def collect_news(hours=24):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/xml",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=25) as client:
        clickpb, jornal, maispb, wscom, polemica = await asyncio.gather(
            collect_clickpb_candidates(client),
            collect_jornal_candidates(client, hours),
            collect_maispb_candidates(client),
            collect_wscom_candidates(client, hours),
            collect_polemica_candidates(client, hours),
        )
        candidates, seen = [], set()
        for candidate in clickpb + jornal + maispb + wscom + polemica:
            if candidate["url"] not in seen:
                seen.add(candidate["url"])
                candidates.append(candidate)
        semaphore = asyncio.Semaphore(12)
        enriched = await asyncio.gather(*(enrich_article(client, c, hours, semaphore) for c in candidates))
    events = merge_duplicate_events([item for item in enriched if item])
    events.sort(key=lambda x: (
        editorial_bucket(x),
        -x["relevancia_interna"],
        -(datetime.fromisoformat(x["publicado_em"]).timestamp() if x.get("publicado_em") else 0),
        x["titulo"].lower(),
    ))
    return [public_item(item) for item in events]
