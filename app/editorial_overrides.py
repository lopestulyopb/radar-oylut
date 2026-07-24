"""Ajustes editoriais pontuais e reversíveis do Radar Oylut."""
from __future__ import annotations

from typing import Any


def _police_pattern_score(title: str, text: str) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []

    weighted_terms = {
        "drogas": 5,
        "trafico de drogas": 6,
        "narcotrafico": 6,
        "desvio de drogas": 7,
        "organizacao criminosa": 6,
        "gaeco": 5,
        "delegado": 3,
        "delegados": 3,
        "agente da policia civil": 3,
        "agentes da policia civil": 3,
        "policia civil": 3,
        "denuncia": 3,
        "denunciado": 3,
        "denunciados": 3,
    }

    for term, weight in weighted_terms.items():
        if term in text:
            score += weight
            signals.append(term)

    # Combinações definem melhor o fato do que palavras isoladas.
    if "denuncia" in title and any(term in text for term in ("drogas", "trafico", "narcotrafico", "desvio de drogas")):
        score += 6
        signals.append("denúncia + drogas")

    if any(term in title for term in ("delegado", "delegados")) and any(
        term in text for term in ("drogas", "trafico", "narcotrafico", "gaeco")
    ):
        score += 5
        signals.append("delegado + crime relacionado a drogas")

    return score, signals


def apply(editorial_module: Any) -> None:
    """Aplica regras complementares sem alterar o motor-base."""
    original_classify = editorial_module.classify_editorial

    def classify_editorial(item: dict[str, Any]):
        title = editorial_module._ascii(editorial_module._title(item))
        summary = editorial_module._ascii(editorial_module._summary(item))
        text = f"{title} {summary}"

        score, signals = _police_pattern_score(title, text)
        if score >= 12:
            return "policial", 0.99, ["combinação policial dominante", *signals[:4]]

        return original_classify(item)

    editorial_module.classify_editorial = classify_editorial
