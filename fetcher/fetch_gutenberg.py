#!/usr/bin/env python3
"""
Télécharge automatiquement des livres (texte brut) via l’API Gutendex,
ne garde que ceux qui ont >= MIN_WORDS mots après normalisation.

- Enregistre dans data/raw/ : pg_{id}_{slug(title)}.txt
- Reprend là où il s'est arrêté (skip si fichier existe)
- Rate limiting basique (politesse)

Ajuste les constantes LANGS / TARGET / MIN_WORDS selon tes besoins.
"""

import os
import time
import requests
from pathlib import Path
from typing import Optional

from utils_text import (
    normalize_text,
    word_count_from_text,
    slugify,
    ensure_dir,
)

API = "https://gutendex.com/books"
OUT_DIR = ensure_dir("data/raw")

# --- Réglages (à adapter) ---
LANGS      = os.getenv("FETCH_LANGS", "en,fr").split(",")  # ex: "fr" ou "en,fr"
TARGET     = int(os.getenv("FETCH_TARGET", "2000"))        # vise large (filtrage ensuite)
RATE_LIMIT = float(os.getenv("FETCH_RATE_S", "1.0"))       # >= 1 req/s
MIN_WORDS  = int(os.getenv("FETCH_MIN_WORDS", "10000"))    # contrainte de l’énoncé
TIMEOUT    = float(os.getenv("FETCH_TIMEOUT_S", "60"))
# ----------------------------

def pick_text_url(formats: dict) -> Optional[str]:
    """
    Choisit un lien texte brut fiable en priorité:
    - 'text/plain; charset=utf-8' puis 'text/plain'
    - évite les .zip pour rester simple
    """
    for k in ("text/plain; charset=utf-8", "text/plain"):
        url = formats.get(k)
        if isinstance(url, str) and url.startswith("http") and not url.endswith(".zip"):
            return url
    return None

def fetch_page(url: str) -> dict:
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def main():
    downloaded = 0
    page_url = f"{API}?languages={','.join(LANGS)}&page=1"

    while page_url and downloaded < TARGET:
        data = fetch_page(page_url)
        results = data.get("results", [])
        for b in results:
            gid = b.get("id")
            title = b.get("title") or "untitled"
            
            # Récupère l'auteur
            authors = b.get("authors", [])
            author_name = authors[0].get("name") if authors else "Unknown"
            
            # Récupère la langue
            languages = b.get("languages", [])
            language = languages[0] if languages else "unknown"
            
            # Récupère l'URL de la couverture
            formats = b.get("formats", {})
            cover_url = formats.get("image/jpeg", "")
            
            txt_url = pick_text_url(formats)
            if not gid or not txt_url:
                continue

            fname = OUT_DIR / f"pg_{gid}_{slugify(title)}.txt"
            meta_fname = OUT_DIR / f"pg_{gid}_meta.json"  # Nouveau fichier pour les métadonnées
            
            if fname.exists():
                downloaded += 1
                continue

            try:
                time.sleep(RATE_LIMIT)
                tr = requests.get(txt_url, timeout=TIMEOUT)
                tr.raise_for_status()
                text_raw = tr.text

                norm = normalize_text(text_raw)
                wc = word_count_from_text(norm)
                if wc < MIN_WORDS:
                    continue

                fname.write_text(norm, encoding="utf-8")
                
                # Sauvegarde les métadonnées dans un fichier JSON
                import json
                meta = {
                    "gutenberg_id": gid,
                    "title": title,
                    "author": author_name,
                    "language": language,
                    "cover_url": cover_url
                }
                meta_fname.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
                
                downloaded += 1
                print(f"[OK] {fname.name}  ({wc} words, author: {author_name})")
            except Exception as e:
                print(f"[SKIP] id={gid} -> {e}")

            if downloaded >= TARGET:
                break

        page_url = data.get("next")
        if page_url:
            time.sleep(RATE_LIMIT)

    print(f"Done. Kept files (>= {MIN_WORDS} words): {downloaded}")

if __name__ == "__main__":
    main()
