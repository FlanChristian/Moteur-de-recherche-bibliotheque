#!/usr/bin/env python3
"""
Recherche avancée par expression régulière (RegEx).

Deux modes selon le sujet :
1. Recherche dans l'INDEXAGE (top_terms → postings) : rapide, mots normalisés
2. Recherche dans le CONTENU (book_texts) : lent, texte original

Architecture :
- top_terms : table d'indexage (top 50 mots par livre)
- postings : index complet (tous les mots tokenisés)
- book_texts : contenu textuel brut original

Usage:
    from search_regex import search_by_regex
    results = search_by_regex(conn, r'sh.*lock', mode='indexing')
"""

import re
from psycopg2.extras import RealDictCursor
from typing import Literal


def validate_regex(pattern: str) -> tuple[bool, str | None]:
    """
    Valide une expression régulière.
    
    Returns:
        (is_valid, error_message)
    """
    try:
        re.compile(pattern)
        return True, None
    except re.error as e:
        return False, str(e)


def search_by_regex_indexing(conn, regex_pattern: str, limit: int = 50):
    """
    Recherche par RegEx dans la TABLE D'INDEXAGE (titres → top_terms → postings).
    RAPIDE : cherche dans les mots normalisés et tokenisés.
    
    Processus (selon ton architecture) :
    1. Cherche d'abord dans les TITRES des livres (priorité 0)
    2. Récupère tous les mots de l'index (words table)
    3. Filtre avec Python regex
    4. Cherche dans top_terms (priorité 1)
    5. Cherche dans postings (priorité 2)
    
    Args:
        conn: connexion PostgreSQL
        regex_pattern: expression régulière Python
        limit: nombre max de résultats
        
    Returns:
        Liste de dict avec: id, title, author, language, source, matched_words, total_matches
    """
    # Valide le regex
    is_valid, error = validate_regex(regex_pattern)
    if not is_valid:
        raise ValueError(f"RegEx invalide: {error}")
    
    pattern = re.compile(regex_pattern, re.IGNORECASE)
    
    # 1) Récupère tous les mots de l'index
    with conn.cursor() as cur:
        cur.execute("SELECT id, w FROM words")
        all_words = cur.fetchall()
    
    # 2) Filtre les mots qui matchent le regex
    matching_word_ids = []
    matching_words = {}
    for word_id, word in all_words:
        if pattern.search(word):
            matching_word_ids.append(word_id)
            matching_words[word_id] = word
    
    if not matching_word_ids:
        return []
    
    print(f"[DEBUG] {len(matching_word_ids)} mots matchent le pattern '{regex_pattern}'")
    print(f"[DEBUG] Exemples: {list(matching_words.values())[:10]}")
    
    # 3) Cherche dans TITRES (priorité 0), top_terms (priorité 1) ET postings (priorité 2)
    sql = """
    WITH matching_titles AS (
        -- Cherche dans les titres (priorité 0)
        SELECT 
            b.id AS book_id,
            NULL::bigint AS word_id,
            NULL::text AS w,
            NULL::integer AS cnt,
            0 AS priority,
            'title'::text AS source
        FROM books b
        WHERE b.title ~* %s
    ),
    matching_top_terms AS (
        -- Cherche dans top_terms (priorité 1)
        SELECT 
            tt.book_id,
            tt.word_id,
            tt.w,
            tt.cnt,
            1 AS priority,
            'top_terms'::text AS source
        FROM top_terms tt
        WHERE tt.word_id = ANY(%s)
    ),
    matching_postings AS (
        -- Cherche dans postings (priorité 2)
        SELECT 
            p.book_id,
            p.word_id,
            w.w,
            p.cnt,
            2 AS priority,
            'postings'::text AS source
        FROM postings p
        JOIN words w ON w.id = p.word_id
        WHERE p.word_id = ANY(%s)
    ),
    all_matches AS (
        SELECT * FROM matching_titles
        UNION ALL
        SELECT * FROM matching_top_terms
        UNION ALL
        SELECT * FROM matching_postings
    ),
    book_aggregates AS (
        SELECT
            b.id,
            b.gutenberg_id,
            b.title,
            b.author,
            b.language,
            b.cover_url,
            MIN(am.priority) AS best_priority,
            CASE 
                WHEN MIN(am.priority) = 0 THEN 'title'
                WHEN MIN(am.priority) = 1 THEN 'top_terms'
                ELSE 'postings'
            END AS source,
            array_agg(DISTINCT am.w ORDER BY am.w) FILTER (WHERE am.w IS NOT NULL) AS matched_words,
            COALESCE(SUM(am.cnt), 0) AS total_matches,
            COUNT(DISTINCT am.word_id) FILTER (WHERE am.word_id IS NOT NULL) AS num_matched_words
        FROM all_matches am
        JOIN books b ON b.id = am.book_id
        GROUP BY b.id, b.gutenberg_id, b.title, b.author, b.language, b.cover_url
    )
    SELECT *
    FROM book_aggregates
    ORDER BY 
        best_priority ASC,           -- title avant top_terms avant postings
        num_matched_words DESC,      -- plus de mots matchés
        total_matches DESC,          -- plus d'occurrences
        title ASC
    LIMIT %s;
    """
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, (regex_pattern, matching_word_ids, matching_word_ids, limit))
        return cur.fetchall()


def search_by_regex_content(conn, regex_pattern: str, limit: int = 50, show_context: bool = True):
    """
    Recherche par RegEx dans le CONTENU TEXTUEL COMPLET (table book_texts).
    LENT : doit scanner tous les textes bruts originaux.
    
    Cette méthode trouve des patterns qui ne sont PAS dans l'index tokenisé,
    par exemple "Mr. Darcy", "221B Baker Street", etc.
    
    Args:
        conn: connexion PostgreSQL
        regex_pattern: expression régulière PostgreSQL
        limit: nombre max de résultats
        show_context: si True, extrait des snippets autour des matches
        
    Returns:
        Liste de dict avec: id, title, author, language, match_count, sample_matches, context
    """
    # Valide le regex avec Python d'abord
    is_valid, error = validate_regex(regex_pattern)
    if not is_valid:
        raise ValueError(f"RegEx invalide: {error}")
    
    # PostgreSQL regex (~* pour case-insensitive)
    if show_context:
        sql = """
        WITH matches AS (
            SELECT
                b.id,
                b.gutenberg_id,
                b.title,
                b.author,
                b.language,
                b.cover_url,
                bt.content,
                -- Compte approximatif des matches
                array_length(regexp_matches(bt.content, %s, 'gi'), 1) AS match_count
            FROM books b
            JOIN book_texts bt ON bt.book_id = b.id
            WHERE bt.content ~* %s
        ),
        with_samples AS (
            SELECT
                id,
                gutenberg_id,
                title,
                author,
                language,
                cover_url,
                COALESCE(match_count, 0) AS match_count,
                -- Extrait quelques exemples de matches
                (SELECT array_agg(matched)
                 FROM (
                     SELECT DISTINCT unnest(regexp_matches(content, %s, 'gi')) AS matched
                     LIMIT 10
                 ) AS sub
                ) AS sample_matches,
                -- Extrait des snippets de contexte
                (SELECT array_agg(snippet)
                 FROM (
                     SELECT substring(content FROM (match_pos - 50) FOR 150) AS snippet
                     FROM (
                         SELECT (regexp_matches(content, %s, 'gi'))[1] AS match,
                                strpos(content, (regexp_matches(content, %s, 'gi'))[1]) AS match_pos
                         LIMIT 3
                     ) AS positions
                 ) AS snippets
                ) AS context_snippets
            FROM matches
        )
        SELECT *
        FROM with_samples
        ORDER BY match_count DESC, title
        LIMIT %s;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (regex_pattern, regex_pattern, regex_pattern, 
                            regex_pattern, regex_pattern, limit))
            return cur.fetchall()
    else:
        # Version simplifiée sans contexte (plus rapide)
        sql = """
        SELECT
            b.id,
            b.gutenberg_id,
            b.title,
            b.author,
            b.language,
            b.cover_url,
            array_length(regexp_matches(bt.content, %s, 'gi'), 1) AS match_count
        FROM books b
        JOIN book_texts bt ON bt.book_id = b.id
        WHERE bt.content ~* %s
        ORDER BY match_count DESC NULLS LAST, b.title
        LIMIT %s;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (regex_pattern, regex_pattern, limit))
            return cur.fetchall()


def search_by_regex(
    conn, 
    regex_pattern: str, 
    mode: Literal['indexing', 'content'] = 'indexing',
    limit: int = 50,
    show_context: bool = False
):
    """
    Recherche par expression régulière.
    
    Args:
        conn: connexion PostgreSQL
        regex_pattern: expression régulière
        mode: 
            - 'indexing' : cherche dans top_terms → postings (rapide, mots tokenisés)
            - 'content' : cherche dans book_texts (lent, texte original)
        limit: nombre max de résultats
        show_context: pour mode 'content', affiche des snippets de contexte
        
    Returns:
        Liste de résultats avec métadonnées
        
    Examples:
        # Trouve tous les mots commençant par 'sh' et finissant par 'lock'
        >>> search_by_regex(conn, r'^sh.*lock$', mode='indexing')
        
        # Trouve tous les mots de 3 lettres dans l'indexage
        >>> search_by_regex(conn, r'^[a-z]{3}$', mode='indexing')
        
        # Cherche "Mr. Darcy" ou "Mr Darcy" dans le contenu original
        >>> search_by_regex(conn, r'Mr\\.?\\s+Darcy', mode='content', show_context=True)
    """
    if mode == 'indexing':
        return search_by_regex_indexing(conn, regex_pattern, limit)
    elif mode == 'content':
        return search_by_regex_content(conn, regex_pattern, limit, show_context)
    else:
        raise ValueError(f"Mode invalide: {mode}. Utilisez 'indexing' ou 'content'.")


def get_regex_statistics(conn, regex_pattern: str, mode: Literal['indexing', 'content'] = 'indexing'):
    """
    Retourne des statistiques sur une recherche regex SANS exécuter la recherche complète.
    Utile pour afficher "X mots matchent, Y livres affectés"
    """
    is_valid, error = validate_regex(regex_pattern)
    if not is_valid:
        return {"error": error, "valid": False}
    
    if mode == 'indexing':
        pattern = re.compile(regex_pattern, re.IGNORECASE)
        
        with conn.cursor() as cur:
            # Compte les mots qui matchent
            cur.execute("SELECT id, w FROM words")
            all_words = cur.fetchall()
            
            matching_word_ids = []
            matching_words = {}
            for wid, w in all_words:
                if pattern.search(w):
                    matching_word_ids.append(wid)
                    matching_words[wid] = w
            
            if not matching_word_ids:
                return {
                    "valid": True,
                    "mode": "indexing",
                    "matched_words_count": 0,
                    "in_titles": 0,
                    "in_top_terms": 0,
                    "in_postings": 0,
                    "sample_words": []
                }
            
            # Compte dans les titres
            cur.execute("""
                SELECT COUNT(*)
                FROM books
                WHERE title ~* %s
            """, (regex_pattern,))
            title_count = cur.fetchone()[0]
            
            # Compte dans top_terms
            cur.execute("""
                SELECT COUNT(DISTINCT book_id)
                FROM top_terms
                WHERE word_id = ANY(%s)
            """, (matching_word_ids,))
            top_terms_count = cur.fetchone()[0]
            
            # Compte dans postings
            cur.execute("""
                SELECT COUNT(DISTINCT book_id)
                FROM postings
                WHERE word_id = ANY(%s)
            """, (matching_word_ids,))
            postings_count = cur.fetchone()[0]
            
            return {
                "valid": True,
                "mode": "indexing",
                "matched_words_count": len(matching_word_ids),
                "in_titles": title_count,
                "in_top_terms": top_terms_count,
                "in_postings": postings_count,
                "sample_words": [matching_words[wid] for wid in matching_word_ids[:10]]
            }
    
    else:  # content
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM book_texts
                WHERE content ~* %s
            """, (regex_pattern,))
            
            book_count = cur.fetchone()[0]
            
            return {
                "valid": True,
                "mode": "content",
                "affected_books_count": book_count
            }


# ============================================================================
# Exemple d'utilisation et tests
# ============================================================================

if __name__ == "__main__":
    import os
    from psycopg2 import connect
    
    PGURL = os.environ.get("PGURL")
    if not PGURL:
        raise SystemExit("Erreur: définis PGURL")
    
    conn = connect(PGURL)
    
    print("="*80)
    print("🔍 TESTS DE RECHERCHE PAR REGEX")
    print("="*80)
    
    # Test 1: Recherche dans l'indexage (titres + top_terms + postings)
    print("\n1️⃣ Mode INDEXING: mots commençant par 'love'")
    print("-" * 80)
    stats = get_regex_statistics(conn, r'^love', mode='indexing')
    print(f"📊 Stats: {stats['matched_words_count']} mots, "
          f"{stats['in_titles']} dans titres, "
          f"{stats['in_top_terms']} dans top_terms, "
          f"{stats['in_postings']} dans postings")
    
    results = search_by_regex(conn, r'^love', mode='indexing', limit=5)
    for i, r in enumerate(results, 1):
        words_display = ', '.join(r['matched_words'][:5])
        if len(r['matched_words']) > 5:
            words_display += f" ... (+{len(r['matched_words']) - 5})"
        print(f"{i}. [{r['source']}] {r['title'][:45]}")
        print(f"   Mots: {words_display}")
        print(f"   {r['num_matched_words']} mots uniques, {r['total_matches']} occurrences")
    
    # Test 2: Mots de 3 lettres
    print("\n2️⃣ Mode INDEXING: mots de exactement 3 lettres")
    print("-" * 80)
    stats = get_regex_statistics(conn, r'^[a-z]{3}$', mode='indexing')
    print(f"📊 Stats: {stats}")
    results = search_by_regex(conn, r'^[a-z]{3}$', mode='indexing', limit=3)
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title'][:50]} ({r['num_matched_words']} mots de 3 lettres)")
    
    # Test 3: Pattern complexe - mots contenant 'sh' et 'ck'
    print("\n3️⃣ Mode INDEXING: mots contenant 'sh.*ck'")
    print("-" * 80)
    results = search_by_regex(conn, r'sh.*ck', mode='indexing', limit=5)
    for i, r in enumerate(results, 1):
        print(f"{i}. [{r['source']}] {r['title'][:45]}")
        print(f"   Mots: {', '.join(r['matched_words'][:8])}")
    
    # Test 4: Recherche dans le contenu (lent!)
    print("\n4️⃣ Mode CONTENT: pattern dans le texte brut")
    print("-" * 80)
    print("⚠️  Attention: peut être lent sur grande base...")
    
    # Example: cherche des noms propres avec titre (Mr., Mrs., Miss, etc.)
    pattern = r'\b(Mr|Mrs|Miss|Dr|Sir)\.?\s+[A-Z][a-z]+'
    try:
        stats = get_regex_statistics(conn, pattern, mode='content')
        print(f"📊 {stats['affected_books_count']} livres contiennent ce pattern")
        
        results = search_by_regex(conn, pattern, mode='content', limit=3, show_context=False)
        for i, r in enumerate(results, 1):
            print(f"{i}. {r['title'][:50]}")
            print(f"   {r.get('match_count', '?')} occurrences")
    except Exception as e:
        print(f"❌ Erreur: {e}")
    
    # Test 5: Comparaison indexing vs content
    print("\n5️⃣ COMPARAISON: 'love' dans indexing vs content")
    print("-" * 80)
    
    import time
    
    # Indexing
    start = time.time()
    results_idx = search_by_regex(conn, r'love', mode='indexing', limit=10)
    time_idx = time.time() - start
    print(f"⚡ Indexing: {len(results_idx)} résultats en {time_idx:.3f}s")
    
    # Content
    start = time.time()
    results_cnt = search_by_regex(conn, r'\blove\b', mode='content', limit=10, show_context=False)
    time_cnt = time.time() - start
    print(f"🐌 Content: {len(results_cnt)} résultats en {time_cnt:.3f}s")
    print(f"📊 Content est {time_cnt/time_idx:.1f}x plus lent")
    
    conn.close()
    print("\n" + "="*80)
    print("✅ Tests terminés!")