"""Motor editorial do Radar Oylut.

Responsabilidades:
1. consolidar matérias que tratam do mesmo fato;
2. classificar o fato no backend;
3. calcular prioridade editorial;
4. devolver fontes em ordem alfabética.
"""
from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Iterable
from urllib.parse import urlparse

_STOPWORDS = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos", "e", "em",
    "entre", "na", "nas", "no", "nos", "o", "os", "para", "por", "que", "se", "sem", "sob",
    "sobre", "um", "uma", "uns", "umas", "apos", "contra", "durante", "nesta", "neste", "novo", "nova",
}

_LOCATION_TERMS = (
    "joao pessoa", "campina grande", "santa rita", "cabedelo", "conde", "lucena", "bayeux", "pombal",
    "itaporanga", "sao bento", "brejo", "sertao", "cariri", "paraiba", "gurugi", "tibiri",
)

_EVENT_GROUPS = {
    "homicidio": ("homicidio", "assassinato", "morto a tiros", "morta a tiros", "feminicidio", "chacina"),
    "prisao": ("preso", "presa", "prisao", "mandado de prisao", "capturado", "detido"),
    "operacao": ("operacao", "acao policial", "deflagrou", "mandados"),
    "armas": ("arma", "armas", "municao", "municoes", "venda ilegal de armas"),
    "trafico": ("trafico", "drogas", "entorpecentes"),
    "acidente": (
        "acidente", "colisao", "batida", "capotamento", "atropelamento", "engavetamento",
        "tombamento", "queda", "explosao", "incendio", "afogamento", "naufragio",
        "capota", "capotou", "colide", "colidiu", "bate", "bateu", "atropela", "atropelou",
        "tomba", "tombou", "cai", "caiu", "despenca", "despencou", "explode", "explodiu",
        "pega fogo", "pegou fogo", "afunda", "afundou", "naufraga", "naufragou",
    ),
    "chuva": ("chuvas intensas", "alerta de chuva", "inmet", "alerta amarelo", "alerta laranja"),
    "eleicao": ("eleicao", "eleitoral", "pre-candidatura", "candidato", "vice", "senado", "governo"),
}

EDITORIA_ORDER = {
    "policial": 0, "servico": 1, "saude": 2, "educacao": 3, "economia": 4,
    "justica": 5, "esportes": 6, "cultura": 7, "meio_ambiente": 8,
    "institucional": 9, "geral": 10, "politica": 11,
}

_EXPRESSIONS = {
    "policial": (
        "busca e apreensao", "atos obscenos", "violencia domestica", "tentativa de homicidio",
        "trafico de drogas", "organizacao criminosa", "corpo encontrado", "arma de fogo",
    ),
    "servico": (
        "alerta amarelo", "alerta laranja", "alerta vermelho", "processo seletivo",
        "falta de agua", "interrupcao no abastecimento",
    ),
    "saude": ("plano de saude", "saude publica", "saude mental"),
    "educacao": ("rede estadual", "rede municipal", "ensino superior"),
    "economia": ("imposto de renda", "mercado imobiliario", "construcao civil", "microempreendedor individual"),
    "justica": ("acao civil publica", "ministerio publico", "supremo tribunal", "tribunal de justica"),
    "esportes": ("copa do brasil", "campeonato brasileiro"),
    "cultura": ("festa das neves", "sao joao"),
    "meio_ambiente": ("meio ambiente",),
    "institucional": ("ordem de servico", "agenda oficial"),
    "politica": ("pre-candidato", "pre-candidata", "base aliada", "oposicao"),
}

_EVENTS = {
    "policial": (
        "prende", "prendeu", "preso", "presa", "detido", "detida", "morre", "morreu", "morto", "morta",
        "mata", "matou", "assassina", "assassinou", "rouba", "roubou", "furta", "furtou",
        "assalta", "assaltou", "atropela", "atropelou", "capota", "capotou", "colide", "colidiu",
        "apreende", "apreendeu", "cumpre mandado", "cumpriu mandado", "investiga", "investigou",
        "tomba", "tombou", "bate", "bateu", "cai", "caiu", "despenca", "despencou",
        "explode", "explodiu", "pega fogo", "pegou fogo", "afunda", "afundou", "naufraga", "naufragou",
    ),
    "servico": (
        "abre", "abriu", "prorroga", "prorrogou", "anuncia", "anunciou", "alerta", "alertou",
        "interdita", "interditou", "suspende", "suspendeu", "libera", "liberou",
        "normaliza", "normalizou", "convoca", "convocou", "disponibiliza", "disponibilizou",
    ),
    "saude": (
        "vacina", "vacinou", "interna", "internou", "opera", "operou", "transplanta", "transplantou",
        "diagnostica", "diagnosticou", "confirma", "confirmou", "registra", "registrou", "amplia", "ampliou",
    ),
    "educacao": (
        "matricula", "matriculou", "forma", "formou", "seleciona", "selecionou", "aprova", "aprovou",
        "convoca", "convocou", "oferta", "ofertou",
    ),
    "economia": (
        "gera", "gerou", "cresce", "cresceu", "reduz", "reduziu", "aumenta", "aumentou",
        "cai", "caiu", "investe", "investiu", "restitui", "restituiu", "arrecada", "arrecadou",
    ),
    "justica": (
        "condena", "condenou", "absolve", "absolveu", "autoriza", "autorizou", "determina", "determinou",
        "suspende", "suspendeu", "mantem", "manteve", "julga", "julgou", "nega", "negou",
    ),
    "esportes": (
        "vence", "venceu", "perde", "perdeu", "empata", "empatou", "classifica", "classificou",
        "elimina", "eliminou", "contrata", "contratou",
    ),
    "cultura": (
        "lanca", "lancou", "estreia", "estreou", "apresenta", "apresentou", "realiza", "realizou",
        "celebra", "celebrou",
    ),
    "meio_ambiente": (
        "desmata", "desmatou", "preserva", "preservou", "embarga", "embargou", "resgata", "resgatou",
        "monitora", "monitorou",
    ),
    "institucional": (
        "entrega", "entregou", "inaugura", "inaugurou", "assina", "assinou", "vistoria", "vistoriou",
        "participa", "participou",
    ),
    "politica": (
        "declara", "declarou", "anuncia", "anunciou", "articula", "articulou", "filia", "filiou",
        "rompe", "rompeu", "apoia", "apoiou",
    ),
}

_CONTEXT = {
    "servico": ("vaga", "emprego", "inscricao", "prazo", "abastecimento", "agua", "energia", "transito", "beneficio", "concurso", "inmet"),
    "saude": ("saude", "hospital", "vacina", "vacinacao", "paciente", "doenca", "cirurgia", "medicamento", "sus"),
    "educacao": ("educacao", "escola", "universidade", "faculdade", "enem", "professor", "aluno", "matricula", "curso"),
    "economia": ("economia", "emprego", "empresa", "mei", "imposto", "restituicao", "mercado", "preco", "salario", "turismo"),
    "justica": ("justica", "juiz", "juiza", "tribunal", "stf", "stj", "tjp", "sentenca", "acao", "liminar", "alvara", "inquerito"),
    "esportes": ("futebol", "campeonato", "clube", "jogo", "atleta", "time", "botafogo-pb", "treze", "campinense"),
    "cultura": ("show", "musica", "cantor", "cantora", "filme", "festival", "livro", "teatro", "cultura"),
    "meio_ambiente": ("ambiental", "meio ambiente", "queimada", "poluicao", "rio", "praia", "desmatamento", "fauna", "flora"),
    "institucional": ("prefeitura", "governo", "secretaria", "gestao", "obra", "solenidade", "agenda"),
    "politica": ("eleicao", "eleitoral", "candidato", "candidata", "prefeito", "governador", "deputado", "senador", "vereador", "partido", "chapa"),
}


def _ascii(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _get(item: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _title(item: dict[str, Any]) -> str:
    return _clean(_get(item, "titulo", "title", "manchete"))


def _summary(item: dict[str, Any]) -> str:
    return _clean(_get(item, "resumo", "summary", "descricao", "description", "snippet"))


def _source(item: dict[str, Any]) -> str:
    return _clean(_get(item, "fonte", "source", "portal", "site"))


def _url(item: dict[str, Any]) -> str:
    return _clean(_get(item, "url", "link", "href"))


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


def _tokens(value: str) -> set[str]:
    normalized = re.sub(r"[^a-z0-9\s-]", " ", _ascii(value))
    return {t for t in normalized.split() if len(t) >= 3 and t not in _STOPWORDS}


def _canonical_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = re.sub(r"/+$", "", parsed.path.lower())
    return f"{host}{path}"


def _contains(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def _locations(text: str) -> set[str]:
    return {term for term in _LOCATION_TERMS if term in text}


def _event_signals(text: str) -> set[str]:
    return {name for name, terms in _EVENT_GROUPS.items() if _contains(text, terms)}


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\b\d+\b", text))


def classify_editorial(item: dict[str, Any]) -> tuple[str, float, list[str]]:
    title = _ascii(_title(item))
    summary = _ascii(_summary(item))
    text = f"{title} {summary}"

    # Expressões específicas prevalecem sobre palavras isoladas.
    for category in ("policial", "justica", "servico", "saude", "educacao", "economia", "esportes", "cultura", "meio_ambiente", "institucional", "politica"):
        if _contains(title, _EXPRESSIONS[category]):
            return category, 0.98, ["expressão editorial no título"]

    # O acontecimento principal do título prevalece sobre a profissão ou personagem.
    if _contains(title, _EVENTS["policial"]) or _contains(title, (
        "policia", "prisao", "suspeito", "suspeita", "foragido", "foragida", "homicidio",
        "feminicidio", "assassinato", "assalto", "roubo", "furto", "trafico", "faccao",
        "arma", "municao", "sequestro", "estupro", "crime", "acidente", "colisao", "batida",
        "atropelamento", "capotamento", "engavetamento", "tombamento", "afogamento", "naufragio",
        "incendio", "explosao",
    )):
        return "policial", 0.97, ["ocorrência policial ou acidente no título"]

    if _contains(title, _EVENTS["justica"]) and _contains(text, _CONTEXT["justica"]):
        return "justica", 0.95, ["evento judicial no título"]
    if _contains(title, _EVENTS["esportes"]) and _contains(text, _CONTEXT["esportes"]):
        return "esportes", 0.94, ["evento esportivo no título"]
    if _contains(title, _EVENTS["servico"]) and _contains(text, _CONTEXT["servico"]):
        return "servico", 0.93, ["evento de serviço no título"]
    if _contains(title, _EVENTS["saude"]) and _contains(text, _CONTEXT["saude"]):
        return "saude", 0.92, ["evento de saúde no título"]
    if _contains(title, _EVENTS["educacao"]) and _contains(text, _CONTEXT["educacao"]):
        return "educacao", 0.91, ["evento educacional no título"]
    if _contains(title, _EVENTS["economia"]) and _contains(text, _CONTEXT["economia"]):
        return "economia", 0.90, ["evento econômico no título"]
    if _contains(title, _EVENTS["cultura"]) and _contains(text, _CONTEXT["cultura"]):
        return "cultura", 0.89, ["evento cultural no título"]
    if _contains(title, _EVENTS["meio_ambiente"]) and _contains(text, _CONTEXT["meio_ambiente"]):
        return "meio_ambiente", 0.88, ["evento ambiental no título"]
    if _contains(title, _EVENTS["institucional"]) and _contains(text, _CONTEXT["institucional"]):
        return "institucional", 0.87, ["evento institucional no título"]
    if _contains(title, _EVENTS["politica"]) and _contains(text, _CONTEXT["politica"]):
        return "politica", 0.86, ["evento político no título"]

    # Temas de apoio, usados apenas quando nenhum evento dominante foi identificado.
    for category in ("justica", "esportes", "servico", "saude", "educacao", "economia", "cultura", "meio_ambiente", "institucional", "politica"):
        if _contains(text, _CONTEXT[category]):
            return category, 0.78, ["tema editorial predominante"]

    if _contains(text, ("anuario", "ranking", "dados mostram", "registra alta", "aumento de", "taxa de", "indice de")):
        if _contains(text, ("violencia", "violenta", "violento", "criminalidade", "roubo", "furto", "homicidio", "assassinato", "seguranca publica")):
            return "policial", 0.91, ["levantamento sobre criminalidade"]
        return "geral", 0.82, ["levantamento estatístico"]

    original = _ascii(_get(item, "classificacao_editorial", "editoria", "categoria", "category", default="geral")).replace(" ", "_")
    if original == "seguranca":
        original = "policial"
    if original in EDITORIA_ORDER:
        return original, 0.62, ["classificação original usada como apoio"]
    return "geral", 0.50, ["sem sinal editorial dominante"]


def editorial_priority(item: dict[str, Any], now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    text = _ascii(f"{_title(item)} {_summary(item)}")
    category, _, _ = classify_editorial(item)
    base = {
        "policial": 100, "servico": 72, "saude": 62, "educacao": 56, "economia": 48,
        "esportes": 35, "cultura": 30, "meio_ambiente": 28, "politica": 24,
        "justica": 22, "institucional": 10, "geral": 18,
    }[category]
    if _contains(text, ("joao pessoa", "santa rita", "bayeux", "cabedelo", "conde")):
        base += 35
    elif _contains(text, ("campina grande", "paraiba", "brejo", "sertao")):
        base += 22
    if _contains(text, ("morte", "homicidio", "feminicidio", "chacina")):
        base += 34
    if _contains(text, ("urgente", "agora", "alerta", "interditado", "desaparecido")):
        base += 18
    published = _parse_datetime(_published(item))
    if published:
        age = max(0.0, (now - published).total_seconds() / 3600)
        base += max(0.0, 24.0 - age)
    return round(float(base), 2)


def _same_story(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_url, right_url = _canonical_url(_url(left)), _canonical_url(_url(right))
    if left_url and right_url and left_url == right_url:
        return True

    lt, rt = _ascii(_title(left)), _ascii(_title(right))
    ls, rs = _ascii(_summary(left)), _ascii(_summary(right))
    if not lt or not rt:
        return False

    ldt, rdt = _parse_datetime(_published(left)), _parse_datetime(_published(right))
    if ldt and rdt and abs((ldt - rdt).total_seconds()) > 36 * 3600:
        return False

    lnums, rnums = _numbers(f"{lt} {ls}"), _numbers(f"{rt} {rs}")
    if lnums and rnums and lnums.isdisjoint(rnums):
        common_tokens = _tokens(lt) & _tokens(rt)
        if len(common_tokens) < 5:
            return False

    llocations, rlocations = _locations(f"{lt} {ls}"), _locations(f"{rt} {rs}")
    if llocations and rlocations and llocations.isdisjoint(rlocations):
        return False

    levents, revents = _event_signals(f"{lt} {ls}"), _event_signals(f"{rt} {rs}")
    if levents and revents and levents.isdisjoint(revents):
        return False

    ltok, rtok = _tokens(lt), _tokens(rt)
    intersection = len(ltok & rtok)
    union = len(ltok | rtok)
    jaccard = intersection / union if union else 0.0
    containment = intersection / min(len(ltok), len(rtok)) if ltok and rtok else 0.0
    sequence = SequenceMatcher(None, lt, rt).ratio()

    summary_tokens_left = _tokens(ls)
    summary_tokens_right = _tokens(rs)
    summary_overlap = len(summary_tokens_left & summary_tokens_right) / max(1, min(len(summary_tokens_left), len(summary_tokens_right)))

    score = 0
    if sequence >= 0.72:
        score += 35
    if jaccard >= 0.42:
        score += 30
    if containment >= 0.66:
        score += 25
    if llocations & rlocations:
        score += 18
    if levents & revents:
        score += 18
    if lnums & rnums:
        score += 12
    if summary_overlap >= 0.38:
        score += 22

    return score >= 70


def _article_quality(item: dict[str, Any]) -> tuple[int, int, float]:
    title = _title(item)
    summary = _summary(item)
    published = _parse_datetime(_published(item))
    return (len(_tokens(title)), len(summary), published.timestamp() if published else 0.0)


def _source_entry(item: dict[str, Any]) -> dict[str, str]:
    name = _source(item) or "Fonte"
    url = _url(item)
    return {"nome": name, "link": url, "fonte": name, "url": url}


def _merge_cluster(cluster: list[dict[str, Any]]) -> dict[str, Any]:
    primary = deepcopy(max(cluster, key=_article_quality))
    best_title_item = max(cluster, key=lambda item: (len(_tokens(_title(item))), len(_title(item))))
    best_summary_item = max(cluster, key=lambda item: len(_summary(item)))
    title = _title(best_title_item) or _title(primary)
    summary = _summary(best_summary_item) or _summary(primary)

    sources: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in cluster:
        entry = _source_entry(item)
        key = (_ascii(entry["nome"]), _canonical_url(entry["link"]))
        if key in seen:
            continue
        seen.add(key)
        sources.append(entry)
    sources.sort(key=lambda entry: _ascii(entry["nome"]))

    primary["titulo"] = primary["title"] = title
    primary["resumo"] = primary["summary"] = summary
    primary["fontes"] = primary["links"] = sources
    primary["quantidade_fontes"] = len(sources)
    primary["duplicidades_consolidadas"] = max(0, len(cluster) - 1)

    dated = [(item, _parse_datetime(_published(item))) for item in cluster]
    dated = [(item, dt) for item, dt in dated if dt is not None]
    if dated:
        oldest_item, _ = min(dated, key=lambda pair: pair[1])
        newest_item, _ = max(dated, key=lambda pair: pair[1])
        primary["primeira_publicacao_em"] = _published(oldest_item)
        primary["ultima_publicacao_em"] = _published(newest_item)
        primary["publicado_em"] = _published(newest_item)

    category, confidence, reasons = classify_editorial(primary)
    primary["classificacao_editorial"] = category
    primary["editoria"] = category
    primary["confianca_classificacao"] = confidence
    primary["motivos_classificacao"] = reasons
    primary["prioridade_editorial"] = max(editorial_priority(item) for item in cluster)

    if sources:
        primary["fonte"] = primary["source"] = sources[0]["nome"]
        primary["url"] = primary["link"] = sources[0]["link"]
    return primary


def consolidate_and_rank(news: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    valid = [item for item in (news or []) if isinstance(item, dict) and _title(item)]
    clusters: list[list[dict[str, Any]]] = []
    for item in sorted(valid, key=_article_quality, reverse=True):
        target = next((cluster for cluster in clusters if any(_same_story(item, existing) for existing in cluster)), None)
        if target is None:
            clusters.append([item])
        else:
            target.append(item)

    consolidated = [_merge_cluster(cluster) for cluster in clusters]
    consolidated.sort(key=lambda item: (
        EDITORIA_ORDER.get(str(item.get("classificacao_editorial", "geral")), 99),
        -float(item.get("prioridade_editorial", 0)),
        -((_parse_datetime(_published(item)) or datetime.min.replace(tzinfo=timezone.utc)).timestamp()),
    ))
    return consolidated
