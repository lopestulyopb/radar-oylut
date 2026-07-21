import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from .text import normalize_text

EDITORIA_LABELS = {
    "policial": "Segurança", "seguranca": "Segurança", "cotidiano": "Cotidiano",
    "paraiba": "Paraíba", "politica": "Política", "economia": "Economia",
    "emprego": "Serviço", "concursos": "Serviço", "educacao": "Educação",
    "saude": "Saúde", "esporte": "Esportes", "esportes": "Esportes",
    "cultura": "Cultura", "entretenimento": "Entretenimento", "brasil": "Brasil",
    "mundo": "Mundo", "justica": "Justiça", "transito": "Trânsito",
    "noticias": "Geral", "cidades": "Paraíba",
}
EDITORIA_BASE = {"Segurança":56,"Trânsito":52,"Cotidiano":45,"Paraíba":43,"Saúde":48,"Serviço":47,"Economia":39,"Justiça":38,"Educação":42,"Política":35,"Brasil":25,"Mundo":18,"Cultura":14,"Entretenimento":10,"Geral":28,"Esportes":35}
IMPACT_KEYWORDS = {"morre":26,"morte":26,"homicidio":25,"assassin":25,"feminicidio":27,"estupro":27,"tiroteio":24,"sequestro":23,"desaparecid":21,"acidente":19,"atropel":20,"capot":18,"colisao":17,"incendio":19,"explosao":23,"desabamento":24,"alagamento":17,"enchente":20,"chuvas intensas":16,"alerta":11,"interdicao":15,"sem agua":18,"falta de agua":18,"sem energia":17,"apagao":18,"suspende":11,"cancelado":10,"prazo":8,"inscricao":8,"vagas":11,"concurso":11,"emprego":10,"beneficio":9,"hospital":10,"doenca":9,"vacina":10,"surto":18,"golpe":14,"fraude":13,"preso":13,"prisao":13,"operacao":9,"crianca":7,"idoso":6,"mulher":4}


def infer_editoria(url: str, title: str = "", summary: str = "") -> str:
    path = urlparse(url).path.lower(); text = normalize_text(f"{title} {summary}")
    if "policia federal" in text and any(k in text for k in ("eduardo bolsonaro","abandono de cargo","demissao")): return "Política"
    if any(k in text for k in ("acidente","atropel","colisao","capot","trem","rodovia","transito")): return "Trânsito"
    if any(k in text for k in ("homicidio","assassin","feminicidio","estupro","tiroteio","trafico","preso","presa","prisao","crime","criminos","golpe","fraude","falso whatsapp","ameaca","maus tratos","arma","drogas","mandado","foragid","roubo","furto","morre","morte")): return "Segurança"
    if any(k in text for k in ("vaga","emprego","concurso","inscricao","curso","prazo","calendario","vacina","vacinacao","influenza","gripe","alerta","chuva","previsao do tempo","fgts","inss","bolsa familia","abastecimento","direitos","voo cancelado","bagagem extraviada","saude em acao","inclusao escolar","gratuita","gratuito","cotas raciais","reserva de vagas","transporte escolar","acionamento direto da pm","secoes acessiveis")): return "Serviço"
    if "/esporte" in path or any(k in text for k in ("futebol","campeonato","botafogo pb","treze","sousa","serie c","serie d","copa do mundo","volei","olimpica","corrida")): return "Esportes"
    if any(k in text for k in ("justica","tribunal","ministerio publico","mppb","juiz","juiza","reu","reus","processo","denuncia","absolve","acao judicial")): return "Justiça"
    if any(k in text for k in ("prefeito","governador","deputado","senador","eleicao","eleicoes","partido","assembleia","alpb","ldo","tse","tre pb","guia eleitoral")): return "Política"
    for part in (p for p in path.split("/") if p):
        if part in EDITORIA_LABELS: return EDITORIA_LABELS[part]
    return "Geral"


def calculate_relevance(title, summary, editoria, published_at):
    text = normalize_text(f"{title} {summary}"); score = EDITORIA_BASE.get(editoria, 28)
    for keyword, points in IMPACT_KEYWORDS.items():
        if normalize_text(keyword) in text: score += points
    if re.search(r"\b\d+[\.,]?\d*\s*(mil|milhoes|pessoas|cidades|municipios|vagas)\b", text): score += 8
    if any(term in text for term in ("joao pessoa","campina grande","paraiba","bayeux","cabedelo","santa rita")): score += 4
    if published_at:
        age = max(0, (datetime.now(timezone.utc)-published_at).total_seconds()/3600)
        score += 10 if age <= 1 else 8 if age <= 2 else 5 if age <= 6 else 2 if age <= 12 else 0
    return score


def editorial_bucket(item):
    return {"Segurança":0,"Trânsito":0,"Serviço":1,"Saúde":1,"Educação":1,"Economia":1,"Esportes":2,"Política":3,"Justiça":3}.get(item.get("editoria_interna","Geral"),4)
