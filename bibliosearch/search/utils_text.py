import re
import unicodedata
from pathlib import Path

# Regex "conforme au cours" : alphabet latin
TOKEN = re.compile(r"[A-Za-z]+")

# Stop words : mots génériques à filtrer de l'indexation
STOP_WORDS = frozenset([
    # Articles, prépositions, conjonctions anglais
    "the", "and", "that", "with", "for", "are", "was", "but", "not", "you", "all",
    "can", "her", "his", "has", "had", "been", "have", "their", "said", "from",
    "they", "one", "what", "which", "this", "these", "those", "there", "where",
    "when", "who", "whom", "whose", "were", "will", "would", "could", "should",
    "may", "might", "must", "shall", "did", "does", "doing", "done", "being",
    "into", "through", "during", "before", "after", "above", "below", "between",
    "among", "under", "over", "again", "further", "then", "once", "here",
    "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "only", "own", "same", "than", "too", "very", "about", "against", "also",
    "because", "while", "until", "upon", "out", "off", "down", "back", "even",
    "just", "still", "much", "many", "such", "like", "however", "moreover",
    "therefore", "thus", "hence", "indeed", "yet", "nor", "either", "neither",
    "whether", "though", "although", "unless", "since", "whenever", "wherever",
    "whatever", "whoever", "whichever", "itself", "himself", "herself", "themselves",
    "myself", "yourself", "ourselves", "yourselves",
    
    # Pronoms et mots courts
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "her", "was",
    "one", "our", "out", "day", "get", "has", "him", "his", "how", "its", "may",
    "new", "now", "old", "see", "two", "way", "who", "boy", "did", "let", "put",
    "say", "she", "too", "use", "man", "men", "own", "per", "set", "try", "war",
    "yes", "yet", "via", "why", "ago", "far", "few", "got", "lot", "off",
    
    # Formes verbales fréquentes
    "am", "is", "be", "as", "at", "by", "do", "go", "he", "if", "in", "it", "me",
    "my", "no", "of", "on", "or", "so", "to", "up", "us", "we",
    
    # Nombres et ordinaux
    "ten", "six", "six", "nine", "four", "five", "eight", "seven", "three",
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
    "ninth", "tenth", "hundred", "thousand", "million",
    
    # Mots français courants
    "les", "des", "une", "dans", "pour", "que", "qui", "est", "avec",
    "sur", "par", "plus", "pas", "cette", "son", "sont", "mais", "tout",
    "aux", "comme", "ses", "leur", "leurs", "sans", "dont", "elle", "nous",
    "vous", "ils", "elles", "ont", "fait", "peut", "faire", "cette", "ces",
    "celui", "celle", "ceux", "celles", "aussi", "bien", "encore", "ainsi",
    "donc", "sous", "depuis", "vers", "entre", "alors", "autre", "autres",
    "trop", "tres", "peu", "beaucoup", "assez", "moins", "jamais", "toujours",
    "souvent", "quelque", "quelques", "chaque", "plusieurs", "aucun", "aucune",
])

def normalize_text(s: str) -> str:
    """
    Normalise le texte façon cours :
    - NFKD + strip accents
    - ASCII-only
    - lowercase
    """
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s.lower()

def tokenize(s: str, filter_stopwords: bool = True) -> list[str]:
    """ 
    Découpe en tokens A–Z et filtre les mots courts (<=2).
    Si filter_stopwords=True, retire également les stop words.
    """
    tokens = [t.lower() for t in TOKEN.findall(s) if len(t) > 2]
    if filter_stopwords:
        tokens = [t for t in tokens if t not in STOP_WORDS]
    return tokens

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
