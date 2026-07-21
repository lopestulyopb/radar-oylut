import re
import unicodedata
from bs4 import BeautifulSoup

PORTALS = "MaisPB|ClickPB|WSCOM|Polêmica Paraíba|Jornal da Paraíba|G1 Paraíba|Patos Online"


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-zA-Z0-9\s]", " ", value).lower()
    return re.sub(r"\s+", " ", value).strip()


def clean_text(value: str, limit: int | None = None) -> str:
    text = BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(rf"^({PORTALS})\s*[•|\-:]\s*", "", text, flags=re.I)
    text = re.sub(rf"\s*[|\-]\s*({PORTALS})(?:\s*[|\-]\s*Quem sabe, faz conteúdo)?$", "", text, flags=re.I)
    text = re.sub(r"\s*-\s*WSCOM\s*-\s*Quem sabe, faz conteúdo\s*$", "", text, flags=re.I)
    text = re.sub(rf"^(?:[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç.-]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÁÉÍÓÚÂÊÔÃÕÇáéíóúâêôãõç.-]+){{0,3}})\s*[–—-]\s*(?:{PORTALS})\s+", "", text)
    text = re.sub(r"^(Descubra|Clique e veja|Saiba mais sobre)\s+", "", text, flags=re.I)
    text = re.sub(r"\bwhatsApp\b", "WhatsApp", text, flags=re.I)
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip(" ,;:-") + "…"
    return text
