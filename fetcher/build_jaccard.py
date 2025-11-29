#!/usr/bin/env python3
import os
import psycopg2
from collections import defaultdict
from itertools import combinations

PGURL = os.environ.get("PGURL")
if not PGURL:
    raise SystemExit("Erreur: définis la variable d'environnement PGURL")

# Seuil : on garde seulement les paires avec distance < THRESH
THRESH = 0.5   # tu pourras ajuster


def load_postings(conn):
    """
    Charge les postings sous forme :
    docs[book_id] = {word_id: cnt, ...}
    """
    docs = defaultdict(dict)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT book_id, word_id, cnt
            FROM postings
        """)
        for book_id, word_id, cnt in cur:
            docs[book_id][word_id] = cnt
    return docs


def jaccard_distance(idx1, idx2):
    """
    idx1, idx2 : dict word_id -> cnt
    retourne une distance dans [0,1]
    """
    common_words = set(idx1.keys()) & set(idx2.keys())
    if not common_words:
        return 1.0

    num = 0.0
    den = 0.0
    for w in common_words:
        k1 = idx1[w]
        k2 = idx2[w]
        mx = max(k1, k2)
        mn = min(k1, k2)
        num += (mx - mn)
        den += mx

    if den == 0:
        return 1.0
    return num / den


def build_jaccard(conn):
    docs = load_postings(conn)
    book_ids = sorted(docs.keys())

    print(f"🔍 {len(book_ids)} livres chargés.")
    total_pairs = len(book_ids) * (len(book_ids) - 1) // 2
    print(f"📊 {total_pairs} paires à calculer.")
    print(f"🎯 Seuil de distance: {THRESH} (similarité >= {1-THRESH})")

    with conn.cursor() as cur:
        # On nettoie la table si besoin
        cur.execute("TRUNCATE jaccard_edges;")
        
        edges_count = 0
        for i, (b1, b2) in enumerate(combinations(book_ids, 2), start=1):
            d = jaccard_distance(docs[b1], docs[b2])
            if d < THRESH:
                sim = 1.0 - d
                cur.execute(
                    """
                    INSERT INTO jaccard_edges (book_id1, book_id2, dist, similarity)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (b1, b2, d, sim),
                )
                edges_count += 1

            if i % 10000 == 0:
                print(f"⏳ {i}/{total_pairs} paires traitées ({edges_count} arêtes créées)...")
                conn.commit()

        conn.commit()
        print(f"\n✅ Graphe construit avec succès!")
        print(f"📊 {edges_count} arêtes créées sur {total_pairs} paires ({100*edges_count/total_pairs:.2f}%)")


def main():
    with psycopg2.connect(PGURL) as conn:
        build_jaccard(conn)


if __name__ == "__main__":
    main()
