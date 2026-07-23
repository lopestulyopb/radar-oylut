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
    "acidente": ("acidente", "colisao", "batida", "capotamento", "atropelamento"),
    "chuva": ("chuvas intensas", "alerta de chuva", "inmet", "alerta amarelo", "alerta laranja"),
    "eleicao": ("eleicao", "eleitoral", "pre-candidatura", "candidato", "vice", "senado", "governo"),
}

EDITORIA_ORDER = {
    "policial": 0, "servico": 1, "saude": 2, "educacao": 3, "economia": 4,
    "esportes": 5, "cultura": 6, "meio_ambiente": 7, "politica": 8,
    "justica": 9, "institucional": 10, "geral": 11,
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
    reasons: list[str] = []

    def hit(terms: Iterable[str], where: str = text) -> bool:
        return _contains(where, terms)

    # Ação principal no título prevalece sobre temas secundários no resumo.
    if hit(("justica eleitoral", "stf", "stj", "tribunal", "juiz", "juiza", "sentenca", "absolve", "absolveu", "condena", "condenou", "determina", "decisao judicial", "recurso", "pericia"), title):
        reasons.append("ação judicial no título")
        return "justica", 0.94, reasons
    if hit(("homenageia", "homenagem", "voto de aplausos", "medalha", "titulo de cidadania", "reconhecimento institucional", "solenidade"), title):
        reasons.append("homenagem ou ato institucional no título")
        return "institucional", 0.93, reasons
    if hit(("campeonato", "partida", "jogo", "times", "torneio", "serie c", "serie d", "segunda divisao", "paraibano", "botafogo-pb", "treze", "campinense"), text):
        reasons.append("competição esportiva")
        return "esportes", 0.92, reasons
    if hit(("policia", "prisao", "preso", "presa", "homicidio", "feminicidio", "assalto", "roubo", "furto", "trafico", "faccao", "arma", "municao", "sequestro", "estupro", "acidente", "colisao", "atropelamento", "capotamento", "incendio", "explosao"), title):
        reasons.append("ocorrência policial ou acidente no título")
        return "policial", 0.94, reasons
    if hit(("inmet", "alerta de chuva", "chuvas intensas", "alerta amarelo", "alerta laranja", "bolsa familia", "calendario de pagamento", "refis", "renegociacao", "inscricoes", "prazo", "auxilio-doenca", "beneficio do inss"), text):
        reasons.append("informação de utilidade pública")
        return "servico", 0.91, reasons
    if hit(("estagio", "estudante", "escola", "educacao", "universidade", "faculdade", "enem", "professor", "aluno", "matricula"), text):
        reasons.append("tema educacional")
        return "educacao", 0.88, reasons
    if hit(("plano de saude", "tea", "autismo", "vacina", "vacinacao", "hospital", "doenca", "medicamento", "atendimento medico"), text):
        reasons.append("tema de saúde")
        return "saude", 0.87, reasons
    if hit(("pre-candidatura", "pre-candidato", "pre-candidata", "candidato", "candidata", "chapa", "vice", "apoio", "convencao", "partido", "eleicoes", "senado", "governo da paraiba"), title):
        reasons.append("articulação eleitoral no título")
        return "politica", 0.91, reasons
    if hit(("deputado", "senador", "vereador", "prefeito", "governador", "assembleia legislativa", "camara municipal", "ldo", "emendas"), text):
        reasons.append("atividade político-parlamentar")
        return "politica", 0.84, reasons
    if hit(("cinema", "cineasta", "festival", "show", "musica", "teatro", "livro", "exposicao", "cultura"), text):
        reasons.append("tema cultural")
        return "cultura", 0.86, reasons
    if hit(("meio ambiente", "ambiental", "poluicao", "esgoto", "desmatamento", "fauna", "flora"), text):
        reasons.append("tema ambiental")
        return "meio_ambiente", 0.84, reasons
    if hit(("economia", "emprego", "salario", "preco", "gasolina", "imposto", "credito", "comercio", "industria", "construcao civil"), text):
        reasons.append("tema econômico")
        return "economia", 0.82, reasons
    if hit(("morre", "morreu", "falecimento", "luto"), title):
        reasons.append("morte de personalidade sem violência")
        return "geral", 0.85, reasons
    if hit(("anuario", "ranking", "dados mostram", "registra alta", "aumento de", "taxa de", "indice de"), text):
        reasons.append("levantamento estatístico")
        return "geral", 0.82, reasons

    original = _ascii(_get(item, "classificacao_editorial", "editoria", "categoria", "category", default="geral")).replace(" ", "_")
    if original == "seguranca":
        original = "policial"
    if original in EDITORIA_ORDER:
        reasons.append("classificação original usada como apoio")
        return original, 0.62, reasons
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
    # Números conflitantes reduzem bastante a chance de ser o mesmo fato.
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
    if sequence >= 0.72: score += 35
    if jaccard >= 0.42: score += 30
    if containment >= 0.66: score += 25
    if llocations & rlocations: score += 18
    if levents & revents: score += 18
    if lnums & rnums: score += 12
    if summary_overlap >= 0.38: score += 22

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
        oldest_item, oldest_dt = min(dated, key=lambda pair: pair[1])
        newest_item, newest_dt = max(dated, key=lambda pair: pair[1])
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
