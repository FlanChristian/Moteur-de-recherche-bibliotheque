from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Count
from django.db import connection
from .models import Book, BookText, Word, Posting
import re


def home(request):
    """Page d'accueil avec les livres les plus consultés"""
    
    # Récupère tous les livres
    all_books = Book.objects.all().order_by('-word_count')[:50]
    
    # Pour les livres populaires, on prend ceux avec le plus de mots
    popular_books = all_books[:5]
    
    # Pour la section catégorie, on affiche les 10 premiers
    category_books = all_books[:10]
    
    # Si une recherche est effectuée
    search_query = request.GET.get('q', '').strip()
    if search_query:
        # Recherche dans le titre ou l'auteur
        category_books = Book.objects.filter(
            Q(title__icontains=search_query) | 
            Q(author__icontains=search_query)
        ).order_by('-word_count')[:20]
    
    context = {
        'popular_books': popular_books,
        'category_books': category_books,
        'search_query': search_query,
    }
    return render(request, 'search/home.html', context)


def book_detail(request, book_id):
    """Page de détail d'un livre"""
    book = get_object_or_404(Book, id=book_id)
    
    # Récupère le contenu du livre si disponible
    try:
        book_text = BookText.objects.get(book=book)
        content_preview = book_text.content[:500] + "..." if len(book_text.content) > 500 else book_text.content
    except BookText.DoesNotExist:
        content_preview = "Contenu non disponible"
    
    # Récupère les mots les plus fréquents du livre
    top_words = Posting.objects.filter(book=book).select_related('word').order_by('-cnt')[:10]
    
    # Livres similaires (même auteur)
    related_books = Book.objects.filter(author=book.author).exclude(id=book.id)[:5]
    
    context = {
        'book': book,
        'content_preview': content_preview,
        'top_words': top_words,
        'related_books': related_books,
    }
    return render(request, 'search/book_detail.html', context)


def search(request):
    """Recherche simple de livres (titre, auteur, mot-clé)"""
    query = request.GET.get('q', '').strip()
    search_type = request.GET.get('type', 'simple')  # simple ou advanced
    results = []
    stats = {}
    
    if query:
        if search_type == 'advanced':
            # Recherche avancée par RegEx
            results, stats = search_by_regex_view(query)
        else:
            # Recherche simple par mot-clé
            results, stats = search_by_keyword_view(query)
    
    context = {
        'query': query,
        'search_type': search_type,
        'results': results,
        'stats': stats,
    }
    return render(request, 'search/search_results.html', context)


def search_by_keyword_view(query):
    """
    Recherche par mot-clé avec priorités:
    1. Titre
    2. Top_terms
    3. Postings
    """
    # Normalise la requête (premier mot)
    from utils_text import tokenize
    tokens = tokenize(query.lower())
    q_norm = tokens[0] if tokens else query.lower()
    
    with connection.cursor() as cursor:
        # Requête SQL avec les 3 niveaux de priorité
        cursor.execute("""
            WITH all_matches AS (
                -- 1) Recherche dans les titres (priorité 0)
                SELECT
                    b.id,
                    b.gutenberg_id,
                    b.title,
                    b.author,
                    b.language,
                    b.cover_url,
                    NULL::integer AS match_count,
                    'title'::text AS source,
                    0 AS priority
                FROM books b
                WHERE LOWER(b.title) LIKE '%%' || %s || '%%'

                UNION ALL

                -- 2) Recherche dans top_terms (priorité 1)
                SELECT
                    b.id,
                    b.gutenberg_id,
                    b.title,
                    b.author,
                    b.language,
                    b.cover_url,
                    tt.cnt AS match_count,
                    'top_terms'::text AS source,
                    1 AS priority
                FROM top_terms tt
                JOIN books b ON b.id = tt.book_id
                WHERE LOWER(tt.w) = %s

                UNION ALL

                -- 3) Recherche dans postings (priorité 2)
                SELECT
                    b.id,
                    b.gutenberg_id,
                    b.title,
                    b.author,
                    b.language,
                    b.cover_url,
                    p.cnt AS match_count,
                    'postings'::text AS source,
                    2 AS priority
                FROM words w
                JOIN postings p ON p.word_id = w.id
                JOIN books b ON b.id = p.book_id
                WHERE LOWER(w.w) = %s
            ),
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
                language,
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
            LIMIT 50;
        """, [query.lower(), q_norm, q_norm])
        
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    # Statistiques
    stats = {
        'total': len(results),
        'in_titles': len([r for r in results if r['source'] == 'title']),
        'in_top_terms': len([r for r in results if r['source'] == 'top_terms']),
        'in_postings': len([r for r in results if r['source'] == 'postings']),
    }
    
    return results, stats


def search_by_regex_view(regex_pattern):
    """
    Recherche avancée par RegEx dans l'indexage (titres → top_terms → postings)
    """
    # Valide le regex
    try:
        pattern = re.compile(regex_pattern, re.IGNORECASE)
    except re.error as e:
        return [], {'error': f'RegEx invalide: {e}'}
    
    # Récupère tous les mots et filtre avec le regex
    all_words = Word.objects.all().values('id', 'w')
    matching_word_ids = [w['id'] for w in all_words if pattern.search(w['w'])]
    
    if not matching_word_ids:
        return [], {'total': 0, 'matched_words': 0}
    
    with connection.cursor() as cursor:
        cursor.execute("""
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
                best_priority ASC,
                num_matched_words DESC,
                total_matches DESC,
                title ASC
            LIMIT 50;
        """, [regex_pattern, matching_word_ids, matching_word_ids])
        
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    # Statistiques
    stats = {
        'total': len(results),
        'matched_words': len(matching_word_ids),
        'in_titles': len([r for r in results if r['source'] == 'title']),
        'in_top_terms': len([r for r in results if r['source'] == 'top_terms']),
        'in_postings': len([r for r in results if r['source'] == 'postings']),
    }
    
    return results, stats


def search_by_word(request):
    """Recherche de livres contenant un mot spécifique"""
    word_query = request.GET.get('word', '').strip().lower()
    results = []
    
    if word_query:
        # Trouve le mot dans la table words
        try:
            word_obj = Word.objects.get(w=word_query)
            # Récupère tous les livres contenant ce mot, triés par nombre d'occurrences
            postings = Posting.objects.filter(word=word_obj).select_related('book').order_by('-cnt')[:50]
            results = [{'book': p.book, 'count': p.cnt} for p in postings]
        except Word.DoesNotExist:
            results = []
    
    context = {
        'word': word_query,
        'results': results,
    }
    return render(request, 'search/word_search.html', context)