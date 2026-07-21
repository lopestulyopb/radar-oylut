from urllib.parse import urlparse
from .text import normalize_text


def is_excluded_content(url: str, title: str = "", summary: str = "") -> bool:
    path = urlparse(url).path.lower(); text = normalize_text(f"{title} {summary}")
    blocked_path = ("/espaco-opiniao/","/opiniao-e-blogs/","/opiniao/","/blogs/","/colunas/","/colunistas/","/ao-vivo","clickfm-ao-vivo","/cultura/silvio-osias/","/blog/","/artigo/")
    if any(token in path for token in blocked_path): return True
    if any(token in text for token in ("por janguie diniz","por cid gadelha","ao vivo","quem sabe faz conteudo fique informado")): return True
    institutional = ("recebe comitiva","reforca compromisso","referencia em inovacao e tecnologia","participa da abertura do projeto")
    if any(token in text for token in institutional) and not any(k in text for k in ("vaga","curso","inscricao","servico","gratuito")): return True
    return False
