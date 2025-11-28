from psycopg2 import connect
from psycopg2.extras import RealDictCursor
from utils_text import tokenize

def normalize_query(s: str) -> str | None:
    """Normalise la requête utilisateur"""
    tokens = tokenize(s)
    return tokens[0] if tokens else None

def search_books(conn, raw_query: str, limit: int = 50):
    """
    Recherche de livres par mot-clé.
    Retourne TOUS les documents contenant le mot, classés par pertinence.
    
    Priorités:
    1. Titre contient le mot → priorité 0
    2. Mot dans top_terms → priorité 1  
    3. Mot dans postings → priorité 2
    
    Args:
        conn: connexion PostgreSQL
        raw_query: requête brute de l'utilisateur
        limit: nombre max de résultats
        
    Returns:
        Liste de dictionnaires avec les clés:
        - id, gutenberg_id, title, author, lang
        - match_count: nombre d'occurrences (None pour titre)
        - source: 'title', 'top_terms', ou 'postings'
        - priority: 0, 1, ou 2
    """
    q_norm = normalize_query(raw_query)
    if not q_norm:
        return []

    # Une seule requête SQL qui combine tout et déduplique
    sql = """
    WITH all_matches AS (
        -- 1) Recherche dans les titres (priorité 0)
        SELECT
            b.id,
            b.gutenberg_id,
            b.title,
            b.author,
            b.lang,
            b.cover_url,
            NULL::integer AS match_count,
            'title'::text AS source,
            0 AS priority
        FROM books b
        WHERE LOWER(b.title) LIKE '%' || LOWER(%(raw_query)s) || '%'

        UNION ALL

        -- 2) Recherche dans top_terms (priorité 1)
        SELECT
            b.id,
            b.gutenberg_id,
            b.title,
            b.author,
            b.lang,
            b.cover_url,
            tt.cnt AS match_count,
            'top_terms'::text AS source,
            1 AS priority
        FROM top_terms tt
        JOIN books b ON b.id = tt.book_id
        WHERE LOWER(tt.w) = LOWER(%(q_norm)s)

        UNION ALL

        -- 3) Recherche dans postings (priorité 2)
        SELECT
            b.id,
            b.gutenberg_id,
            b.title,
            b.author,
            b.lang,
            b.cover_url,
            p.cnt AS match_count,
            'postings'::text AS source,
            2 AS priority
        FROM words w
        JOIN postings p ON p.word_id = w.id
        JOIN books b ON b.id = p.book_id
        WHERE LOWER(w.w) = LOWER(%(q_norm)s)
    ),
    -- Déduplique: pour chaque livre, garde la meilleure source
    deduplicated AS (
        SELECT
            *,
            ROW_NUMBER() OVER (
                PARTITION BY id
                ORDER BY priority ASC, COALESCE(match_count, 0) DESC
            ) AS rn
        FROM all_matches
    )
    SELECT
        id,
        gutenberg_id,
        title,
        author,
        lang,
        cover_url,
        match_count,
        source,
        priority
    FROM deduplicated
    WHERE rn = 1
    ORDER BY
        priority ASC,
        COALESCE(match_count, 0) DESC,
        title ASC
    LIMIT %(limit)s;
    """

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, {
            "raw_query": raw_query,
            "q_norm": q_norm,
            "limit": limit
        })
        return cur.fetchall()


def search_books_by_source(conn, raw_query: str, limit: int = 50):
    """
    Variante qui retourne les résultats groupés par source.
    Utile pour débugger ou afficher des sections séparées dans l'UI.
    
    Returns:
        dict avec clés 'title', 'top_terms', 'postings'
    """
    q_norm = normalize_query(raw_query)
    if not q_norm:
        return {"title": [], "top_terms": [], "postings": []}

    results = {"title": [], "top_terms": [], "postings": []}

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # 1) Titre
        cur.execute("""
            SELECT b.id, b.gutenberg_id, b.title, b.author, b.lang, b.cover_url,
                   NULL::integer AS match_count
            FROM books b
            WHERE LOWER(b.title) LIKE '%' || LOWER(%s) || '%'
            ORDER BY b.title
            LIMIT %s;
        """, (raw_query, limit))
        results["title"] = cur.fetchall()

        # 2) top_terms
        cur.execute("""
            SELECT b.id, b.gutenberg_id, b.title, b.author, b.lang, b.cover_url,
                   tt.cnt AS match_count
            FROM top_terms tt
            JOIN books b ON b.id = tt.book_id
            WHERE LOWER(tt.w) = LOWER(%s)
            ORDER BY tt.cnt DESC, b.title
            LIMIT %s;
        """, (q_norm, limit))
        results["top_terms"] = cur.fetchall()

        # 3) postings
        cur.execute("""
            SELECT b.id, b.gutenberg_id, b.title, b.author, b.lang, b.cover_url,
                   p.cnt AS match_count
            FROM words w
            JOIN postings p ON p.word_id = w.id
            JOIN books b ON b.id = p.book_id
            WHERE LOWER(w.w) = LOWER(%s)
            ORDER BY p.cnt DESC, b.title
            LIMIT %s;
        """, (q_norm, limit))
        results["postings"] = cur.fetchall()

    return results


def get_search_statistics(conn, raw_query: str):
    """
    Retourne des statistiques sur la recherche.
    Utile pour afficher "Trouvé dans X titres, Y livres au total"
    """
    q_norm = normalize_query(raw_query)
    if not q_norm:
        return {"title": 0, "top_terms": 0, "postings": 0, "total": 0}

    with conn.cursor() as cur:
        # Compte dans chaque source
        cur.execute("""
            SELECT
                COUNT(DISTINCT b.id) FILTER (
                    WHERE LOWER(b.title) LIKE '%' || LOWER(%s) || '%'
                ) AS title_count,
                COUNT(DISTINCT tt.book_id) FILTER (
                    WHERE LOWER(tt.w) = LOWER(%s)
                ) AS top_terms_count,
                COUNT(DISTINCT p.book_id) FILTER (
                    WHERE LOWER(w.w) = LOWER(%s)
                ) AS postings_count
            FROM books b
            CROSS JOIN LATERAL (
                SELECT book_id FROM top_terms WHERE LOWER(w) = LOWER(%s)
            ) tt ON TRUE
            CROSS JOIN LATERAL (
                SELECT p.book_id
                FROM words w
                JOIN postings p ON p.word_id = w.id
                WHERE LOWER(w.w) = LOWER(%s)
            ) p ON TRUE;
        """, (raw_query, q_norm, q_norm, q_norm, q_norm))
        
        title_cnt, top_cnt, post_cnt = cur.fetchone()
        
        # Compte le total unique
        cur.execute("""
            SELECT COUNT(DISTINCT id) FROM (
                SELECT b.id FROM books b
                WHERE LOWER(b.title) LIKE '%' || LOWER(%s) || '%'
                UNION
                SELECT tt.book_id FROM top_terms tt
                WHERE LOWER(tt.w) = LOWER(%s)
                UNION
                SELECT p.book_id
                FROM words w
                JOIN postings p ON p.word_id = w.id
                WHERE LOWER(w.w) = LOWER(%s)
            ) AS combined;
        """, (raw_query, q_norm, q_norm))
        
        total = cur.fetchone()[0]

    return {
        "title": title_cnt,
        "top_terms": top_cnt,
        "postings": post_cnt,
        "total": total
    }


# Exemple d'utilisation
if __name__ == "__main__":
    import os
    PGURL = os.environ.get("PGURL")
    if not PGURL:
        raise SystemExit("Erreur: définis PGURL")
    
    conn = connect(PGURL)
    
    query = "love"
    print(f"Recherche: {query}\n")
    
    # Statistiques
    stats = get_search_statistics(conn, query)
    print(f"Statistiques:")
    print(f"  - Dans les titres: {stats['title']}")
    print(f"  - Dans top_terms: {stats['top_terms']}")
    print(f"  - Dans postings: {stats['postings']}")
    print(f"  - Total unique: {stats['total']}\n")
    
    # Résultats
    results = search_books(conn, query, limit=10)
    print(f"Top 10 résultats:")
    for i, r in enumerate(results, 1):
        cnt = r['match_count'] if r['match_count'] else "-"
        print(f"  {i}. [{r['source']}] {r['title'][:50]} ({cnt} occ.)")
    
    conn.close()