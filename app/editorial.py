"""Prioridade editorial e consolidação de pautas do Radar Oylut.

Etapa 6.1.1:
- substitui a ordenação genérica por prioridade editorial local;
- consolida matérias equivalentes em um único fato;
- preserva todas as fontes encontradas.

A classificação visual em Urgente, Muito Relevante, Serviço etc. fica para a 6.1.2.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any


PARAIBA_TERMS = {
    "paraiba", "pb", "joao pessoa", "campina grande", "cabedelo", "bayeux",
    "santa rita", "conde", "lucena", "alhandra", "caapora", "pitimbu",
    "mamanguape", "guarabira", "sape", "patos", "sousa", "cajazeiras",
    "catole do rocha", "pombal", "pianco", "conceicao", "monteiro",
    "esperanca", "bananeiras", "areia", "solanea", "itabaiana", "pilar",
    "sao bento", "princesa isabel", "quixaba", "sumé", "queimadas",
    "boqueirao", "picui", "arara", "remigio", "itaporanga", "teixeira",
    "serra branca", "rio tinto", "baia da traicao", "pedras de fogo",
    "cruz do espirito santo", "mari", "mulungu", "sao jose dos ramos",
}

METRO_TERMS = {
    "cabedelo", "bayeux", "santa rita", "conde", "lucena", "alhandra",
    "caapora", "pitimbu", "pedras de fogo", "cruz do espirito santo",
}

OUT_OF_STATE_TERMS = {
    "pernambuco", "recife", "olinda", "ceara", "fortaleza", "rio grande do norte",
    "natal", "alagoas", "maceio", "sergipe", "aracaju", "bahia", "salvador",
    "maranhao", "piaui", "teresina", "sao paulo", "rio de janeiro", "minas gerais",
    "distrito federal", "brasilia", "parana", "santa catarina", "rio grande do sul",
}

INTERNATIONAL_TERMS = {
    "eua", "estados unidos", "china", "russia", "ucrania", "israel", "gaza",
    "venezuela", "argentina", "europa", "turquia", "franca", "alemanha",
    "espanha", "italia", "portugal", "mexico", "japao", "coreia", "ira",
}

SECURITY_TERMS = {
    "homicidio", "assassinato", "morte", "morre", "morto", "cadaver", "crime",
    "tiroteio", "baleado", "facada", "agressao", "roubo", "furto", "sequestro",
    "estupro", "violencia", "operacao", "prisao", "preso", "apreensao", "arma",
    "drogas", "trafico", "policia", "foragido", "mandado", "suspeito",
}

ACCIDENT_TERMS = {
    "acidente", "colisao", "capotamento", "atropelamento", "batida", "queda",
    "incendio", "explosao", "desabamento", "afogamento", "resgate", "feridos",
    "vitima", "transito", "br-230", "br 230", "rodovia", "vlt", "trem",
}

SERVICE_TERMS = {
    "vacina", "vacinacao", "concurso", "inscricao", "inscricoes", "curso",
    "cursos", "vagas", "edital", "alerta", "inmet", "previsao", "chuva",
    "abastecimento", "energia", "interrupcao", "bloqueio de rua", "transito",
    "pesquisa de precos", "procon", "campanha", "atendimento", "prazo",
}

HEALTH_TERMS = {
    "saude", "hospital", "samu", "uti", "doenca", "surto", "dengue", "influenza",
    "medicamento", "cirurgia", "paciente", "emergencia", "urgencia",
}

EDUCATION_TERMS = {
    "educacao", "escola", "universidade", "ufpb", "enem", "prouni", "professor",
    "aluno", "estudante", "creche", "matricula", "bolsa de estudo",
}

ECONOMY_TERMS = {
    "preco", "aumento", "reajuste", "tarifa", "gasolina", "diesel", "energia",
    "salario minimo", "inflacao", "imposto", "credito", "emprego", "desemprego",
    "economia", "comercio", "exportacao", "juros", "beneficio", "inss",
}

POLITICS_TERMS = {
    "prefeito", "governador", "presidente", "deputado", "senador", "vereador",
    "partido", "eleicao", "candidato", "camara", "assembleia", "ministro",
    "lula", "bolsonaro", "pl", "pt", "psb", "mdb", "politica",
}

POLITICS_STRONG_TERMS = {
    "cassacao", "prisao", "preso", "operacao", "investigacao", "denuncia",
    "condenacao", "afastamento", "inelegivel", "impeachment", "eleicao",
    "decisao judicial", "mandado", "fraude", "corrupcao",
}

INSTITUTIONAL_TERMS = {
    "inaugura", "inauguracao", "entrega", "entregou", "promove", "realiza",
    "realizou", "participa", "participou", "visita", "visitou", "lanca",
    "lancamento", "solenidade", "programacao especial", "reuniao", "comemora",
}

CELEBRITY_TERMS = {
    "atriz", "ator", "influenciadora", "influenciador", "cantor", "cantora",
    "famoso", "famosa", "celebridade", "novela", "reality", "virginia",
    "neymar", "show", "artista",
}

BROAD_NATIONAL_IMPACT_TERMS = {
    "lei nacional", "nova lei", "salario minimo", "inss", "imposto", "inflacao",
    "gasolina", "diesel", "energia eletrica", "tarifa", "preco dos alimentos",
    "juros", "pix", "aposentadoria", "beneficio", "sus", "vacina", "anvisa",
    "stf", "congresso aprova", "governo federal anuncia", "aumento de preco",
}

URGENT_TERMS = {
    "agora", "urgente", "ao vivo", "neste momento", "desaparecido", "desaparecida",
    "em andamento", "interditado", "interditada", "sem previsao", "alerta vermelho",
}

STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "de", "da", "do", "das", "dos", "e",
    "em", "no", "na", "nos", "nas", "por", "para", "com", "que", "se", "ao",
    "aos", "apos", "sobre", "entre", "novo", "nova", "nesta", "neste", "diz",
    "veja", "video", "paraiba", "pb",
}


def _normalize(value: Any) -> str:
    text = str(value or "").lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _news_text(item: dict[str, Any]) -> str:
    return _normalize(f"{item.get('titulo', '')} {item.get('resumo', '')}")


def _contains_term(text: str, term: str) -> bool:
    # Limites evitam falsos positivos como "conde" dentro de "esconde".
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None


def _contains_any(text: str, terms: set[str]) -> bool:
    return any(_contains_term(text, term) for term in terms)


TOKEN_EQUIVALENTS = {
    "colisao": "acidente", "batida": "acidente", "capotamento": "acidente",
    "ferida": "ferido", "feridas": "ferido", "feridos": "ferido",
    "pessoas": "pessoa", "vitimas": "vitima", "mortos": "morto",
    "prisao": "preso", "prende": "preso", "prendeu": "preso",
    "apreende": "apreensao", "apreendeu": "apreensao",
}
NUMBER_WORDS = {"dois", "duas", "tres", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez"}


def _tokens(title: str) -> set[str]:
    result: set[str] = set()
    for token in _normalize(title).split():
        if len(token) <= 2 or token in STOPWORDS or token in NUMBER_WORDS:
            continue
        token = TOKEN_EQUIVALENTS.get(token, token)
        if token.endswith("s") and len(token) > 5:
            token = token[:-1]
        result.add(token)
    return result


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def _location_score(text: str) -> int:
    if "joao pessoa" in text:
        return 120
    if _contains_any(text, METRO_TERMS):
        return 105
    if "campina grande" in text:
        return 95
    if _contains_any(text, PARAIBA_TERMS):
        return 80
    if _contains_any(text, OUT_OF_STATE_TERMS):
        return 10
    if _contains_any(text, INTERNATIONAL_TERMS):
        return 0
    return 35


def _topic_score(text: str) -> int:
    score = 0
    if _contains_any(text, SECURITY_TERMS):
        score = max(score, 115)
    if _contains_any(text, ACCIDENT_TERMS):
        score = max(score, 110)
    if _contains_any(text, SERVICE_TERMS):
        score = max(score, 78)
    if _contains_any(text, HEALTH_TERMS):
        score = max(score, 70)
    if _contains_any(text, EDUCATION_TERMS):
        score = max(score, 60)
    if _contains_any(text, ECONOMY_TERMS):
        score = max(score, 55)
    if any(term in text for term in ("esporte", "futebol", "cultura", "festival", "cinema", "musica")):
        score = max(score, 38)
    if any(term in text for term in ("meio ambiente", "ambiental", "rio", "poluicao", "desmatamento")):
        score = max(score, 32)
    return score or 20


def _penalty_score(text: str) -> int:
    penalty = 0
    is_service = _contains_any(text, SERVICE_TERMS)
    is_strong_politics = _contains_any(text, POLITICS_STRONG_TERMS)

    if _contains_any(text, POLITICS_TERMS) and not is_strong_politics:
        penalty -= 55
    if _contains_any(text, INSTITUTIONAL_TERMS) and not is_service:
        penalty -= 65
    if _contains_any(text, CELEBRITY_TERMS):
        penalty -= 45
    if _contains_any(text, INTERNATIONAL_TERMS) and not _contains_any(text, BROAD_NATIONAL_IMPACT_TERMS):
        penalty -= 55
    if _contains_any(text, OUT_OF_STATE_TERMS) and not _contains_any(text, PARAIBA_TERMS):
        penalty -= 45
    return penalty


def _freshness_score(item: dict[str, Any]) -> int:
    published = _parse_datetime(item.get("publicado_em"))
    if not published:
        return 0
    now = datetime.now(timezone.utc)
    hours = max(0.0, (now - published.astimezone(timezone.utc)).total_seconds() / 3600)
    if hours <= 0.5:
        return 24
    if hours <= 1:
        return 20
    if hours <= 3:
        return 14
    if hours <= 6:
        return 9
    if hours <= 12:
        return 5
    return 0


def editorial_priority(item: dict[str, Any]) -> int:
    """Calcula prioridade editorial para um telejornal popular da Paraíba."""
    text = _news_text(item)
    score = _location_score(text) + _topic_score(text) + _penalty_score(text)

    if _contains_any(text, URGENT_TERMS):
        score += 30
    if _contains_any(text, POLITICS_STRONG_TERMS):
        score += 45
    if len(item.get("fontes") or []) > 1:
        score += min(18, (len(item["fontes"]) - 1) * 6)
    score += _freshness_score(item)
    return max(0, score)


def _is_relevant_scope(item: dict[str, Any]) -> bool:
    """Remove conteúdo claramente alheio ao foco local, de forma conservadora."""
    text = _news_text(item)
    has_pb = _contains_any(text, PARAIBA_TERMS)
    broad_impact = _contains_any(text, BROAD_NATIONAL_IMPACT_TERMS)
    strong_event = _contains_any(text, SECURITY_TERMS | ACCIDENT_TERMS | POLITICS_STRONG_TERMS)

    if has_pb or broad_impact:
        return True
    if _contains_any(text, INTERNATIONAL_TERMS):
        return strong_event and _contains_any(text, URGENT_TERMS)
    if _contains_any(text, OUT_OF_STATE_TERMS):
        return False
    # Conteúdo nacional sem local explícito só permanece se tiver impacto amplo.
    if any(term in text for term in ("brasil", "nacional", "governo federal", "congresso")):
        return broad_impact
    return True


def _similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    title_a = _normalize(a.get("titulo"))
    title_b = _normalize(b.get("titulo"))
    if not title_a or not title_b:
        return 0.0

    tokens_a = _tokens(title_a)
    tokens_b = _tokens(title_b)
    if not tokens_a or not tokens_b:
        return SequenceMatcher(None, title_a, title_b).ratio()

    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    jaccard = intersection / union if union else 0.0
    containment = intersection / min(len(tokens_a), len(tokens_b))
    sequence = SequenceMatcher(None, title_a, title_b).ratio()

    # Requer sobreposição real de entidades/termos; evita juntar notícias apenas temáticas.
    return max(jaccard, containment * 0.96, sequence * 0.86)


def _same_story(a: dict[str, Any], b: dict[str, Any]) -> bool:
    score = _similarity(a, b)
    if score >= 0.62:
        return True

    # Títulos curtos ou reescritos podem divergir, mas devem compartilhar ao menos
    # três termos relevantes e localização/ator principal.
    ta, tb = _tokens(a.get("titulo", "")), _tokens(b.get("titulo", ""))
    shared = ta & tb
    return len(shared) >= 3 and score >= 0.48


def _source_key(source: dict[str, Any]) -> tuple[str, str]:
    return (_normalize(source.get("nome")), str(source.get("link") or "").strip())


def _merge_sources(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        for source in group or []:
            if not isinstance(source, dict):
                continue
            key = _source_key(source)
            if not key[1] or key in seen:
                continue
            seen.add(key)
            merged.append({"nome": source.get("nome") or "Fonte", "link": source.get("link")})
    return merged


def _content_quality(item: dict[str, Any]) -> tuple[int, int, int]:
    title = str(item.get("titulo") or "").strip()
    summary = str(item.get("resumo") or "").strip()
    # Títulos informativos, não excessivamente longos; resumo mais completo.
    title_score = 100 - abs(min(len(title), 180) - 90)
    return (editorial_priority(item), title_score, min(len(summary), 500))


def _merge_story(base: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    preferred = max((base, candidate), key=_content_quality)
    other = candidate if preferred is base else base
    merged = dict(preferred)

    if len(str(other.get("resumo") or "")) > len(str(merged.get("resumo") or "")):
        merged["resumo"] = other.get("resumo")

    dates = [d for d in (_parse_datetime(base.get("publicado_em")), _parse_datetime(candidate.get("publicado_em"))) if d]
    if dates:
        merged["publicado_em"] = max(dates).isoformat()

    merged["fontes"] = _merge_sources(base.get("fontes") or [], candidate.get("fontes") or [])
    return merged


def consolidate_news(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Consolida duplicidades, filtra escopo e ordena por prioridade editorial."""
    valid = [dict(item) for item in items if isinstance(item, dict) and item.get("titulo")]
    scoped = [item for item in valid if _is_relevant_scope(item)]

    # Processa primeiro as pautas editorialmente mais fortes para que elas virem o card-base.
    scoped.sort(key=editorial_priority, reverse=True)
    consolidated: list[dict[str, Any]] = []

    for item in scoped:
        item["fontes"] = _merge_sources(item.get("fontes") or [])
        match_index = next(
            (index for index, existing in enumerate(consolidated) if _same_story(existing, item)),
            None,
        )
        if match_index is None:
            consolidated.append(item)
        else:
            consolidated[match_index] = _merge_story(consolidated[match_index], item)

    for item in consolidated:
        item["prioridade_editorial"] = editorial_priority(item)
        # Remove o campo antigo do payload, quando existir, sem quebrar outros consumidores.
        item.pop("peso_jornalistico", None)
        item.pop("peso", None)

    consolidated.sort(
        key=lambda item: (
            int(item.get("prioridade_editorial", 0)),
            _parse_datetime(item.get("publicado_em")) or datetime.min.replace(tzinfo=timezone.utc),
        ),
        reverse=True,
    )
    return consolidated
