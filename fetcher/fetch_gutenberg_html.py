#!/usr/bin/env python3
"""
Télécharge des livres Gutenberg en utilisant le format HTML quand text/plain n'est pas disponible.
Extrait le texte propre du HTML avec BeautifulSoup.

Version alternative de fetch_gutenberg.py pour les livres récents sans format texte.
"""

import os
import time
import requests
from pathlib import Path
from typing import Optional, Tuple
from bs4 import BeautifulSoup
import re

from utils_text import (
    normalize_text,
    word_count_from_text,
    slugify,
    ensure_dir,
)

API = "https://gutendex.com/books"
SCRIPT_DIR = Path(__file__).parent
OUT_DIR = ensure_dir(SCRIPT_DIR / "data" / "raw")

# --- Réglages ---
LANGS      = os.getenv("FETCH_LANGS", "en,fr").split(",")
TARGET     = int(os.getenv("FETCH_TARGET", "2000"))
RATE_LIMIT = float(os.getenv("FETCH_RATE_S", "1.0"))
MIN_WORDS  = int(os.getenv("FETCH_MIN_WORDS", "10000"))
TIMEOUT    = float(os.getenv("FETCH_TIMEOUT_S", "60"))
MAX_RETRIES = int(os.getenv("FETCH_MAX_RETRIES", "3"))
RETRY_DELAY = float(os.getenv("FETCH_RETRY_DELAY_S", "5.0"))
START_PAGE = int(os.getenv("FETCH_START_PAGE", "1"))

def extract_text_from_html(html_content: str) -> str:
    """
    Extrait le texte lisible du HTML Gutenberg.
    Le contenu principal est généralement dans des balises <p>, <div>, etc.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Retire les scripts, styles, et metadata
    for script in soup(["script", "style", "head", "title", "meta", "[document]"]):
        script.extract()
    
    # Essaie de trouver le contenu principal
    # Gutenberg utilise souvent <body> ou <div> avec le texte
    main_content = soup.find('body')
    if main_content:
        text = main_content.get_text(separator='\n', strip=True)
    else:
        text = soup.get_text(separator='\n', strip=True)
    
    # Nettoie les lignes vides multiples
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    text = '\n'.join(lines)
    
    return text

def pick_url(formats: dict) -> Optional[Tuple[str, str]]:
    """
    Retourne (type, url) en priorité:
    1. text/plain (idéal)
    2. text/html (on va extraire le texte)
    3. text/plain; charset=us-ascii (ascii)
    """
    # Priorité 1: text/plain UTF-8
    for k in ("text/plain; charset=utf-8", "text/plain"):
        url = formats.get(k)
        if isinstance(url, str) and url.startswith("http") and not url.endswith(".zip"):
            return ("text", url)
    
    # Priorité 2: HTML (disponible pour presque tous les livres)
    html_url = formats.get("text/html")
    if isinstance(html_url, str) and html_url.startswith("http"):
        return ("html", html_url)
    
    # Priorité 3: text/plain ASCII
    ascii_url = formats.get("text/plain; charset=us-ascii")
    if isinstance(ascii_url, str) and ascii_url.startswith("http") and not ascii_url.endswith(".zip"):
        return ("text", ascii_url)
    
    return None

def fetch_page(url: str, retry_count: int = 0) -> Optional[dict]:
    """Fetch une page de l'API avec retry"""
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code >= 500 and retry_count < MAX_RETRIES:
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
    # Vérifie BeautifulSoup
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("❌ BeautifulSoup4 n'est pas installé!")
        print("Installation: pip install beautifulsoup4")
        return
    
    existing_files = list(OUT_DIR.glob("pg_*_*.txt"))
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
    html_count = 0  # Compteur de livres extraits du HTML
    
    print(f"Recherche de livres à partir de la page {START_PAGE}...")
    print(f"Mode: TEXT/PLAIN ou HTML (extraction automatique)")
    page_url = f"{API}?languages={','.join(LANGS)}&page={START_PAGE}&sort=ascending"
    current_page = START_PAGE

    while page_url and kept_files < TARGET:
        print(f"\n[PAGE {current_page}] Récupération de la page...")
        data = fetch_page(page_url)
        current_page += 1
        
        if data is None:
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                print(f"\n[STOP] Trop d'erreurs consécutives ({consecutive_errors}). Arrêt du script.")
                break
            if data and data.get("next"):
                page_url = data.get("next")
                time.sleep(RATE_LIMIT * 2)
            else:
                print("[STOP] Impossible de continuer, pas de page suivante.")
                break
            continue
        
        consecutive_errors = 0
        results = data.get("results", [])
        
        if not results:
            print("[INFO] Aucun résultat sur cette page, passage à la suivante...")
            page_url = data.get("next")
            if page_url:
                time.sleep(RATE_LIMIT)
            continue
        
        print(f"[INFO] {len(results)} livres trouvés sur cette page")
        
        for idx, b in enumerate(results, 1):
            gid = b.get("id")
            title = b.get("title") or "untitled"
            authors = b.get("authors", [])
            author_name = authors[0].get("name") if authors else "Unknown"
            languages = b.get("languages", [])
            language = languages[0] if languages else "unknown"
            formats = b.get("formats", {})
            cover_url = formats.get("image/jpeg", "")
            
            url_info = pick_url(formats)
            if not gid or not url_info:
                print(f"  [{idx}/{len(results)}] SKIP id={gid} - Aucun format TEXT ou HTML disponible")
                continue

            content_type, url = url_info
            fname = OUT_DIR / f"pg_{gid}_{slugify(title)}.txt"
            meta_fname = OUT_DIR / f"pg_{gid}_meta.json"
            
            if fname.exists():
                print(f"  [{idx}/{len(results)}] EXISTS id={gid} - {title[:40]}...")
                continue

            try:
                processed += 1
                format_label = "HTML→TEXT" if content_type == "html" else "TEXT"
                print(f"  [{idx}/{len(results)}] DOWNLOADING id={gid} [{format_label}] - {title[:40]}...")
                time.sleep(RATE_LIMIT)
                
                tr = requests.get(url, timeout=TIMEOUT)
                tr.raise_for_status()
                
                # Traitement selon le type
                if content_type == "html":
                    text_raw = extract_text_from_html(tr.text)
                    html_count += 1
                else:
                    text_raw = tr.text

                norm = normalize_text(text_raw)
                wc = word_count_from_text(norm)
                
                if wc < MIN_WORDS:
                    print(f"  [{idx}/{len(results)}] SKIP id={gid} - Trop court ({wc} words < {MIN_WORDS})")
                    continue

                fname.write_text(norm, encoding="utf-8")
                
                # Métadonnées
                import json
                meta = {
                    "gutenberg_id": gid,
                    "title": title,
                    "author": author_name,
                    "language": language,
                    "cover_url": cover_url,
                    "source_format": content_type  # Indique si c'était HTML ou TEXT
                }
                meta_fname.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                
                kept_files += 1
                downloaded_this_run += 1
                print(f"  [{idx}/{len(results)}] ✓ OK id={gid} - {fname.name} ({wc} words) [{kept_files}/{TARGET}]")
                
            except requests.exceptions.RequestException as e:
                print(f"  [{idx}/{len(results)}] ✗ ERROR Téléchargement id={gid} -> {e}")
            except Exception as e:
                print(f"  [{idx}/{len(results)}] ✗ ERROR Traitement id={gid} -> {e}")

            if kept_files >= TARGET:
                break

        page_url = data.get("next")
        if page_url:
            time.sleep(RATE_LIMIT)

    print(f"\n=== Terminé ===")
    print(f"Livres traités cette session: {processed}")
    print(f"Nouveaux livres gardés: {downloaded_this_run}")
    print(f"  - Extraits du HTML: {html_count}")
    print(f"  - Format texte direct: {downloaded_this_run - html_count}")
    print(f"Total de livres valides (>= {MIN_WORDS} words): {kept_files}/{TARGET}")
    
    if kept_files < TARGET:
        print(f"\n⚠️  Objectif non atteint ({kept_files}/{TARGET}). Relancez le script pour continuer.")

if __name__ == "__main__":
    main()
