#!/usr/bin/env python3
"""
Charge les fichiers data/raw/*.txt dans PostgreSQL :
- books(gutenberg_id,title,author,language,word_count,path_txt)
- book_texts(book_id, content)
- words(w) + postings(word_id, book_id, cnt)

Prérequis:
- Crée le schéma via sql/schema.sql (ou lance avec INIT_SCHEMA=1)
- Variable d'env PGURL, ex:
  export PGURL=postgresql://user:pass@localhost:5432/daar

Dépendances: psycopg2-binary
"""

import os
import re
from pathlib import Path
from collections import Counter
import json

import psycopg2
from psycopg2.extras import execute_values

from utils_text import tokenize, ensure_dir

RAW_DIR = Path("data/raw")

# --- Option: créer le schéma si INIT_SCHEMA=1 ---
SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS books (
  id           BIGSERIAL PRIMARY KEY,
  gutenberg_id BIGINT UNIQUE,
  title        TEXT NOT NULL,
  author       TEXT,
  language     TEXT,
  word_count   INT NOT NULL,
  path_txt     TEXT,
  cover_url    TEXT, 
  created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS book_texts (
  book_id BIGINT PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,
  content TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS words (
  id BIGSERIAL PRIMARY KEY,
  w  TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS postings (
  word_id BIGINT REFERENCES words(id) ON DELETE CASCADE,
  book_id BIGINT REFERENCES books(id) ON DELETE CASCADE,
  cnt     INT NOT NULL,
  PRIMARY KEY (word_id, book_id)
);

CREATE TABLE IF NOT EXISTS jaccard_edges (
    book_id1 INTEGER NOT NULL,
    book_id2 INTEGER NOT NULL,
    dist     DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (book_id1, book_id2)
);

CREATE INDEX IF NOT EXISTS words_w_idx ON words (w);
CREATE INDEX IF NOT EXISTS postings_word_idx ON postings (word_id);
CREATE INDEX IF NOT EXISTS postings_book_idx ON postings (book_id);
CREATE INDEX IF NOT EXISTS book_texts_trgm_idx ON book_texts USING GIN (content gin_trgm_ops);
"""

FNAME_RE = re.compile(r"^pg_(\d+)_")  # extrait gutenberg_id depuis le nom de fichier

def build_top_terms(conn, k=50):
    """
    Construit la table top_terms avec les k mots les plus fréquents par livre.
    """
    print(f"[INFO] Construction de top_terms avec top-{k} mots par livre...")

    q = f"""
    DROP TABLE IF EXISTS top_terms;
    CREATE TABLE top_terms (
      book_id BIGINT NOT NULL,
      word_id BIGINT NOT NULL,
      w       TEXT   NOT NULL,
      cnt     INT    NOT NULL,
      rnk     INT    NOT NULL,
      PRIMARY KEY (book_id, word_id)
    );

    CREATE INDEX ON top_terms (book_id);
    CREATE INDEX ON top_terms (w);

    WITH ranked AS (
      SELECT
        p.book_id,
        p.word_id,
        w.w,
        p.cnt,
        ROW_NUMBER() OVER (
          PARTITION BY p.book_id
          ORDER BY p.cnt DESC, w.w ASC
        ) AS rnk
      FROM postings p
      JOIN words w ON w.id = p.word_id
      LEFT JOIN stopwords s ON s.w = w.w
      WHERE (s.w IS NULL OR s.w IS NULL) AND char_length(w.w) > 2
    )
    INSERT INTO top_terms (book_id, word_id, w, cnt, rnk)
    SELECT book_id, word_id, w, cnt, rnk
    FROM ranked
    WHERE rnk <= {k};
    """

    with conn.cursor() as cur:
        cur.execute(q)
        conn.commit()
    print("[OK] Table top_terms créée avec succès.")


def parse_meta_from_filename(path: Path):
    """
    Récupère les métadonnées depuis le fichier JSON associé
    """
    m = FNAME_RE.match(path.name)
    gid = int(m.group(1)) if m else None
    
    # Cherche le fichier meta JSON
    meta_file = path.parent / f"pg_{gid}_meta.json"
    
    if meta_file.exists():
        try:
            meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
            return {
                "gutenberg_id": gid,
                "title": meta_data.get("title", "Unknown"),
                "author": meta_data.get("author", "Unknown"),
                "language": meta_data.get("language", "unknown"),
                "cover_url": meta_data.get("cover_url", "")
            }
        except:
            pass
    
    # Fallback sur l'ancien système
    title_slug = path.stem
    if gid is not None:
        title_slug = title_slug[len(f"pg_{gid}_"):]
    title = title_slug.replace("_", " ").strip() or "Unknown"
    
    return {
        "gutenberg_id": gid,
        "title": title,
        "author": "Unknown",
        "language": "unknown",
        "cover_url": ""
    }

def bulk_upsert_words(cur, words: list[str]) -> None:
    """
    Insère la liste de mots dans `words(w)` en ignorant les doublons.
    (ON CONFLICT DO NOTHING). Utilise execute_values pour aller vite.
    """
    if not words:
        return
    values = [(w,) for w in words]
    execute_values(
        cur,
        "INSERT INTO words (w) VALUES %s ON CONFLICT (w) DO NOTHING",
        values,
        page_size=10000
    )

def fetch_word_ids(cur, words: list[str]) -> dict[str, int]:
    """
    Récupère les id pour les mots donnés.
    """
    if not words:
        return {}
    cur.execute("SELECT id, w FROM words WHERE w = ANY(%s)", (words,))
    return {w: i for (i, w) in cur.fetchall()}

def bulk_upsert_postings(cur, book_id: int, counts: Counter) -> None:
    """
    Insère (word_id, book_id, cnt) pour un livre.
    """
    if not counts:
        return
    # Prépare les mots, upsert, récup IDs
    unique_words = list(counts.keys())
    bulk_upsert_words(cur, unique_words)
    ids = fetch_word_ids(cur, unique_words)

    values = [(ids[w], book_id, int(c)) for w, c in counts.items()]
    execute_values(
        cur,
        """
        INSERT INTO postings (word_id, book_id, cnt)
        VALUES %s
        ON CONFLICT (word_id, book_id) DO UPDATE SET cnt = EXCLUDED.cnt
        """,
        values,
        page_size=10000
    )

def ingest_file(cur, path: Path) -> bool:
    meta = parse_meta_from_filename(path)
    if meta["gutenberg_id"] is None:
        return False

    text = path.read_text(encoding="utf-8", errors="ignore")
    tokens = tokenize(text)
    if len(tokens) < 10000:
        return False

    # 1) books - AVEC cover_url
    cur.execute(
        """
        INSERT INTO books (gutenberg_id, title, author, language, word_count, path_txt, cover_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (gutenberg_id) DO UPDATE
          SET title = EXCLUDED.title,
              author = EXCLUDED.author,
              language = EXCLUDED.language,
              word_count = EXCLUDED.word_count,
              path_txt = EXCLUDED.path_txt,
              cover_url = EXCLUDED.cover_url
        RETURNING id
        """,
        (meta["gutenberg_id"], meta["title"], meta["author"], meta["language"],
         len(tokens), str(path), meta.get("cover_url", ""))
    )
    book_id = cur.fetchone()[0]

    # 2) book_texts
    cur.execute(
        """
        INSERT INTO book_texts (book_id, content)
        VALUES (%s, %s)
        ON CONFLICT (book_id) DO UPDATE SET content = EXCLUDED.content
        """,
        (book_id, text)
    )

    # 3) postings
    counts = Counter(tokens)
    bulk_upsert_postings(cur, book_id, counts)
    return True

def main():
    if not RAW_DIR.exists():
        ensure_dir(RAW_DIR)

    pgurl = os.environ.get("PGURL")
    if not pgurl:
        raise SystemExit("Erreur: définis la variable d'env PGURL (ex: postgres://user:pwd@localhost/db)")

    conn = psycopg2.connect(pgurl)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        if os.environ.get("INIT_SCHEMA", "0") == "1":
            print("[INIT] création du schéma…")
            cur.execute(SCHEMA_SQL)
            conn.commit()

        files = sorted([p for p in RAW_DIR.glob("*.txt") if p.is_file()])
        inserted = 0
        for i, path in enumerate(files, start=1):
            ok = ingest_file(cur, path)
            if ok:
                inserted += 1
            if i % 20 == 0:
                conn.commit()
                print(f"[PROGRESS] {i}/{len(files)} fichiers traités (insérés/MAJ: {inserted})")

        conn.commit()
        print(f"[DONE] Fichiers traités: {len(files)} ; Livres insérés/MAJ: {inserted}")
    finally:
        cur.close()
        conn.close()

# ----------------------------------------------------------------
# Ici commence ton script principal
# ----------------------------------------------------------------
if __name__ == "__main__":
    import os

    PGURL = os.getenv("PGURL")
    if not PGURL:
        print("Erreur: définis la variable d'environnement PGURL")
        exit(1)

    # ✅ ici on crée la connexion
    conn = psycopg2.connect(PGURL)
    print("[INFO] Connexion PostgreSQL ouverte")

    # ... ton code d’ingestion des livres ...
    # (ajout dans books, book_texts, words, postings, etc.)

    # ✅ une fois les livres insérés :
    build_top_terms(conn, k=50)

    # ✅ enfin on ferme la connexion
    conn.close()
    print("[INFO] Connexion PostgreSQL fermée")

    main()

