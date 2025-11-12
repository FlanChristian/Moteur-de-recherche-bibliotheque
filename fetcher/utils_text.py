import re
import unicodedata
from pathlib import Path

# Regex "conforme au cours" : alphabet latin
TOKEN = re.compile(r"[A-Za-z]+")

def normalize_text(s: str) -> str:
    """
    Normalise le texte façon cours :
    - NFKD + strip accents
    - ASCII-only
    - lowercase
    """
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.lower()

def tokenize(s: str) -> list[str]:
    """ Découpe en tokens A–Z et filtre les mots courts (<=2). """
    return [t for t in TOKEN.findall(s) if len(t) > 2]

def word_count_from_text(s: str) -> int:
    """ Compte les tokens utiles (même règle que tokenize). """
    return len(tokenize(s))

def ensure_dir(p: str | Path) -> Path:
    """ Crée le dossier s'il n'existe pas et le retourne. """
    p = Path(p)
    p.mkdir(parents=True, exist_ok=True)
    return p

def slugify(s: str, limit: int = 60) -> str:
    """ Slug ASCII, max `limit` chars. """
    s = normalize_text(s)
    out = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return out[:limit] if out else "untitled"
