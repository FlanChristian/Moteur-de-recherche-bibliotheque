#!/usr/bin/env python3
"""
Télécharge automatiquement des livres (texte brut) via l'API Gutendex,
ne garde que ceux qui ont >= MIN_WORDS mots après normalisation.

- Enregistre dans data/raw/ : pg_{id}_{slug(title)}.txt
- Reprend là où il s'est arrêté (skip si fichier existe)
- Rate limiting basique (politesse)
- Gestion robuste des erreurs serveur

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
LANGS      = os.getenv("FETCH_LANGS", "en,fr").split(",")
TARGET     = int(os.getenv("FETCH_TARGET", "2000"))
RATE_LIMIT = float(os.getenv("FETCH_RATE_S", "1.0"))
MIN_WORDS  = int(os.getenv("FETCH_MIN_WORDS", "10000"))
TIMEOUT    = float(os.getenv("FETCH_TIMEOUT_S", "60"))
MAX_RETRIES = int(os.getenv("FETCH_MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("FETCH_RETRY_DELAY_S", "5.0"))
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

def fetch_page(url: str, retry_count: int = 0) -> Optional[dict]:
    """
    Fetch une page de l'API avec retry en cas d'erreur serveur
    """
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code >= 500 and retry_count < MAX_RETRIES:
            # Erreur serveur, on retry
            wait_time = RETRY_DELAY * (retry_count + 1)
            print(f"[WARN] Erreur serveur {e.response.status_code}, retry {retry_count + 1}/{MAX_RETRIES} dans {wait_time}s...")
            time.sleep(wait_time)
            return fetch_page(url, retry_count + 1)
        else:
            print(f"[ERROR] Impossible de récupérer la page après {retry_count} tentatives: {e}")
            return None
    except Exception as e:
        print(f"[ERROR] Erreur lors du fetch: {e}")
        return None

def main():
    # Compte d'abord les fichiers déjà téléchargés
    existing_files = list(OUT_DIR.glob("pg_*_*.txt"))
    # Exclut les fichiers meta
    existing_files = [f for f in existing_files if not f.name.endswith("_meta.json")]
    kept_files = len(existing_files)
    
    print(f"Fichiers déjà téléchargés: {kept_files}/{TARGET}")
    
    if kept_files >= TARGET:
        print(f"Objectif déjà atteint! {kept_files} livres disponibles.")
        return
    
    downloaded_this_run = 0
    processed = 0
    consecutive_errors = 0
    max_consecutive_errors = 10
    
    page_url = f"{API}?languages={','.join(LANGS)}&page=1"

    while page_url and kept_files < TARGET:
        data = fetch_page(page_url)
        
        if data is None:
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                print(f"\n[STOP] Trop d'erreurs consécutives ({consecutive_errors}). Arrêt du script.")
                break
            # Passe à la page suivante si disponible
            if data and data.get("next"):
                page_url = data.get("next")
                time.sleep(RATE_LIMIT * 2)  # Double le délai après erreur
            else:
                print("[STOP] Impossible de continuer, pas de page suivante.")
                break
            continue
        
        # Reset le compteur d'erreurs si succès
        consecutive_errors = 0
        
        results = data.get("results", [])
        
        if not results:
            print("[INFO] Aucun résultat sur cette page, passage à la suivante...")
            page_url = data.get("next")
            if page_url:
                time.sleep(RATE_LIMIT)
            continue
        
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
            meta_fname = OUT_DIR / f"pg_{gid}_meta.json"
            
            if fname.exists():
                # Fichier existe déjà, on continue sans incrémenter
                continue

            try:
                processed += 1
                time.sleep(RATE_LIMIT)
                tr = requests.get(txt_url, timeout=TIMEOUT)
                tr.raise_for_status()
                text_raw = tr.text

                norm = normalize_text(text_raw)
                wc = word_count_from_text(norm)
                if wc < MIN_WORDS:
                    print(f"[SKIP] {title[:40]}... ({wc} words < {MIN_WORDS})")
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
                
                kept_files += 1
                downloaded_this_run += 1
                print(f"[OK] {fname.name}  ({wc} words, author: {author_name}) [{kept_files}/{TARGET}]")
            except requests.exceptions.RequestException as e:
                print(f"[ERROR] Téléchargement id={gid} -> {e}")
            except Exception as e:
                print(f"[ERROR] Traitement id={gid} -> {e}")

            if kept_files >= TARGET:
                break

        page_url = data.get("next")
        if page_url:
            time.sleep(RATE_LIMIT)

    print(f"\n=== Terminé ===")
    print(f"Livres traités cette session: {processed}")
    print(f"Nouveaux livres gardés: {downloaded_this_run}")
    print(f"Total de livres valides (>= {MIN_WORDS} words): {kept_files}/{TARGET}")
    
    if kept_files < TARGET:
        print(f"\n⚠️  Objectif non atteint ({kept_files}/{TARGET}). Relancez le script pour continuer.")

if __name__ == "__main__":
    main()