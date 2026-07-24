"""Sprint 8.3: classificação editorial por tema principal.

O módulo substitui apenas a função de classificação do motor original. A
consolidação, a ordenação e a remoção de duplicidades permanecem intactas.
"""
from __future__ import annotations

from typing import Any

from app import editorial as legacy


def _has(text: str, *terms: str) -> bool:
    return any(term in text for term in terms)


def _all(text: str, *terms: str) -> bool:
    return all(term in text for term in terms)


def classify_editorial_v83(item: dict[str, Any]) -> tuple[str, float, list[str]]:
    title = legacy._ascii(legacy._title(item))
    summary = legacy._ascii(legacy._summary(item))
    text = f"{title} {summary}"

    # 1. Política eleitoral e partidária é sempre dominante.
    if _has(
        text,
        "eleicao", "eleitoral", "pre-candidato", "pre-candidata", "pre-candidatura",
        "candidatura", "convencao partidaria", "convencoes partidarias", "convencao eleitoral",
        "partido", "chapa", "vaga de vice", "escolha do vice", "apoio ao governo",
        "apoio ao pp", "intencoes de voto", "pesquisa datafolha", "primeiro turno",
        "1o turno", "deputado federal", "deputado estadual", "assembleia legislativa",
        "alpb", "senado", "presidencia da republica",
    ):
        return "politica", 0.99, ["assunto eleitoral ou partidário dominante"]

    # 2. Justiça: decisão, processo, denúncia formal ou atuação de tribunal/MP.
    judicial_action = _has(
        title,
        "justica", "stf", "stj", "tribunal", "tjp", "trf", "tre", "ministerio publico",
        "mppb", "mpf", "condena", "condenado", "condenada", "absolve", "absolvido",
        "suspende", "decisao", "liminar", "recurso", "denunciado", "denunciada",
        "indiciado", "inquerito civil", "tac", "prisao domiciliar", "acao civil",
    )
    if judicial_action:
        return "justica", 0.98, ["ato judicial ou ministerial no título"]

    # 3. Policial: crime, ocorrência, investigação criminal, prisão ou apreensão.
    if _has(
        title,
        "policia", "preso", "presa", "prende", "prisao", "suspeito", "suspeita",
        "morto", "morta", "mata", "assassinado", "assassinada", "homicidio", "feminicidio",
        "corpo", "raptado", "sequestrado", "sequestro", "espancado", "agredido",
        "drogas", "trafico", "municoes", "municao", "arma", "facção", "faccao",
        "roubo", "assalto", "furto", "crime", "criminosos", "operacao policial",
        "confronto", "tiros", "violencia psicologica", "stalking",
    ):
        return "policial", 0.98, ["ocorrência criminal ou policial dominante"]

    # Mortes acidentais e acidentes também entram no policial no fluxo do Radar.
    if _has(
        title,
        "afogamento", "afogado", "afogada", "acidente", "colisao", "atropelamento",
        "capotamento", "incendio", "explosao", "desabamento", "queda fatal",
    ):
        return "policial", 0.97, ["acidente ou morte acidental dominante"]

    # 4. Saúde antes de Geral, inclusive orientação e prevenção.
    if _has(
        text,
        "saude", "obesidade", "endometriose", "gravidez", "doenca", "vacina", "vacinacao",
        "hospital", "paciente", "medico", "medica", "tratamento", "cirurgia", "terapia",
        "reproducao humana", "infertil", "autismo", "tea nivel",
    ) and not _has(text, "projeto de lei", "assembleia legislativa"):
        return "saude", 0.94, ["tema de saúde, prevenção ou tratamento"]

    # 5. Educação: vagas, seleção, cursos e rotina educacional.
    if _has(
        text,
        "educacao", "escola", "universidade", "faculdade", "estagio", "aluno", "professor",
        "matricula", "enem", "curso gratuito", "cursos gratuitos", "vagas de estágio",
        "vagas de estagio",
    ):
        return "educacao", 0.93, ["tema educacional dominante"]

    # 6. Serviço: alertas, inscrições, consulta, trânsito e informação prática.
    if _has(
        text,
        "inmet", "alerta amarelo", "alerta laranja", "alerta vermelho", "chuvas intensas",
        "acumulado de chuvas", "inscricoes", "inscricao", "veja como participar", "prazo",
        "consulta ao", "calendario de pagamento", "falta de agua", "abastecimento",
        "interdicao", "interdita area", "defesa civil", "procon", "mega-sena", "mega sena",
        "vagas abertas", "selecao com", "transito", "bloqueio de via",
    ):
        return "servico", 0.92, ["informação prática ou alerta ao público"]

    # 7. Economia: dinheiro, preços, impostos, tarifas, mercado e atividade econômica.
    if _has(
        text,
        "economia", "imposto de renda", "restituicao", "gasolina", "etanol", "diesel",
        "preco", "tarifa", "exportacoes", "exportacao", "importacao", "mercado",
        "empresa", "comercio", "industria", "emprego", "salario", "inflacao", "selic",
        "pib", "cagepa", "r$", "milhoes",
    ):
        return "economia", 0.91, ["impacto econômico, tarifário ou de preços"]

    # 8. Esportes.
    if _has(
        text,
        "campeonato", "futebol", "botafogo-pb", "treze", "campinense", "serie c", "cartola fc",
        "atacante", "jogador", "rodada", "time", "clube", "estadual", "ronaldinho gaucho",
    ):
        return "esportes", 0.94, ["tema esportivo dominante"]

    # 9. Cultura e agenda cultural.
    if _has(
        text,
        "cultura", "cultural", "show", "festival", "caminhos do frio", "qual a boa",
        "o que fazer no fim de semana", "musica", "teatro", "cinema", "festa", "gastronomia",
    ):
        return "cultura", 0.92, ["tema cultural ou de entretenimento"]

    # 10. Meio ambiente apenas quando o foco é ambiental, não meteorologia de serviço.
    if _has(
        text,
        "meio ambiente", "ambiental", "desmatamento", "poluicao", "fauna", "flora",
        "rio", "praia", "queimada", "sustentabilidade",
    ):
        return "meio_ambiente", 0.88, ["tema ambiental dominante"]

    # 11. Institucional: atos administrativos sem disputa eleitoral nem decisão judicial.
    if _has(
        text,
        "nomeado", "nomeacao", "conselho deliberativo", "agenda oficial", "ordem de servico",
        "prefeitura inaugura", "governo entrega", "secretaria anuncia", "programa governamental",
    ):
        return "institucional", 0.84, ["ato administrativo ou institucional"]

    # A classificação original só é aceita quando não for Geral e não houver conflito.
    original = legacy._ascii(
        legacy._get(item, "classificacao_editorial", "editoria", "categoria", "category", default="geral")
    ).replace(" ", "_")
    if original == "seguranca":
        original = "policial"
    if original in legacy.EDITORIA_ORDER and original != "geral":
        return original, 0.66, ["classificação original usada como apoio"]

    return "geral", 0.45, ["nenhum tema principal atingiu confiança mínima"]


def install() -> None:
    """Instala o classificador 8.3 no módulo editorial já carregado."""
    legacy.classify_editorial = classify_editorial_v83
