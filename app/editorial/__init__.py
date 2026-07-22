"""Motor de Prioridade Editorial do Radar Oylut — Etapa 6.1.1b.

Responsabilidades desta etapa:
- calcular prioridade editorial com visão de telejornal local;
- consolidar pautas equivalentes, mesmo quando os títulos usam palavras diferentes;
- filtrar páginas que não são notícias.

Inclui classificação editorial e ordenação Editor-Chefe ou cronológica.
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
    "policia", "policial", "civil", "realiza", "realizou", "caso", "cidade", "estado",
}

# Termos equivalentes são reduzidos a uma raiz comum para melhorar a consolidação.
STEM_REPLACEMENTS = (
    (r"\batropel\w*\b", "atropel"),
    (r"\bprodutor(?:a)?\s+(?:cultural|de\s+eventos?)\b", "produtor_evento"),
    (r"\bhidrometr\w*\b", "hidrometro"),
    (r"\brecepta\w*\b", "receptacao"),
    (r"\bfurt\w*\b", "furto"),
    (r"\bmoedas?\s+falsas?\b", "moeda_falsa"),
    (r"\btrafic\w*\b", "trafico"),
    (r"\bpolui\w*\b", "poluicao"),
    (r"\besgotos?\b", "esgoto"),
    (r"\birregular\w*\b", "irregular"),
    (r"\bprest\w*\s+depoimento\b", "depoimento"),
    (r"\bse\s+apresent\w*\b", "depoimento"),
    (r"\boperac\w*\b", "operacao"),
    (r"\bpris\w*\b", "prisao"),
    (r"\bassalt\w*\b", "assalto"),
    (r"\brefe(?:m|ns)\b", "refem"),
    (r"\bmort[oa]\b|\bmorre\w*\b|\bhomicid\w*\b|\bassassin\w*\b", "morte"),
)

LOCATION_RULES: tuple[tuple[int, tuple[str, ...]], ...] = (
    (120, ("joao pessoa", "capital paraibana")),
    (112, ("cabedelo", "bayeux", "santa rita", "conde", "lucena", "regiao metropolitana")),
    (104, ("campina grande",)),
    (88, ("paraiba", "paraibano", "paraibana", "sertao", "brejo", "cariri", "curimatau", "litoral sul", "litoral norte")),
    (38, ("nordeste",)),
    (12, ("brasil", "nacional", "brasileiro", "brasileira")),
    (0, ("internacional", "mundo", "exterior")),
)

# A ordem importa: o primeiro grupo encontrado define a natureza principal do fato.
TOPIC_RULES: tuple[tuple[int, tuple[str, ...]], ...] = (
    (150, ("morte", "morto a tiros", "tiroteio", "chacina", "feminicidio")),
    (138, ("familia mantida refem", "refem", "sequestro", "assalto", "roubo", "estupro", "violencia domestica", "gasolina na casa")),
    (126, ("acidente", "atropel", "colisao", "capotamento", "desabamento", "incendio", "explosao", "presa as ferragens")),
    (122, ("prisao", "operacao", "mandado", "apreensao", "trafico", "moeda_falsa", "arma", "drogas")),
    (112, ("br 230", "br-230", "transito", "engarrafamento", "interdicao", "bloqueio de via")),
    (108, ("emergencia", "alerta", "chuva forte", "alagamento", "risco", "evacuacao")),
    (100, ("vacinacao", "vacina", "inscricao", "inscricoes", "concurso", "selecao", "vagas", "curso gratuito", "matricula", "castracao gratuita", "bolsa familia", "abastecimento", "falta de agua", "falta de energia", "transporte publico", "entrega de alimentos")),
    (78, ("hospital", "saude", "doenca", "surto", "atendimento", "medicamento")),
    (66, ("escola", "educacao", "universidade", "enem", "professor", "aluno")),
    (58, ("economia", "emprego", "salario", "preco", "gasolina", "inss", "imposto", "beneficio")),
    (44, ("meio ambiente", "ambiental", "poluicao", "esgoto", "desmatamento", "area de preservacao", "obras embargadas")),
    (34, ("esporte", "futebol", "botafogo pb", "treze", "campinense", "cultura", "festival")),
)

URGENT_TERMS = ("agora", "urgente", "neste momento", "acaba de", "interditado", "desaparecido", "desaparecida", "alerta", "evacuacao", "emergencia")
ROUTINE_POLITICS = ("reuniao", "agenda", "visita", "participa", "participou", "acompanha", "acompanhou", "discursa", "cerimonia", "solenidade", "inaugura", "inauguracao", "entrega", "recebe", "homenagem", "destaca", "defende", "ressalta", "legado")
HIGH_IMPACT_POLITICS = ("prisao", "investigacao", "operacao", "cassacao", "cassado", "impeachment", "eleicao", "decisao judicial", "escandalo", "denuncia", "afastamento", "contas irregulares", "tce")
PROMOTIONAL_POLITICS = ("lideranca regional", "capaz de levar demandas", "populacao reconhece", "pre candidato", "pre-candidato", "chapa", "aliados", "definicao do vice")
CELEBRITY_TERMS = ("famoso", "famosa", "celebridade", "influenciador", "influenciadora", "reality", "bbb", "atriz", "ator", "cantor", "cantora", "virginia")
NATIONAL_IMPACT = ("gasolina", "inss", "salario minimo", "imposto", "tributo", "lei", "aposentadoria", "beneficio", "energia", "combustivel", "pix", "sus", "bolsa familia")
SERVICE_TERMS = TOPIC_RULES[6][1]
RETROSPECTIVE_TERMS = ("relembre", "um mes apos", "dois meses apos", "meses apos", "anos apos", "como esta a investigacao", "volta a tv", "retorna a tv", "se emociona com surpresa", "homenagem")
LOW_VALUE_TERMS = ("ao vivo", "clickfm", "opiniao", "artigo", "ranking de clubes", "privilegio digital", "ser offline")
COMMERCIAL_TERMS = ("firma convenio", "garante descontos", "parceria com", "software lider mundial", "unica instituicao", "beneficios exclusivos")


def normalize_text(value: Any) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-zA-Z0-9\s-]", " ", value).lower()
    value = re.sub(r"\s+", " ", value).strip()
    for pattern, replacement in STEM_REPLACEMENTS:
        value = re.sub(pattern, replacement, value)
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


def concise_summary(value: str, title: str = "", limit: int = 235) -> str:
    """Transforma descrições de portal em uma síntese curta, factual e legível."""
    text = clean_text(value)
    if not text:
        return "Resumo não disponível na fonte."

    # Remove aberturas burocráticas e chamadas promocionais sem retirar o fato principal.
    text = re.sub(
        r"^(?:a|o)\s+(?:policia civil|prefeitura|governo|secretaria|ministerio publico federal|mpf|tribunal|justica)"
        r"(?:\s+da paraiba|\s+de [^,.;]+)?(?:,\s*por meio de [^,.;]+)?\s+",
        lambda match: match.group(0).split(',')[0].strip().capitalize() + " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"^(?:descubra|saiba|veja|confira)\s+[^.!?]{0,80}[.!?]\s*", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()

    sentences = re.split(r"(?<=[.!?])\s+", text)
    selected: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        selected.append(sentence)
        candidate = " ".join(selected)
        if len(candidate) >= 125 or len(selected) == 2:
            break

    result = " ".join(selected) or text
    if normalize_text(result) == normalize_text(title):
        result = text
    return clean_text(result, limit)


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
            for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y, %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
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
    if any(k in text for k in ("morte", "feminicidio", "estupro", "tiroteio", "trafico", "prisao", "crime", "golpe", "fraude", "arma", "drogas", "mandado", "foragid", "roubo", "furto", "assalto", "refem")):
        return "Segurança"
    if _contains(text, SERVICE_TERMS) or any(k in text for k in ("fgts", "previsao do tempo", "gratuita", "gratuito")):
        return "Serviço"
    if any(k in text for k in ("hospital", "saude", "doenca", "surto", "medicamento")):
        return "Saúde"
    if any(k in text for k in ("escola", "educacao", "universidade", "enem", "professor", "aluno")):
        return "Educação"
    if any(k in text for k in ("emprego", "economia", "salario", "preco", "gasolina", "inss", "imposto")):
        return "Economia"
    if any(k in path or k in text for k in ("esporte", "futebol", "botafogo pb", "treze", "campinense")):
        return "Esportes"
    if any(k in text for k in ("justica", "tribunal", "ministerio publico", "mppb", "juiz", "processo", "tce")):
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
    if _contains(text, LOW_VALUE_TERMS):
        return True
    return any(token in text for token in ("por janguie diniz", "por cid gadelha", "quem sabe faz conteudo fique informado"))


def editorial_priority(item: dict[str, Any], now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    title, summary = _title(item), _summary(item)
    title_text = normalize_text(title)
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

    if _contains(title_text, URGENT_TERMS):
        score += 28

    # Mortes e crimes graves locais devem abrir antes de pautas leves e institucionais.
    if _contains(text, ("morte", "morto a tiros", "feminicidio", "chacina")):
        score += 44
    if _contains(text, ("refem", "sequestro", "gasolina na casa", "presa as ferragens")):
        score += 34
    if _contains(text, ("vacinacao", "vacina")) and _contains(text, ("toda populacao", "todos os 223 municipios", "paraiba")):
        score += 38

    is_politics = _contains(text, ("prefeito", "governador", "deputado", "senador", "vereador", "politica", "assembleia", "camara municipal", "partido", "chapa"))
    if is_politics:
        if _contains(text, HIGH_IMPACT_POLITICS):
            score += 32
        elif _contains(text, ROUTINE_POLITICS):
            score -= 72
        else:
            score -= 34
    if _contains(text, PROMOTIONAL_POLITICS):
        score -= 64

    is_service = _contains(text, SERVICE_TERMS)
    if not is_service and _contains(text, ROUTINE_POLITICS):
        score -= 34
    if _contains(text, CELEBRITY_TERMS) and not _contains(text, ("morte", "prisao", "escandalo nacional")):
        score -= 62
    if _contains(text, COMMERCIAL_TERMS):
        score -= 72

    # Retrospectivas e retornos não herdam a urgência do fato antigo mencionado no título.
    if _contains(text, RETROSPECTIVE_TERMS):
        score -= 118

    has_paraiba = _contains(text, ("paraiba", "paraibano", "paraibana", "joao pessoa", "campina grande", "bayeux", "cabedelo", "santa rita"))
    if _contains(text, ("brasil", "nacional", "brasileiro", "brasileira")) and not has_paraiba and not _contains(text, NATIONAL_IMPACT):
        score -= 48
    if _contains(text, ("internacional", "mundo", "exterior", "estados unidos", "europa", "asia", "maduro", "trump")) and not has_paraiba:
        score -= 76

    published = _parse_datetime(_published(item))
    if published:
        age_hours = max(0.0, (now - published).total_seconds() / 3600)
        score += max(0.0, 30.0 - age_hours * 1.1)
    else:
        score += 3

    score += min(10.0, len(_tokens(title)) * 0.65)
    if len(title) < 25:
        score -= 4
    return round(score, 2)



CLASS_ORDER = {
    "urgente": 6,
    "muito_relevante": 5,
    "servico": 4,
    "institucional": 3,
    "politica": 2,
    "geral": 1,
}

CLASS_LABELS = {
    "urgente": "Urgente",
    "muito_relevante": "Muito relevante",
    "servico": "Serviço",
    "institucional": "Institucional",
    "politica": "Política",
    "geral": "Geral",
}

CRITICAL_SERVICE_TERMS = (
    "vacinacao", "vacina", "surto", "alerta", "emergencia", "falta de agua",
    "falta de energia", "abastecimento", "interdicao", "bloqueio", "transito",
    "chuva forte", "alagamento", "evacuacao", "entrega de alimentos",
)

OPPORTUNITY_SERVICE_TERMS = (
    "vagas", "selecao", "concurso", "inscricao", "inscricoes", "curso",
    "matricula", "castracao", "premio professor", "desconto", "convenio",
)

INSTITUTIONAL_TERMS = (
    "prefeitura", "governo da paraiba", "governador", "secretaria", "fiep",
    "sindojus", "universidade", "uniesp", "uninassau", "unimed",
)

GRAVE_EVENT_TERMS = (
    "morte", "morto a tiros", "feminicidio", "chacina", "refem", "sequestro",
    "estupro", "assalto", "roubo", "presa as ferragens", "afogamento",
    "resgatam adolescente", "resgate no mar", "incendio", "explosao",
)

HIGH_RELEVANCE_TERMS = (
    "operacao", "prisao", "mandado", "trafico", "moeda_falsa", "arma",
    "drogas", "acidente", "atropel", "colisao", "embargadas", "poluicao",
    "esgoto", "tce", "contas irregulares", "decisao judicial",
)


def classify_editorial(item: dict[str, Any]) -> tuple[str, str, int]:
    """Classifica a pauta antes da ordenação, como uma mesa de edição."""
    title = normalize_text(_title(item))
    text = normalize_text(f"{_title(item)} {_summary(item)} {item.get('editoria_interna', '')}")

    is_retrospective = _contains(text, RETROSPECTIVE_TERMS)
    is_politics = _contains(text, (
        "prefeito", "governador", "deputado", "senador", "vereador", "politica",
        "assembleia", "camara municipal", "partido", "chapa", "eleicoes",
    ))
    high_impact_politics = _contains(text, HIGH_IMPACT_POLITICS)
    routine_institutional = _contains(text, ROUTINE_POLITICS) or _contains(text, COMMERCIAL_TERMS)

    if _contains(text, GRAVE_EVENT_TERMS) and not is_retrospective:
        return "urgente", CLASS_LABELS["urgente"], CLASS_ORDER["urgente"]

    if _contains(text, CRITICAL_SERVICE_TERMS):
        return "muito_relevante", CLASS_LABELS["muito_relevante"], CLASS_ORDER["muito_relevante"]

    if _contains(text, HIGH_RELEVANCE_TERMS) or (is_politics and high_impact_politics):
        return "muito_relevante", CLASS_LABELS["muito_relevante"], CLASS_ORDER["muito_relevante"]

    if _contains(text, OPPORTUNITY_SERVICE_TERMS):
        return "servico", CLASS_LABELS["servico"], CLASS_ORDER["servico"]

    if is_politics:
        if routine_institutional or _contains(text, PROMOTIONAL_POLITICS):
            return "institucional", CLASS_LABELS["institucional"], CLASS_ORDER["institucional"]
        return "politica", CLASS_LABELS["politica"], CLASS_ORDER["politica"]

    if routine_institutional or (_contains(text, INSTITUTIONAL_TERMS) and _contains(text, ("parceria", "acompanha", "destaca", "celebra", "discute"))):
        return "institucional", CLASS_LABELS["institucional"], CLASS_ORDER["institucional"]

    return "geral", CLASS_LABELS["geral"], CLASS_ORDER["geral"]

def calculate_relevance(title: str, summary: str, editoria: str, published_at: Any) -> float:
    return editorial_priority({"titulo": title, "resumo": summary, "editoria_interna": editoria, "publicado_em": published_at})


def _event_tokens(item: dict[str, Any]) -> set[str]:
    # O resumo ajuda a ligar títulos diferentes que descrevem o mesmo fato.
    return _tokens(f"{_title(item)} {_summary(item)}")


def _event_anchors(text: str) -> set[str]:
    anchors = set()
    normalized = normalize_text(text)
    phrases = (
        "produtor_evento", "hidrometro", "moeda_falsa", "mucumagro", "baia da traicao",
        "princesa isabel", "agua branca", "rio", "esgoto", "litoral", "drone",
        "joao pessoa", "campina grande", "bayeux", "cabedelo", "alhandra",
        "tce", "mpf", "prf", "pix", "br 230", "br-230",
    )
    for phrase in phrases:
        if phrase in normalized:
            anchors.add(phrase.replace(" ", "_"))
    anchors.update(re.findall(r"\b(?:r\$\s*)?\d+(?:[.,]\d+)?\s*(?:mil|milhoes?|bilhoes?)?\b", normalized))
    return anchors


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
    lw, rw = _event_tokens(left), _event_tokens(right)
    if not lw or not rw:
        return ratio >= 0.86

    common = lw & rw
    union = lw | rw
    jaccard = len(common) / max(1, len(union))
    containment = len(common) / max(1, min(len(lw), len(rw)))

    la = _event_anchors(f"{lt} {_summary(left)}")
    ra = _event_anchors(f"{rt} {_summary(right)}")
    shared_anchors = la & ra

    # Não une pautas com números incompatíveis, salvo quando há dois fortes marcadores comuns.
    left_numbers = {n for n in re.findall(r"\b\d+(?:[.,]\d+)?\b", ln) if len(n) >= 2}
    right_numbers = {n for n in re.findall(r"\b\d+(?:[.,]\d+)?\b", rn) if len(n) >= 2}
    incompatible_numbers = left_numbers and right_numbers and left_numbers.isdisjoint(right_numbers)
    if incompatible_numbers and len(shared_anchors) < 2 and ratio < 0.90:
        return False

    # Critérios complementares: semelhança textual, sobreposição de evento e âncoras específicas.
    if ratio >= 0.78:
        return True
    if jaccard >= 0.42 and containment >= 0.62 and len(common) >= 4:
        return True
    if containment >= 0.72 and len(common) >= 5:
        return True
    generic_anchors = {"joao_pessoa", "campina_grande", "bayeux", "cabedelo", "alhandra", "rio", "litoral"}
    specific_shared = shared_anchors - generic_anchors
    if specific_shared and containment >= 0.50 and len(common) >= 4:
        return True
    if len(specific_shared) >= 2 and len(common) >= 3:
        return True
    return False


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

    merged = {
        "titulo": _title(best_title),
        "resumo": concise_summary(_summary(best_summary), _title(best_title)),
        "publicado_em": newest_value,
        "fontes": sources,
        "prioridade_editorial": max(editorial_priority(item) for item in cluster),
    }
    class_key, class_label, class_order = classify_editorial(merged)
    merged["classificacao_editorial"] = class_key
    merged["classificacao_label"] = class_label
    merged["classe_ordem"] = class_order
    return merged


def consolidate_and_rank(news: list[dict[str, Any]] | None, order: str = "editor_chefe") -> list[dict[str, Any]]:
    valid = []
    for item in news or []:
        if not isinstance(item, dict) or not _title(item):
            continue
        first_url = (_sources(item) or [{"link": ""}])[0]["link"]
        if is_excluded_content(first_url, _title(item), _summary(item)):
            continue
        valid.append(item)

    clusters: list[list[dict[str, Any]]] = []
    for item in sorted(valid, key=_quality, reverse=True):
        cluster = next((group for group in clusters if any(_same_story(item, existing) for existing in group)), None)
        if cluster is None:
            clusters.append([item])
        else:
            cluster.append(item)

    consolidated = [_merge_cluster(cluster) for cluster in clusters]
    if order == "recentes":
        consolidated.sort(
            key=lambda item: _parse_datetime(item.get("publicado_em")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
    else:
        consolidated.sort(
            key=lambda item: (
                item.get("classe_ordem", 0),
                item["prioridade_editorial"],
                _parse_datetime(item.get("publicado_em")) or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
    return consolidated
