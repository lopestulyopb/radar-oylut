import re
from difflib import SequenceMatcher
from .categories import editorial_bucket, infer_editoria
from .text import normalize_text

STOPWORDS={"a","o","as","os","de","da","do","das","dos","e","em","no","na","nos","nas","um","uma","para","por","com","que","se","ao","aos","apos","sobre","contra","sao","ser","tem","mais","pb","paraiba","joao","pessoa","diz","segundo","nesta","neste","durante","novo","nova","confira","veja","saiba","entenda","caso","portal","jornal","maispb","clickpb","wscom","polemica","homem","mulher","suspeito","suspeita","investigado","investigada"}
ACTION_GROUPS={"morte":{"morre","morreu","morto","morta","morte","mata","matar","assassinato","homicidio"},"prisao":{"preso","presa","prende","prisao","captura","detido","detida"},"acidente":{"acidente","colisao","capotamento","atropelamento","atropela","bate","trem"},"denuncia":{"denuncia","denunciado","denunciada","reu","reus","processo","acusado","acusada"},"absolvicao":{"absolve","absolvido","absolvida","arquiva","arquivado"},"alerta":{"alerta","chuva","temporal","previsao","inmet"},"vacina":{"vacina","vacinacao","influenza","gripe","imunizacao"},"golpe":{"golpe","fraude","falso","whatsapp"},"operacao":{"operacao","mandado","apreende","apreensao","busca"},"servico":{"vagas","inscricao","prazo","concurso","curso","beneficio","fgts","inss"},"politica":{"aprova","ldo","eleicao","partido","senado","deputado","prefeito","governador"}}


def stem_token(word):
    for suffix in ("amento","imento","acoes","acao","mente","ados","adas","ido","ida","ou","aram","eram","es","s"):
        if len(word)>len(suffix)+4 and word.endswith(suffix): return word[:-len(suffix)]
    return word


def canonicalize_event_text(text):
    text=normalize_text(text)
    replacements={r"\binfluenza\b":"gripe",r"\bimunizacao\b":"vacinacao",r"\btorna(?:m)? reus?\b|\bvira(?:m)? reus?\b|\btransforma(?:m)? .*? em reus?\b|\baceita denuncia\b":"justica aceita denuncia reus",r"\barrastado por cavalo\b|\barrastado e morto por cavalo\b":"morte arrastado cavalo",r"\bforagida ha 10 anos\b|\bcondenada por maus tratos\b":"condenada maus tratos presa",r"\blimite de gastos(?: de campanha)?\b|\bpoderao gastar\b":"limite gastos campanha",r"\bchuvas intensas\b|\bprevisao do tempo\b":"alerta chuva inmet",r"\bex esposa\b|\bnamorada\b":"companheira",r"\bcomplexo viario beira rio ao altiplano\b|\bviaduto do altiplano\b":"complexo viario altiplano beira rio"}
    for pattern,replacement in replacements.items(): text=re.sub(pattern,replacement,text)
    return re.sub(r"\s+"," ",text).strip()


def meaningful_words(text): return {stem_token(w) for w in canonicalize_event_text(text).split() if len(w)>=4 and w not in STOPWORDS}
def extract_numbers(text): return set(re.findall(r"\b\d+(?:[\.,]\d+)?\b",normalize_text(text)))

def action_labels(text):
    words=set(canonicalize_event_text(text).split()); labels=set()
    for label,variants in ACTION_GROUPS.items():
        if words & variants: labels.add(label)
    return labels


def event_signature(item):
    title=canonicalize_event_text(item.get("titulo","")); summary=canonicalize_event_text(item.get("resumo","")); tw=meaningful_words(title); words=meaningful_words(f"{title} {summary}"); generic={"policia","civil","militar","justica","ministerio","publico","cidade","estado","programa","paraiba"}
    return {"title":title,"summary":summary,"title_words":tw,"words":words,"entities":{w for w in tw if w not in generic and len(w)>=5},"actions":action_labels(f"{title} {summary}"),"numbers":extract_numbers(f"{title} {summary}"),"editoria":item.get("editoria_interna","Geral"),"bucket":editorial_bucket(item)}


def token_overlap(a,b): return len(a&b)/max(1,min(len(a),len(b)))
def jaccard(a,b): return len(a&b)/max(1,len(a|b))

def same_sports_event(sa,sb):
    similarity=SequenceMatcher(None,sa["title"],sb["title"]).ratio(); overlap=token_overlap(sa["title_words"],sb["title_words"]); common=sa["title_words"]&sb["title_words"]
    return similarity>=.90 or (overlap>=.86 and len(common)>=5)


def both_match(sa,sb,terms):
    return all(any(term in side for term in terms) for side in (f"{sa['title']} {sa['summary']}",f"{sb['title']} {sb['summary']}"))


def distinctive_event_rules(sa,sb):
    if both_match(sa,sb,("rubinho",)) and both_match(sa,sb,("reu","denuncia")): return True
    if both_match(sa,sb,("cavalo",)) and both_match(sa,sb,("arrast","morte","morre")) and both_match(sa,sb,("sao jose de piranhas",)): return True
    if both_match(sa,sb,("maus tratos",)) and both_match(sa,sb,("filha",)) and both_match(sa,sb,("presa","prisao","foragida")): return True
    if both_match(sa,sb,("gripe","influenza")) and both_match(sa,sb,("vacina","vacinacao")): return True
    if both_match(sa,sb,("inmet",)) and both_match(sa,sb,("chuva","alerta","previsao")): return True
    if both_match(sa,sb,("limite gastos campanha",)) and both_match(sa,sb,("eleicoes 2026","eleicao 2026")): return True
    if both_match(sa,sb,("trabalhadores baianos","baianos mortos")) and both_match(sa,sb,("bayeux","joao pessoa")): return True
    if both_match(sa,sb,("complexo viario altiplano beira rio",)): return True
    if both_match(sa,sb,("leo bezerra",)) and both_match(sa,sb,("joao azevedo",)) and both_match(sa,sb,("psb","senador","boi de piranha","malas prontas")): return True
    return False


def same_event(a,b):
    sa,sb=event_signature(a),event_signature(b)
    if not sa["title_words"] or not sb["title_words"]: return False
    if sa["editoria"]=="Esportes" or sb["editoria"]=="Esportes": return sa["editoria"]==sb["editoria"] and same_sports_event(sa,sb)
    if distinctive_event_rules(sa,sb): return True
    title_sim=SequenceMatcher(None,sa["title"],sb["title"]).ratio(); title_overlap=token_overlap(sa["title_words"],sb["title_words"]); all_jaccard=jaccard(sa["words"],sb["words"]); common_entities=sa["entities"]&sb["entities"]; common_actions=sa["actions"]&sb["actions"]; common_numbers=sa["numbers"]&sb["numbers"]
    if abs(sa["bucket"]-sb["bucket"])>=3 and title_sim<.86: return False
    return title_sim>=.70 or (title_overlap>=.56 and len(sa["title_words"]&sb["title_words"])>=3) or (len(common_entities)>=2 and common_actions and all_jaccard>=.15) or (len(common_entities)>=2 and all_jaccard>=.25) or (len(common_entities)>=1 and common_actions and common_numbers and all_jaccard>=.16) or (len(common_entities)>=3 and all_jaccard>=.18)


def summary_quality(text):
    if not text or text=="Resumo não disponível na fonte.": return -1000
    low=normalize_text(text); penalty=sum(80 for bad in ("descubra","clique","fique informado","ultimas postagens","boas praticas se compartilham") if bad in low)
    return min(len(text),320)-penalty


def title_quality(text):
    low=normalize_text(text); penalty=sum(25 for bad in ("quem sabe faz conteudo","confira","veja","saiba") if bad in low)
    return min(len(text),180)-penalty


def member_quality(item):
    return title_quality(item.get("titulo",""))+summary_quality(item.get("resumo",""))


def merge_duplicate_events(items):
    groups=[]; ordered=sorted(items,key=lambda x:(x.get("publicado_em") or "",x["relevancia_interna"]),reverse=True)
    for item in ordered:
        match=next((g for g in groups if any(same_event(item,m) for m in g["_members"])),None)
        if match is None:
            item["_members"]=[dict(item)]; item["_best_member"]=dict(item); groups.append(item); continue
        match["_members"].append(dict(item))
        existing={s["link"] for s in match["fontes"]}
        for source in item["fontes"]:
            if source["link"] not in existing: match["fontes"].append(source)
        if member_quality(item)>member_quality(match["_best_member"]):
            match["_best_member"]=dict(item); match["titulo"]=item["titulo"]; match["resumo"]=item["resumo"]
        match["relevancia_interna"]=max(match["relevancia_interna"],item["relevancia_interna"])+min(8,2*(len(match["fontes"])-1))
        dates=[d for d in (match.get("publicado_em"),item.get("publicado_em")) if d]; match["publicado_em"]=max(dates) if dates else None
        match["editoria_interna"]=infer_editoria(match["_best_member"]["fontes"][0]["link"],match["titulo"],match["resumo"])
    for group in groups: group.pop("_members",None); group.pop("_best_member",None)
    return groups
