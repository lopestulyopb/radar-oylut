from app.models import Article, TVAnalysis
from app.text import normalize

KEYWORDS = {
    "Polícia": ["preso", "prisao", "homicidio", "tiro", "assalto", "operacao", "apreensao", "desaparecido"],
    "Cidade": ["transito", "agua", "energia", "obra", "bairro", "chuva", "onibus", "interdicao"],
    "Saúde": ["saude", "hospital", "doenca", "vacina", "atendimento", "surto"],
    "Política": ["prefeitura", "governo", "assembleia", "camara", "lei", "eleicao"],
    "Economia": ["emprego", "preco", "comercio", "salario", "economia", "vaga"],
    "Educação": ["escola", "universidade", "enem", "fies", "prouni", "educacao"],
}

VISUAL_WORDS = ["incendio", "acidente", "chuva", "alagamento", "operacao", "obra", "protesto", "fila", "apreensao"]
SERVICE_WORDS = ["prazo", "inscricao", "interdicao", "abastecimento", "vacina", "vaga", "atendimento", "alerta"]
IMPACT_WORDS = ["joao pessoa", "paraiba", "moradores", "familias", "usuarios", "motoristas", "estudantes"]


def classify(text: str) -> str:
    normalized = normalize(text)
    scores = {section: sum(word in normalized for word in words) for section, words in KEYWORDS.items()}
    return max(scores, key=scores.get) if max(scores.values(), default=0) else "Geral"


def analyze_tv(article_group: list[Article]) -> TVAnalysis:
    text = normalize(" ".join(a.title + " " + (a.summary or "") for a in article_group))
    score = 25
    reasons: list[str] = []
    visuals: list[str] = []
    if any(word in text for word in VISUAL_WORDS):
        score += 25; reasons.append("Possibilidade clara de imagens"); visuals.append("Imagens do local ou do acontecimento")
    if any(word in text for word in SERVICE_WORDS):
        score += 20; reasons.append("Contém informação de serviço")
    if any(word in text for word in IMPACT_WORDS):
        score += 15; reasons.append("Impacto local ou coletivo")
    if len(article_group) > 1:
        score += 10; reasons.append("Assunto repercutido por mais de uma fonte")
    score = min(score, 100)
    potential = "alto" if score >= 70 else "médio" if score >= 45 else "baixo"
    section = classify(text)
    source_map = {
        "Polícia": ["Polícia Civil", "Polícia Militar", "vítimas ou testemunhas"],
        "Saúde": ["Secretaria de Saúde", "especialista", "usuário do serviço"],
        "Cidade": ["órgão responsável", "moradores afetados", "especialista técnico"],
        "Política": ["gestor responsável", "oposição", "população afetada"],
        "Educação": ["Secretaria de Educação", "instituição", "estudante ou responsável"],
        "Economia": ["órgão responsável", "especialista", "trabalhador ou consumidor"],
    }
    return TVAnalysis(
        section=section, tv_score=score, tv_potential=potential,
        reasons=reasons or ["Tema precisa de confirmação e desenvolvimento"],
        suggested_sources=source_map.get(section, ["fonte oficial", "especialista", "personagem afetado"]),
        suggested_character="Pessoa diretamente afetada pelo fato",
        visual_needs=visuals or ["Verificar disponibilidade de imagens e local para gravação"],
        next_steps=["Abrir e conferir as matérias originais", "Confirmar dados com fonte oficial", "Buscar personagem e imagens", "Definir possibilidade de vivo ou VT"],
    )
