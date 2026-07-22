"""Motor de Prioridade Editorial do Radar Oylut — Etapa 6.1.1.

Esta etapa implementa somente:
- prioridade editorial;
- consolidação definitiva de pautas duplicadas.

A classificação visual por Urgente, Serviço, Política etc. fica para a 6.1.2.
"""
from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Iterable
from urllib.parse import urlparse

from bs4 import BeautifulSoup

PORTALS = "MaisPB|ClickPB|Polêmica Paraíba|Jornal da Paraíba"

STOPWORDS = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos",
    "e", "em", "entre", "na", "nas", "no", "nos", "o", "os", "para", "por",
    "que", "se", "sem", "sob", "sobre", "um", "uma", "uns", "umas", "apos",
    "contra", "durante", "nesta", "neste", "novo", "nova", "pb", "diz", "veja",
    "confira", "saiba", "portal", "jornal", "homem", "mulher", "suspeito", "suspeita",
}

LOCATION_RULES: tuple[tuple[int, tuple[str, ...]], ...] = (
    (110, ("joao pessoa", "capital paraibana")),
    (100, ("cabedelo", "bayeux", "santa rita", "conde", "lucena", "regiao metropolitana")),
    (92, ("campina grande",)),
    (78, ("paraiba", "paraibano", "paraibana", "sertao", "brejo", "cariri", "curimatau", "litoral sul", "litoral norte")),
    (36, ("nordeste",)),
    (14, ("brasil", "nacional", "brasileiro", "brasileira")),
    (0, ("internacional", "mundo", "exterior")),
)

TOPIC_RULES: tuple[tuple[int, tuple[str, ...]], ...] = (
    (112, ("morte", "morre", "morreu", "homicidio", "assassinato", "feminicidio", "tiroteio", "chacina")),
    (104, ("acidente", "atropelamento", "colisao", "capotamento", "desabamento", "incendio", "explosao")),
    (100, ("prisao", "preso", "presa", "operacao policial", "mandado", "apreensao", "sequestro", "desaparecido", "desaparecida")),
    (92, ("br 230", "br-230", "transito", "engarrafamento", "interdicao", "bloqueio de via")),
    (88, ("emergencia", "alerta", "chuva forte", "alagamento", "risco", "evacuacao")),
    (78, ("vacinacao", "vacina", "inscricao", "inscricoes", "concurso", "selecao", "vagas", "curso gratuito", "matricula", "abastecimento", "falta de agua", "falta de energia", "transporte publico")),
    (66, ("hospital", "saude", "doenca", "surto", "atendimento", "medicamento")),
    (56, ("escola", "educacao", "universidade", "enem", "professor", "aluno")),
    (48, ("economia", "emprego", "salario", "preco", "gasolina", "inss", "imposto", "beneficio")),
    (34, ("esporte", "futebol", "botafogo pb", "treze", "campinense", "cultura", "festival")),
    (28, ("meio ambiente", "ambiental", "poluicao", "desmatamento")),
)

URGENT_TERMS = ("agora", "urgente", "neste momento", "ao vivo", "acaba de", "interditado", "desaparecido", "desaparecida", "alerta", "evacuacao", "emergencia")
ROUTINE_POLITICS = ("reuniao", "agenda", "visita", "participa", "participou", "discursa", "cerimonia", "solenidade", "inaugura", "inauguracao", "entrega", "recebe", "homenagem")
HIGH_IMPACT_POLITICS = ("prisao", "preso", "investigacao", "operacao", "cassacao", "cassado", "impeachment", "eleicao", "decisao judicial", "escandalo", "denuncia", "afastamento")
CELEBRITY_TERMS = ("famoso", "famosa", "celebridade", "influenciador", "influenciadora", "reality", "bbb", "atriz", "ator", "cantor", "cantora")
NATIONAL_IMPACT = ("gasolina", "inss", "salario minimo", "imposto", "tributo", "lei", "aposentadoria", "beneficio", "energia", "combustivel", "pix", "sus", "eleicao presidencial")
SERVICE_TERMS = TOPIC_RULES[5][1]


def normalize_text(value: Any) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-zA-Z0-9\s-]", " ", value).lower()
    return re.sub(r"\s+", " ", value).strip()


def clean_text(value: str, limit: int | None = None) -> str:
    text = BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(rf"^({PORTALS})\s*[•|\-:]\s*", "", text, flags=re.I)
    text = re.sub(rf"\s*[|\-]\s*({PORTALS})(?:\s*[|\-]\s*Quem sabe, faz conteúdo)?$", "", text, flags=re.I)
    text = re.sub(r"\s*-\s*WSCOM\s*-\s*Quem sabe, faz conteúdo\s*$", "", text, flags=re.I)
    text = re.sub(r"^(Descubra|Clique e veja|Saiba mais sobre)\s+", "", text, flags=re.I)
    text = re.sub(r"\bwhatsApp\b", "WhatsApp", text, flags=re.I)
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip(" ,;:-") + "…"
    return text


def _contains(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def _title(item: dict[str, Any]) -> str:
    return clean_text(item.get("titulo") or item.get("title") or "")


def _summary(item: dict[str, Any]) -> str:
    return clean_text(item.get("resumo") or item.get("summary") or item.get("descricao") or "")


def _published(item: dict[str, Any]) -> Any:
    return item.get("publicado_em") or item.get("published_at") or item.get("data_publicacao")


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif not value:
        return None
    else:
        raw = str(value).strip()
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            dt = None
            for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    break
                except ValueError:
                    continue
            if dt is None:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _tokens(text: str) -> set[str]:
    return {word for word in normalize_text(text).split() if len(word) >= 3 and word not in STOPWORDS}


def _sources(item: dict[str, Any]) -> list[dict[str, str]]:
    entries = item.get("fontes") or item.get("links") or []
    result: list[dict[str, str]] = []
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = clean_text(entry.get("nome") or entry.get("fonte") or entry.get("source") or "Fonte")
            link = clean_text(entry.get("link") or entry.get("url") or "")
            if link:
                result.append({"nome": name, "link": link})
    if not result:
        link = clean_text(item.get("link") or item.get("url") or "")
        if link:
            result.append({"nome": clean_text(item.get("fonte") or item.get("source") or "Fonte"), "link": link})
    return result


def _canonical_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = re.sub(r"/+$", "", parsed.path.lower())
    return f"{host}{path}"


def infer_editoria(url: str, title: str = "", summary: str = "") -> str:
    path = normalize_text(urlparse(url).path)
    text = normalize_text(f"{title} {summary}")
    if any(k in text for k in ("acidente", "atropel", "colisao", "capot", "rodovia", "transito")):
        return "Trânsito"
    if any(k in text for k in ("homicidio", "assassin", "feminicidio", "estupro", "tiroteio", "trafico", "preso", "presa", "prisao", "crime", "golpe", "fraude", "arma", "drogas", "mandado", "foragid", "roubo", "furto", "morre", "morte")):
        return "Segurança"
    if _contains(text, SERVICE_TERMS) or any(k in text for k in ("fgts", "bolsa familia", "previsao do tempo", "gratuita", "gratuito")):
        return "Serviço"
    if any(k in text for k in ("hospital", "saude", "doenca", "surto", "medicamento")):
        return "Saúde"
    if any(k in text for k in ("escola", "educacao", "universidade", "enem", "professor", "aluno")):
        return "Educação"
    if any(k in text for k in ("emprego", "economia", "salario", "preco", "gasolina", "inss", "imposto")):
        return "Economia"
    if any(k in path or k in text for k in ("esporte", "futebol", "botafogo pb", "treze", "campinense")):
        return "Esportes"
    if any(k in text for k in ("justica", "tribunal", "ministerio publico", "mppb", "juiz", "processo")):
        return "Justiça"
    if any(k in text for k in ("prefeito", "governador", "deputado", "senador", "eleicao", "partido", "assembleia", "camara municipal")):
        return "Política"
    return "Geral"


def is_excluded_content(url: str, title: str = "", summary: str = "") -> bool:
    path = urlparse(url).path.lower()
    text = normalize_text(f"{title} {summary}")
    blocked_path = ("/espaco-opiniao/", "/opiniao-e-blogs/", "/opiniao/", "/blogs/", "/colunas/", "/colunistas/", "/ao-vivo", "/blog/", "/artigo/")
    if any(token in path for token in blocked_path):
        return True
    return any(token in text for token in ("por janguie diniz", "por cid gadelha", "quem sabe faz conteudo fique informado"))


def editorial_priority(item: dict[str, Any], now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    title, summary = _title(item), _summary(item)
    text = normalize_text(f"{title} {summary} {item.get('editoria_interna', '')}")
    score = 0.0

    for weight, terms in LOCATION_RULES:
        if _contains(text, terms):
            score += weight
            break
    for weight, terms in TOPIC_RULES:
        if _contains(text, terms):
            score += weight
            break
    if _contains(text, URGENT_TERMS):
        score += 28

    is_politics = _contains(text, ("prefeito", "governador", "deputado", "senador", "vereador", "politica", "assembleia", "camara municipal"))
    if is_politics:
        if _contains(text, HIGH_IMPACT_POLITICS):
            score += 48
        elif _contains(text, ROUTINE_POLITICS):
            score -= 38
        else:
            score -= 16

    is_service = _contains(text, SERVICE_TERMS)
    if not is_service and _contains(text, ROUTINE_POLITICS):
        score -= 30
    if _contains(text, CELEBRITY_TERMS) and not _contains(text, ("morre", "morte", "prisao", "preso", "escandalo nacional")):
        score -= 44

    has_paraiba = _contains(text, ("paraiba", "paraibano", "paraibana", "joao pessoa", "campina grande", "bayeux", "cabedelo", "santa rita"))
    if _contains(text, ("brasil", "nacional", "brasileiro", "brasileira")) and not has_paraiba and not _contains(text, NATIONAL_IMPACT):
        score -= 32
    if _contains(text, ("internacional", "mundo", "exterior", "estados unidos", "europa", "asia")) and not has_paraiba:
        score -= 58

    published = _parse_datetime(_published(item))
    if published:
        age_hours = max(0.0, (now - published).total_seconds() / 3600)
        score += max(0.0, 34.0 - age_hours * 1.4)
    else:
        score += 4

    score += min(12.0, len(_tokens(title)) * 0.8)
    if len(title) < 25:
        score -= 4
    return round(score, 2)


def calculate_relevance(title: str, summary: str, editoria: str, published_at: Any) -> float:
    """Compatibilidade com o coletor atual."""
    return editorial_priority({"titulo": title, "resumo": summary, "editoria_interna": editoria, "publicado_em": published_at})


def _same_story(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_sources, right_sources = _sources(left), _sources(right)
    left_urls = {_canonical_url(s["link"]) for s in left_sources}
    right_urls = {_canonical_url(s["link"]) for s in right_sources}
    if left_urls & right_urls:
        return True

    lt, rt = _title(left), _title(right)
    if not lt or not rt:
        return False
    ln, rn = normalize_text(lt), normalize_text(rt)
    ratio = SequenceMatcher(None, ln, rn).ratio()
    lw, rw = _tokens(lt), _tokens(rt)
    if not lw or not rw:
        return ratio >= 0.88

    common = lw & rw
    jaccard = len(common) / max(1, len(lw | rw))
    containment = len(common) / max(1, min(len(lw), len(rw)))
    left_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", ln))
    right_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?\b", rn))
    if left_numbers and right_numbers and left_numbers.isdisjoint(right_numbers) and ratio < 0.9:
        return False

    left_actions = {term for _, terms in TOPIC_RULES for term in terms if term in ln}
    right_actions = {term for _, terms in TOPIC_RULES for term in terms if term in rn}
    action_match = bool(left_actions & right_actions)
    return ratio >= 0.82 or (jaccard >= 0.55 and containment >= 0.70) or (containment >= 0.82 and len(common) >= 4) or (action_match and containment >= 0.65 and len(common) >= 3)


def _quality(item: dict[str, Any]) -> tuple[float, int, int, float]:
    published = _parse_datetime(_published(item))
    return (editorial_priority(item), len(_tokens(_title(item))), len(_summary(item)), published.timestamp() if published else 0.0)


def _merge_cluster(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    primary = deepcopy(max(cluster, key=_quality))
    best_title = max(cluster, key=lambda item: (len(_tokens(_title(item))), len(_title(item))))
    valid_summaries = [item for item in cluster if _summary(item) and _summary(item) != "Resumo não disponível na fonte."]
    best_summary = max(valid_summaries, key=lambda item: len(_summary(item))) if valid_summaries else primary

    sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in sorted(cluster, key=_quality, reverse=True):
        for source in _sources(item):
            canonical = _canonical_url(source["link"])
            if not canonical or canonical in seen_urls:
                continue
            seen_urls.add(canonical)
            sources.append(source)

    dated = [(item, _parse_datetime(_published(item))) for item in cluster]
    dated = [(item, dt) for item, dt in dated if dt]
    newest_value = _published(max(dated, key=lambda pair: pair[1])[0]) if dated else None

    return {
        "titulo": _title(best_title),
        "resumo": _summary(best_summary) or "Resumo não disponível na fonte.",
        "publicado_em": newest_value,
        "fontes": sources,
        "prioridade_editorial": max(editorial_priority(item) for item in cluster),
    }


def consolidate_and_rank(news: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    valid = [item for item in (news or []) if isinstance(item, dict) and _title(item)]
    clusters: list[list[dict[str, Any]]] = []
    for item in sorted(valid, key=_quality, reverse=True):
        cluster = next((group for group in clusters if any(_same_story(item, existing) for existing in group)), None)
        if cluster is None:
            clusters.append([item])
        else:
            cluster.append(item)

    consolidated = [_merge_cluster(cluster) for cluster in clusters]
    consolidated.sort(key=lambda item: (item["prioridade_editorial"], _parse_datetime(item.get("publicado_em")) or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    return consolidated
