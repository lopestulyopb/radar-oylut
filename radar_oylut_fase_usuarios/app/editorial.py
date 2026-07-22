"""Motor editorial do Radar Oylut — Etapa 6.1.1.

Responsabilidades desta etapa:
1. calcular prioridade editorial;
2. consolidar matérias que tratam da mesma pauta;
3. manter compatibilidade com os formatos já usados pelo coletor e pela interface.

A classificação visual por Urgente, Serviço, Política etc. pertence à Etapa 6.1.2.
"""

from __future__ import annotations

import math
import re
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Iterable
from urllib.parse import urlparse


_STOPWORDS = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos",
    "e", "em", "entre", "é", "na", "nas", "no", "nos", "o", "os", "para",
    "por", "que", "se", "sem", "sob", "sobre", "um", "uma", "uns", "umas",
    "após", "contra", "durante", "nesta", "neste", "novo", "nova",
}

# Pesos geográficos: refletem a rotina de uma produção de telejornal da Paraíba.
_LOCATION_RULES: tuple[tuple[int, tuple[str, ...]], ...] = (
    (100, ("joao pessoa", "capital paraibana")),
    (90, ("cabedelo", "bayuex", "santa rita", "conde", "lucena", "regiao metropolitana")),
    (84, ("campina grande",)),
    (72, ("paraiba", "paraibano", "paraibana", "sertão", "sertao", "brejo", "cariri", "curimatau", "litoral sul", "litoral norte")),
    (38, ("nordeste",)),
    (16, ("brasil", "nacional", "brasileiro", "brasileira")),
    (2, ("internacional", "mundo", "exterior")),
)

# Núcleo editorial. Não são categorias visuais; são sinais para o ranking.
_TOPIC_RULES: tuple[tuple[int, tuple[str, ...]], ...] = (
    (105, ("morte", "morre", "morreu", "homicidio", "assassinato", "feminicidio", "tiroteio", "chacina")),
    (98, ("acidente", "atropelamento", "colisao", "capotamento", "desabamento", "incendio", "explosao")),
    (94, ("prisao", "preso", "presa", "operacao policial", "mandado", "apreensao", "sequestro", "desaparecido", "desaparecida")),
    (88, ("br-230", "br 230", "transito", "engarrafamento", "interdicao", "bloqueio de via")),
    (82, ("emergencia", "alerta", "chuva forte", "alagamento", "risco", "evacuacao")),
    (72, ("vacinacao", "vacina", "inscricao", "inscricoes", "concurso", "selecao", "vagas", "curso gratuito", "matricula", "abastecimento", "falta de agua", "falta de energia", "transporte publico")),
    (62, ("hospital", "saude", "doenca", "surto", "atendimento", "medicamento")),
    (52, ("escola", "educacao", "universidade", "enem", "professor", "aluno")),
    (44, ("economia", "emprego", "salario", "preco", "gasolina", "inss", "imposto", "beneficio")),
    (30, ("esporte", "futebol", "botafogo-pb", "treze", "campinense", "cultura", "festival")),
    (24, ("meio ambiente", "ambiental", "poluicao", "desmatamento")),
)

_URGENT_TERMS = (
    "agora", "urgente", "neste momento", "ao vivo", "acaba de", "interditado",
    "desaparecido", "desaparecida", "alerta", "evacuacao", "emergencia",
)

_ROUTINE_POLITICS = (
    "reuniao", "agenda", "visita", "participa", "participou", "discursa", "cerimonia",
    "solenidade", "inaugura", "inauguracao", "entrega", "recebe", "homenagem",
)

_HIGH_IMPACT_POLITICS = (
    "prisao", "preso", "investigacao", "operacao", "cassacao", "cassado", "impeachment",
    "eleicao", "decisao judicial", "escandalo", "denuncia", "afastamento",
)

_CELEBRITY_TERMS = (
    "famoso", "famosa", "celebridade", "influenciador", "influenciadora", "reality",
    "bbb", "atriz", "ator", "cantor", "cantora",
)

_NATIONAL_IMPACT = (
    "gasolina", "inss", "salario minimo", "imposto", "tributo", "lei", "aposentadoria",
    "beneficio", "energia", "combustivel", "pix", "sus", "eleicao presidencial",
)


def _ascii(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(
        char for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )


def _clean_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _get(item: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _title(item: dict[str, Any]) -> str:
    return _clean_space(_get(item, "titulo", "title", "manchete"))


def _summary(item: dict[str, Any]) -> str:
    return _clean_space(_get(item, "resumo", "summary", "descricao", "description", "snippet"))


def _source(item: dict[str, Any]) -> str:
    return _clean_space(_get(item, "fonte", "source", "portal", "site"))


def _url(item: dict[str, Any]) -> str:
    return _clean_space(_get(item, "url", "link", "href"))


def _published(item: dict[str, Any]) -> Any:
    return _get(item, "publicado_em", "published_at", "data_publicacao", "date", "datetime", "data")


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
            # Formatos comuns em feeds brasileiros.
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


def _tokens(title: str) -> set[str]:
    normalized = re.sub(r"[^a-z0-9\s-]", " ", _ascii(title))
    return {
        token for token in normalized.split()
        if len(token) >= 3 and token not in _STOPWORDS
    }


def _canonical_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = re.sub(r"/+$", "", parsed.path.lower())
    return f"{host}{path}"


def _contains(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def editorial_priority(item: dict[str, Any], now: datetime | None = None) -> float:
    """Calcula uma prioridade editorial estável e explicável."""
    now = now or datetime.now(timezone.utc)
    title = _title(item)
    summary = _summary(item)
    source_text = " ".join((title, summary, _clean_space(_get(item, "editoria", "category", "categoria"))))
    text = _ascii(source_text)

    score = 0.0

    # Localização: aplica apenas o nível geográfico mais específico identificado.
    for weight, terms in _LOCATION_RULES:
        if _contains(text, terms):
            score += weight
            break

    # Natureza da notícia: aplica o sinal editorial dominante.
    for weight, terms in _TOPIC_RULES:
        if _contains(text, terms):
            score += weight
            break

    if _contains(text, _URGENT_TERMS):
        score += 28

    # Política só sobe com fatos de consequência clara.
    is_politics = _contains(text, ("prefeito", "governador", "deputado", "senador", "vereador", "politica", "assembleia", "camara municipal"))
    if is_politics:
        if _contains(text, _HIGH_IMPACT_POLITICS):
            score += 48
        elif _contains(text, _ROUTINE_POLITICS):
            score -= 34
        else:
            score -= 14

    # Institucional protocolar perde espaço; serviço público útil não é penalizado.
    is_service = _contains(text, _TOPIC_RULES[5][1])
    if not is_service and _contains(text, _ROUTINE_POLITICS):
        score -= 28

    if _contains(text, _CELEBRITY_TERMS) and not _contains(text, ("morre", "morte", "prisao", "preso", "escandalo nacional")):
        score -= 42

    # Nacional e internacional só sobem quando há impacto amplo ou ligação local.
    has_paraiba = _contains(text, ("paraiba", "paraibano", "paraibana", "joao pessoa", "campina grande"))
    is_national = _contains(text, ("brasil", "nacional", "brasileiro", "brasileira"))
    is_international = _contains(text, ("internacional", "mundo", "exterior", "estados unidos", "europa", "asia"))
    if is_national and not has_paraiba and not _contains(text, _NATIONAL_IMPACT):
        score -= 30
    if is_international and not has_paraiba:
        score -= 55

    # Atualidade tem efeito gradual, sem atropelar relevância editorial.
    published = _parse_datetime(_published(item))
    if published:
        age_hours = max(0.0, (now - published).total_seconds() / 3600)
        score += max(0.0, 32.0 - (age_hours * 1.35))
    else:
        score += 4

    # Títulos informativos tendem a ser mais úteis para a produção.
    title_tokens = _tokens(title)
    score += min(12.0, len(title_tokens) * 0.8)
    if len(title) < 25:
        score -= 4

    return round(score, 2)


def _same_story(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_url = _canonical_url(_url(left))
    right_url = _canonical_url(_url(right))
    if left_url and right_url and left_url == right_url:
        return True

    left_title = _title(left)
    right_title = _title(right)
    if not left_title or not right_title:
        return False

    left_norm = _ascii(left_title)
    right_norm = _ascii(right_title)
    sequence_ratio = SequenceMatcher(None, left_norm, right_norm).ratio()

    left_tokens = _tokens(left_title)
    right_tokens = _tokens(right_title)
    if not left_tokens or not right_tokens:
        return sequence_ratio >= 0.88

    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    jaccard = intersection / union if union else 0.0
    containment = intersection / min(len(left_tokens), len(right_tokens))

    # Exige coincidência substantiva. Números ajudam a evitar juntar ocorrências diferentes.
    left_numbers = set(re.findall(r"\b\d+\b", left_norm))
    right_numbers = set(re.findall(r"\b\d+\b", right_norm))
    conflicting_numbers = bool(left_numbers and right_numbers and left_numbers.isdisjoint(right_numbers))
    if conflicting_numbers and sequence_ratio < 0.9:
        return False

    return (
        sequence_ratio >= 0.83
        or (jaccard >= 0.58 and containment >= 0.72)
        or (containment >= 0.82 and intersection >= 4)
    )


def _article_quality(item: dict[str, Any]) -> tuple[float, int, int, float]:
    title = _title(item)
    summary = _summary(item)
    published = _parse_datetime(_published(item))
    published_ts = published.timestamp() if published else 0.0
    # Prioriza conteúdo editorialmente forte, depois título/resumo mais informativos e recência.
    return (
        editorial_priority(item),
        min(len(title), 180),
        min(len(summary), 500),
        published_ts,
    )


def _source_entry(item: dict[str, Any]) -> dict[str, str]:
    return {
        "fonte": _source(item) or "Fonte",
        "url": _url(item),
    }


def _merge_cluster(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    primary = deepcopy(max(cluster, key=_article_quality))

    # O melhor título e o melhor resumo podem vir de versões diferentes.
    best_title_item = max(cluster, key=lambda item: (len(_tokens(_title(item))), len(_title(item))))
    best_summary_item = max(cluster, key=lambda item: len(_summary(item)))
    title = _title(best_title_item) or _title(primary)
    summary = _summary(best_summary_item) or _summary(primary)

    sources: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in sorted(cluster, key=_article_quality, reverse=True):
        entry = _source_entry(item)
        key = (_ascii(entry["fonte"]), _canonical_url(entry["url"]))
        if key in seen:
            continue
        seen.add(key)
        sources.append(entry)

    # Mantém os nomes de campos usados hoje e acrescenta aliases seguros.
    primary["titulo"] = title
    primary["title"] = title
    if summary:
        primary["resumo"] = summary
        primary["summary"] = summary

    primary["fontes"] = sources
    primary["links"] = sources
    primary["quantidade_fontes"] = len(sources)
    primary["duplicidades_consolidadas"] = max(0, len(cluster) - 1)
    primary["prioridade_editorial"] = max(editorial_priority(item) for item in cluster)

    if sources:
        primary["fonte"] = sources[0]["fonte"]
        primary["source"] = sources[0]["fonte"]
        primary["url"] = sources[0]["url"]
        primary["link"] = sources[0]["url"]

    # Usa a publicação mais recente conhecida no card consolidado.
    dated = [(item, _parse_datetime(_published(item))) for item in cluster]
    dated = [(item, dt) for item, dt in dated if dt is not None]
    if dated:
        newest_item, _ = max(dated, key=lambda pair: pair[1])
        newest_value = _published(newest_item)
        for key in ("publicado_em", "published_at", "data_publicacao"):
            if key in primary or key == "publicado_em":
                primary[key] = newest_value

    return primary


def consolidate_and_rank(news: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Consolida duplicidades e devolve a lista em prioridade editorial decrescente."""
    valid_news = [item for item in (news or []) if isinstance(item, dict) and _title(item)]
    clusters: list[list[dict[str, Any]]] = []

    # Notícias de maior qualidade tornam-se representantes dos agrupamentos.
    for item in sorted(valid_news, key=_article_quality, reverse=True):
        matching_cluster = None
        for cluster in clusters:
            if any(_same_story(item, existing) for existing in cluster):
                matching_cluster = cluster
                break
        if matching_cluster is None:
            clusters.append([item])
        else:
            matching_cluster.append(item)

    consolidated = [_merge_cluster(cluster) for cluster in clusters]
    consolidated.sort(
        key=lambda item: (
            float(item.get("prioridade_editorial", 0)),
            _parse_datetime(_published(item)) or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return consolidated
