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
MAISPB_LATEST = "https://www.maispb.com.br/ultimas-noticias"

EDITORIA_LABELS = {
    "policial": "Segurança", "seguranca": "Segurança", "cotidiano": "Cotidiano",
    "paraiba": "Paraíba", "politica": "Política", "economia": "Economia",
    "emprego": "Serviço", "concursos": "Serviço", "educacao": "Educação",
    "saude": "Saúde", "esporte": "Esportes", "esportes": "Esportes",
    "cultura": "Cultura", "entretenimento": "Entretenimento", "brasil": "Brasil",
    "mundo": "Mundo", "justica": "Justiça", "transito": "Trânsito",
}

# O usuário não vê esta pontuação. Ela serve apenas para ordenar a pauta como programa popular.
EDITORIA_BASE = {
    "Segurança": 56, "Trânsito": 51, "Cotidiano": 47, "Paraíba": 46,
    "Saúde": 45, "Serviço": 44, "Economia": 39, "Justiça": 38,
    "Educação": 35, "Política": 31, "Brasil": 26, "Mundo": 20,
    "Cultura": 14, "Entretenimento": 10, "Geral": 28, "Esportes": -100,
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
    "criança": 7, "crianca": 7, "idoso": 6, "mulher": 4,
}

STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na",
    "nos", "nas", "um", "uma", "para", "por", "com", "que", "se", "ao", "aos", "após",
    "apos", "sobre", "contra", "é", "são", "ser", "tem", "mais", "pb", "paraiba", "joao",
    "pessoa", "diz", "segundo", "nesta", "neste", "durante", "novo", "nova",
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
        # Os portais paraibanos publicam em horário local (UTC-3).
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


def infer_source(url):
    host = urlparse(url).netloc.lower()
    if "clickpb" in host: return "ClickPB"
    if "jornaldaparaiba" in host: return "Jornal da Paraíba"
    if "maispb" in host: return "MaisPB"
    return host.replace("www.", "")


def infer_editoria(url, title=""):
    parts = [part for part in urlparse(url).path.lower().split("/") if part]
    for part in parts:
        if part in EDITORIA_LABELS:
            return EDITORIA_LABELS[part]
    text = normalize_text(title)
    if any(word in text for word in ("preso", "policia", "homicidio", "crime", "assassin", "tiroteio")):
        return "Segurança"
    if any(word in text for word in ("acidente", "atropel", "rodovia", "transito", "interdita")):
        return "Trânsito"
    if any(word in text for word in ("vaga", "concurso", "inscricao", "abastecimento", "prazo")):
        return "Serviço"
    if any(word in text for word in ("futebol", "campeonato", "botafogo pb", "treze", "sousa")):
        return "Esportes"
    return "Geral"


def calculate_relevance(title, summary, editoria, published_at):
    text = normalize_text(f"{title} {summary}")
    score = EDITORIA_BASE.get(editoria, 28)
    for keyword, points in IMPACT_KEYWORDS.items():
        if normalize_text(keyword) in text:
            score += points
    # Impacto coletivo e serviço prático.
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


def is_clickpb_article(url):
    parsed = urlparse(url)
    parts = [part for part in parsed.path.lower().rstrip("/").split("/") if part]
    blocked = {"author", "colunistas", "blogs", "termos-de-uso", "politica-de-privacidade", "ultimas-noticias"}
    return parsed.netloc.lower().replace("www.", "") == "clickpb.com.br" and not any(p in blocked for p in parts) and len(parts) >= 2 and parsed.path.lower().endswith(".html")


def is_maispb_article(url, anchor_text=""):
    parsed = urlparse(url)
    host = parsed.netloc.lower().replace("www.", "")
    if host != "maispb.com.br": return False  # exclui blogs externos/subdomínios nesta etapa
    parts = [p for p in parsed.path.lower().strip("/").split("/") if p]
    blocked = {"ultimas-noticias", "categoria", "tag", "author", "sobre", "expediente", "anuncie", "contato", "page"}
    if not parts or parts[0] in blocked: return False
    return len(clean_text(anchor_text)) >= 24 and len(parts[-1]) >= 15


async def collect_html_candidates(client, page_url, validator, limit=60):
    response = await fetch(client, page_url)
    if response is None: return []
    soup = BeautifulSoup(response.text, "html.parser")
    candidates, seen = [], set()
    for anchor in soup.select("a[href]"):
        text = clean_text(anchor.get_text(" ", strip=True), 200)
        url = normalize_url(page_url, anchor.get("href"))
        if not url or url in seen or not validator(url, text):
            continue
        seen.add(url)
        candidates.append({"url": url, "title": text})
        if len(candidates) >= limit: break
    return candidates


async def collect_clickpb_candidates(client):
    return await collect_html_candidates(client, CLICKPB_LATEST, lambda url, _text: is_clickpb_article(url), 60)


async def collect_maispb_candidates(client):
    return await collect_html_candidates(client, MAISPB_LATEST, is_maispb_article, 60)


async def collect_jornal_candidates(client, hours):
    now, cutoff = datetime.now(timezone.utc), datetime.now(timezone.utc) - timedelta(hours=hours)
    response = await fetch(client, JORNAL_FEED)
    if response is None: return []
    feed = feedparser.parse(response.content)
    candidates, seen = [], set()
    for entry in feed.entries:
        url = normalize_url(JORNAL_FEED, entry.get("link", ""))
        if not url or url in seen: continue
        dt = next((parse_datetime(entry.get(k)) for k in ("published", "updated", "created") if parse_datetime(entry.get(k))), None)
        if dt and not (cutoff <= dt <= now + timedelta(minutes=15)): continue
        seen.add(url)
        candidates.append({"url": url, "title": clean_text(entry.get("title", "")), "summary": clean_text(entry.get("summary", ""), 300), "published_at": dt})
    return candidates


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
            time_tag = soup.find("time", attrs={"datetime": True})
            date_value = time_tag.get("datetime") if time_tag else ""
        published_at = parse_datetime(date_value) or published_at
    now, cutoff = datetime.now(timezone.utc), datetime.now(timezone.utc) - timedelta(hours=hours)
    if published_at and not (cutoff <= published_at <= now + timedelta(minutes=20)):
        return None
    title, summary = clean_text(title, 190), clean_text(summary, 300)
    if not title: return None
    editoria = infer_editoria(candidate["url"], title)
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



def meaningful_words(text):
    return {w for w in normalize_text(text).split() if len(w) >= 4 and w not in STOPWORDS}


def extract_numbers(text):
    return set(re.findall(r"\b\d+(?:[\.,]\d+)?\b", normalize_text(text)))


def event_signature(item):
    title = normalize_text(item.get("titulo", ""))
    summary = normalize_text(item.get("resumo", ""))
    combined = f"{title} {summary}"
    words = meaningful_words(combined)

    # Palavras que ajudam a identificar o núcleo factual.
    action_terms = {
        "morre", "morto", "morta", "mata", "matar", "preso", "presa", "prende",
        "prisao", "homicidio", "assassinato", "acidente", "atropelamento", "atropela",
        "denuncia", "denunciado", "denunciada", "reu", "reus", "absolve", "alerta",
        "vacina", "vacinacao", "chuva", "golpe", "incendio", "apreende", "operacao",
        "desaparecido", "desaparecida", "interdita", "suspende", "aprova", "abre",
    }
    actions = {w for w in words if any(w.startswith(term[:5]) for term in action_terms)}

    # Entidades aproximadas: palavras relevantes do título, excluindo termos genéricos.
    generic = {
        "policia", "civil", "militar", "justica", "paraiba", "jornal", "maispb",
        "clickpb", "caso", "homem", "mulher", "idoso", "idosa", "cidade", "estado",
        "suspeito", "suspeita", "investigado", "investigada", "programa", "confira",
    }
    title_entities = {w for w in meaningful_words(title) if w not in generic and len(w) >= 5}

    return {
        "title": title,
        "summary": summary,
        "words": words,
        "title_words": meaningful_words(title),
        "entities": title_entities,
        "actions": actions,
        "numbers": extract_numbers(combined),
        "editoria": item.get("editoria_interna", "Geral"),
    }


def same_sports_event(sa, sb):
    # Em esporte, só agrupa quando há forte coincidência no título.
    intersection = sa["title_words"] & sb["title_words"]
    overlap = len(intersection) / max(1, min(len(sa["title_words"]), len(sb["title_words"])))
    similarity = SequenceMatcher(None, sa["title"], sb["title"]).ratio()
    return similarity >= 0.86 or (overlap >= 0.82 and len(intersection) >= 5)


def same_event(a, b):
    sa, sb = event_signature(a), event_signature(b)
    if not sa["title_words"] or not sb["title_words"]:
        return False

    if sa["editoria"] == "Esportes" or sb["editoria"] == "Esportes":
        return sa["editoria"] == sb["editoria"] and same_sports_event(sa, sb)

    title_similarity = SequenceMatcher(None, sa["title"], sb["title"]).ratio()
    title_intersection = sa["title_words"] & sb["title_words"]
    title_overlap = len(title_intersection) / max(1, min(len(sa["title_words"]), len(sb["title_words"])))

    all_intersection = sa["words"] & sb["words"]
    all_jaccard = len(all_intersection) / max(1, len(sa["words"] | sb["words"]))

    entity_intersection = sa["entities"] & sb["entities"]
    action_intersection = sa["actions"] & sb["actions"]
    number_intersection = sa["numbers"] & sb["numbers"]

    # 1) Títulos muito semelhantes.
    if title_similarity >= 0.74:
        return True

    # 2) Mesmo núcleo factual: entidades + ação compatível.
    if len(entity_intersection) >= 2 and (action_intersection or title_overlap >= 0.42):
        return True

    # 3) Título e resumo compartilham conjunto expressivo de informações.
    if title_overlap >= 0.48 and all_jaccard >= 0.30 and len(title_intersection) >= 3:
        return True

    # 4) Casos com nome/local/número distintivo, mesmo que os verbos mudem.
    if len(entity_intersection) >= 1 and number_intersection and all_jaccard >= 0.24:
        return True

    return False

def merge_duplicate_events(items):
    groups = []
    for item in sorted(items, key=lambda x: x["relevancia_interna"], reverse=True):
        match = next((saved for saved in groups if same_event(item, saved)), None)
        if match is None:
            groups.append(item)
            continue
        existing_links = {source["link"] for source in match["fontes"]}
        for source in item["fontes"]:
            if source["link"] not in existing_links:
                match["fontes"].append(source)
        # Mantém a versão mais informativa do título e do resumo.
        if len(item["titulo"]) > len(match["titulo"]): match["titulo"] = item["titulo"]
        if item["resumo"] != "Resumo não disponível na fonte." and len(item["resumo"]) > len(match["resumo"]): match["resumo"] = item["resumo"]
        match["relevancia_interna"] = max(match["relevancia_interna"], item["relevancia_interna"]) + min(8, 2 * (len(match["fontes"]) - 1))
        dates = [d for d in (match.get("publicado_em"), item.get("publicado_em")) if d]
        match["publicado_em"] = max(dates) if dates else None
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
        clickpb, jornal, maispb = await asyncio.gather(
            collect_clickpb_candidates(client), collect_jornal_candidates(client, hours),
            collect_maispb_candidates(client),
        )
        candidates, seen = [], set()
        for candidate in clickpb + jornal + maispb:
            if candidate["url"] not in seen:
                seen.add(candidate["url"]); candidates.append(candidate)
        semaphore = asyncio.Semaphore(10)
        enriched = await asyncio.gather(*(enrich_article(client, c, hours, semaphore) for c in candidates))
    events = merge_duplicate_events([item for item in enriched if item])
    # Esporte permanece, mas vai para o fim independentemente da pontuação.
    events.sort(key=lambda x: (x["editoria_interna"] == "Esportes", -x["relevancia_interna"], x["titulo"].lower()))
    return [public_item(item) for item in events]
