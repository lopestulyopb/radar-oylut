import re
import unicodedata


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"[^a-zA-Z0-9\s]", " ", value.lower())
    return " ".join(value.split())


def matches_query(text: str, query: str) -> bool:
    if not query.strip():
        return True
    haystack = normalize(text)
    tokens = [t for t in normalize(query).split() if len(t) >= 3]
    return all(token in haystack for token in tokens)
