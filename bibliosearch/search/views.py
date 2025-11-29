from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Count
from django.db import connection
from django.http import JsonResponse
from .models import Book, BookText, Word, Posting
import re


def home(request):
    """Page d'accueil avec les livres les plus consultés"""
    
    # Filtres
    language_filter = request.GET.get('lang', '')
    sort_by = request.GET.get('sort', 'popular')  # popular, recent, title, pagerank
    
    # Récupère tous les livres
    all_books = Book.objects.all()
    
    # Applique le filtre de langue
    if language_filter:
        all_books = all_books.filter(language=language_filter)
    
    # Applique le tri
    if sort_by == 'title':
        all_books = all_books.order_by('title')
    elif sort_by == 'recent':
        all_books = all_books.order_by('-id')
    elif sort_by == 'pagerank':
        # Tri par PageRank (utilise SQL brut pour joindre avec book_centrality)
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT b.id, b.title, b.author, b.language, b.cover_url, b.word_count, bc.pagerank
                FROM books b
                LEFT JOIN book_centrality bc ON bc.book_id = b.id
                ORDER BY bc.pagerank DESC NULLS LAST
                LIMIT 50
            """)
            all_books = [
                type('Book', (), {
                    'id': row[0], 'title': row[1], 'author': row[2],
                    'language': row[3], 'cover_url': row[4], 'word_count': row[5],
                    'pagerank': row[6]
                })() for row in cursor.fetchall()
            ]
    else:  # popular
        all_books = all_books.order_by('-word_count')
    
    if sort_by != 'pagerank':
        all_books = all_books[:50]
    
    # Pour les livres populaires, utilise PageRank si disponible, sinon word_count
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT b.id, b.title, b.author, b.language, b.cover_url, 
                   COALESCE(bc.pagerank, 0) as score
            FROM books b
            LEFT JOIN book_centrality bc ON bc.book_id = b.id
            ORDER BY score DESC
            LIMIT 5
        """)
        popular_books = [
            type('Book', (), {
                'id': row[0], 'title': row[1], 'author': row[2],
                'language': row[3], 'cover_url': row[4]
            })() for row in cursor.fetchall()
        ]
    
    # Pour la section catégorie, on affiche les 10 premiers filtrés
    category_books = all_books[:10]
    
    # Statistiques de la bibliothèque
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM books")
        total_books = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT language) FROM books WHERE language IS NOT NULL")
        total_languages = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(word_count) FROM books WHERE word_count IS NOT NULL")
        total_words = cursor.fetchone()[0] or 0
    
    # Langues disponibles
    available_languages = Book.objects.values_list('language', flat=True).distinct().order_by('language')
    
    # Si une recherche est effectuée
    search_query = request.GET.get('q', '').strip()
    search_type = request.GET.get('type', 'simple')  # 'simple' ou 'regex'
    search_sort = request.GET.get('search_sort', 'relevance')  # tri des résultats de recherche
    search_results = []
    search_stats = {}
    
    if search_query:
        # Choisit le type de recherche
        if search_type == 'regex':
            search_results, search_stats = search_by_regex_view(search_query, search_sort)
        else:
            search_results, search_stats = search_by_keyword_view(search_query, search_sort)
        # Si on a des résultats, on les affiche au lieu des catégories
        if search_results:
            category_books = []  # On cache les catégories quand on a des résultats
    
    context = {
        'popular_books': popular_books,
        'category_books': category_books,
        'search_query': search_query,
        'search_type': search_type,
        'search_sort': search_sort,
        'search_results': search_results,
        'search_stats': search_stats,
        'available_languages': available_languages,
        'current_language': language_filter,
        'current_sort': sort_by,
        'total_books': total_books,
        'total_languages': total_languages,
        'total_words': total_words,
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
    except Exception as e:
        content_preview = f"Erreur lors du chargement: {str(e)}"
    
    # Récupère les mots les plus fréquents du livre via SQL brut (évite le problème de clé primaire)
    top_words = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT w, cnt
                FROM top_terms
                WHERE book_id = %s
                ORDER BY rnk ASC
                LIMIT 10
            """, [book.id])
            top_words = [{'word': row[0], 'count': row[1]} for row in cursor.fetchall()]
    except Exception as e:
        print(f"Erreur chargement top_words: {e}")
    
    # Livres similaires (même auteur)
    related_books = []
    try:
        if book.author:
            related_books = Book.objects.filter(author=book.author).exclude(id=book.id)[:5]
    except Exception as e:
        print(f"Erreur chargement related_books: {e}")
    
    # Livres similaires (graphe de Jaccard) - suggestions basées sur la similarité de contenu
    jaccard_similar_books = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    b.id,
                    b.title,
                    b.author,
                    b.language,
                    b.cover_url,
                    je.similarity
                FROM (
                    SELECT book_id2 as similar_id, similarity
                    FROM jaccard_edges
                    WHERE book_id1 = %s
                    UNION ALL
                    SELECT book_id1 as similar_id, similarity
                    FROM jaccard_edges
                    WHERE book_id2 = %s
                ) je
                JOIN books b ON b.id = je.similar_id
                ORDER BY je.similarity DESC
                LIMIT 5
            """, [book.id, book.id])
            jaccard_similar_books = [
                {
                    'id': row[0],
                    'title': row[1],
                    'author': row[2],
                    'language': row[3],
                    'cover_url': row[4],
                    'similarity': row[5]
                }
                for row in cursor.fetchall()
            ]
    except Exception as e:
        print(f"Erreur chargement jaccard_similar_books: {e}")
    
    # Navigation entre livres (précédent/suivant par ID)
    try:
        prev_book = Book.objects.filter(id__lt=book.id).order_by('-id').first()
        next_book = Book.objects.filter(id__gt=book.id).order_by('id').first()
    except Exception as e:
        print(f"Erreur chargement navigation: {e}")
        prev_book = None
        next_book = None
    
    context = {
        'book': book,
        'content_preview': content_preview,
        'top_words': top_words,
        'related_books': related_books,
        'jaccard_similar_books': jaccard_similar_books,
        'prev_book': prev_book,
        'next_book': next_book,
    }
    return render(request, 'search/book_detail.html', context)


def search(request):
    """Recherche simple de livres (titre, auteur, mot-clé)"""
    query = request.GET.get('q', '').strip()
    search_type = request.GET.get('type', 'simple')  # simple ou advanced
    sort_by = request.GET.get('sort', 'relevance')  # relevance, pagerank, occurrences, title
    results = []
    stats = {}
    
    if query:
        if search_type == 'advanced':
            # Recherche avancée par RegEx
            results, stats = search_by_regex_view(query, sort_by)
        else:
            # Recherche simple par mot-clé
            results, stats = search_by_keyword_view(query, sort_by)
    
    context = {
        'query': query,
        'search_type': search_type,
        'sort_by': sort_by,
        'results': results,
        'stats': stats,
    }
    return render(request, 'search/search_result.html', context)


def search_by_keyword_view(query, sort_by='relevance'):
    """
    Recherche par mot-clé avec priorités:
    1. Titre
    2. Top_terms
    3. Postings
    
    Options de tri:
    - relevance: priorité + pagerank + occurrences (défaut)
    - pagerank: par PageRank
    - occurrences: par nombre d'occurrences
    - title: par titre alphabétique
    - closeness: par closeness centrality
    - betweenness: par betweenness centrality
    """
    # Normalise la requête (premier mot)
    from .utils_text import tokenize
    tokens = tokenize(query.lower())
    q_norm = tokens[0] if tokens else query.lower()
    
    # Définir l'ordre de tri SQL selon le choix
    if sort_by == 'pagerank':
        order_clause = "bc.pagerank DESC NULLS LAST, d.title ASC"
    elif sort_by == 'occurrences':
        order_clause = "COALESCE(d.match_count, 0) DESC, d.title ASC"
    elif sort_by == 'title':
        order_clause = "d.title ASC"
    elif sort_by == 'closeness':
        order_clause = "bc.closeness DESC NULLS LAST, d.title ASC"
    elif sort_by == 'betweenness':
        order_clause = "bc.betweenness DESC NULLS LAST, d.title ASC"
    else:  # relevance (défaut)
        order_clause = "d.priority ASC, bc.pagerank DESC NULLS LAST, COALESCE(d.match_count, 0) DESC, d.title ASC"
    
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
                d.id,
                d.gutenberg_id,
                d.title,
                d.author,
                d.language,
                d.cover_url,
                d.match_count,
                d.source,
                d.priority,
                COALESCE(bc.pagerank, 0) as pagerank,
                COALESCE(bc.closeness, 0) as closeness,
                COALESCE(bc.betweenness, 0) as betweenness
            FROM deduplicated d
            LEFT JOIN book_centrality bc ON bc.book_id = d.id
            WHERE d.rn = 1
            ORDER BY {}
            LIMIT 50;
        """.format(order_clause), [query.lower(), q_norm, q_norm])
        
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


def search_by_regex_view(regex_pattern, sort_by='relevance'):
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
    
    # Définir l'ordre de tri SQL selon le choix
    if sort_by == 'pagerank':
        order_clause = "COALESCE(bc.pagerank, 0) DESC, b.title ASC"
    elif sort_by == 'occurrences':
        order_clause = "COUNT(*) DESC, b.title ASC"
    elif sort_by == 'title':
        order_clause = "b.title ASC"
    elif sort_by == 'closeness':
        order_clause = "COALESCE(bc.closeness, 0) DESC, b.title ASC"
    elif sort_by == 'betweenness':
        order_clause = "COALESCE(bc.betweenness, 0) DESC, b.title ASC"
    else:  # relevance (défaut)
        order_clause = "COUNT(*) DESC, COALESCE(bc.pagerank, 0) DESC, b.title ASC"
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT DISTINCT
                b.id,
                b.gutenberg_id,
                b.title,
                b.author,
                b.language,
                b.cover_url,
                array_agg(DISTINCT w.w) AS matched_words,
                COALESCE(bc.pagerank, 0) as pagerank,
                COALESCE(bc.closeness, 0) as closeness,
                COALESCE(bc.betweenness, 0) as betweenness
            FROM words w
            JOIN postings p ON p.word_id = w.id
            JOIN books b ON b.id = p.book_id
            LEFT JOIN book_centrality bc ON bc.book_id = b.id
            WHERE w.w ~ %s
            GROUP BY b.id, b.gutenberg_id, b.title, b.author, b.language, b.cover_url, bc.pagerank, bc.closeness, bc.betweenness
            ORDER BY {}
            LIMIT 50;
        """.format(order_clause), [regex_pattern])
        
        columns = [col[0] for col in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    # Statistiques
    stats = {
        'total': len(results),
        'matched_words': len(matching_word_ids),
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


def statistics(request):
    """Page de statistiques de la bibliothèque"""
    with connection.cursor() as cursor:
        # Stats de base
        cursor.execute("SELECT COUNT(*) FROM books")
        total_books = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT author) FROM books WHERE author IS NOT NULL")
        total_authors = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT language) FROM books WHERE language IS NOT NULL")
        total_languages = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(word_count) FROM books WHERE word_count IS NOT NULL")
        total_words = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM words")
        unique_words = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM postings")
        total_postings = cursor.fetchone()[0]
        
        # Top 10 auteurs
        cursor.execute("""
            SELECT author, COUNT(*) as count
            FROM books
            WHERE author IS NOT NULL
            GROUP BY author
            ORDER BY count DESC
            LIMIT 10
        """)
        top_authors = [{'author': row[0], 'count': row[1]} for row in cursor.fetchall()]
        
        # Distribution par langue
        cursor.execute("""
            SELECT language, COUNT(*) as count
            FROM books
            WHERE language IS NOT NULL
            GROUP BY language
            ORDER BY count DESC
        """)
        language_distribution = [{'language': row[0], 'count': row[1]} for row in cursor.fetchall()]
        
        # Top 20 mots globaux (avec nombre de livres)
        cursor.execute("""
            SELECT w.w, SUM(p.cnt) as total_count, COUNT(DISTINCT p.book_id) as book_count
            FROM words w
            JOIN postings p ON p.word_id = w.id
            GROUP BY w.w
            ORDER BY total_count DESC
            LIMIT 20
        """)
        top_global_words = [{'word': row[0], 'total_count': row[1], 'book_count': row[2]} for row in cursor.fetchall()]
        
        # Livres les plus longs
        longest_books = Book.objects.filter(word_count__isnull=False).order_by('-word_count')[:15]
    
    context = {
        'total_books': total_books,
        'total_authors': total_authors,
        'total_languages': total_languages,
        'total_words': total_words,
        'unique_words': unique_words,
        'total_postings': total_postings,
        'top_authors': top_authors,
        'language_distribution': language_distribution,
        'top_global_words': top_global_words,
        'longest_books': longest_books,
    }
    return render(request, 'search/statistics.html', context)


def autocomplete(request):
    """API d'autocomplete pour les suggestions de recherche"""
    query = request.GET.get('q', '').strip().lower()
    
    if len(query) < 2:
        return JsonResponse([], safe=False)
    
    suggestions = []
    
    # 1. Recherche dans les titres de livres
    books = Book.objects.filter(title__icontains=query)[:5]
    for book in books:
        suggestions.append({
            'text': book.title,
            'type': 'book'
        })
    
    # 2. Recherche dans les auteurs
    authors = Book.objects.filter(author__icontains=query).values('author').distinct()[:5]
    for author in authors:
        if author['author']:
            suggestions.append({
                'text': author['author'],
                'type': 'author'
            })
    
    # 3. Recherche dans les mots indexés
    from .utils_text import tokenize
    tokens = tokenize(query)
    q_norm = tokens[0] if tokens else query
    
    words = Word.objects.filter(w__istartswith=q_norm)[:5]
    for word in words:
        suggestions.append({
            'text': word.w,
            'type': 'word'
        })
    
    # Limiter à 10 suggestions au total
    return JsonResponse(suggestions[:10], safe=False)


def jaccard_graph(request):
    """Page de visualisation du graphe de Jaccard"""
    
    # Statistiques du graphe
    with connection.cursor() as cursor:
        # Nombre de livres et d'arêtes
        cursor.execute("SELECT COUNT(*) FROM books")
        nb_books = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM jaccard_edges")
        nb_edges = cursor.fetchone()[0]
        
        # Stats sur les similarités
        cursor.execute("""
            SELECT 
                MIN(similarity),
                AVG(similarity),
                MAX(similarity)
            FROM jaccard_edges
        """)
        sim_stats = cursor.fetchone()
        
        # Top 20 paires les plus similaires
        cursor.execute("""
            SELECT 
                b1.id as id1,
                b1.title as title1,
                b1.author as author1,
                b2.id as id2,
                b2.title as title2,
                b2.author as author2,
                je.similarity
            FROM jaccard_edges je
            JOIN books b1 ON b1.id = je.book_id1
            JOIN books b2 ON b2.id = je.book_id2
            ORDER BY je.similarity DESC
            LIMIT 20
        """)
        top_pairs = cursor.fetchall()
        
        # Top 15 livres les plus connectés
        cursor.execute("""
            WITH degrees AS (
                SELECT book_id1 as book_id FROM jaccard_edges
                UNION ALL
                SELECT book_id2 FROM jaccard_edges
            )
            SELECT 
                b.id,
                b.title,
                b.author,
                COUNT(*) as degree,
                AVG(CASE 
                    WHEN je1.book_id1 = b.id THEN je1.similarity 
                    ELSE je2.similarity 
                END) as avg_similarity
            FROM degrees d
            JOIN books b ON b.id = d.book_id
            LEFT JOIN jaccard_edges je1 ON je1.book_id1 = b.id
            LEFT JOIN jaccard_edges je2 ON je2.book_id2 = b.id
            GROUP BY b.id, b.title, b.author
            ORDER BY degree DESC, avg_similarity DESC
            LIMIT 15
        """)
        top_connected = cursor.fetchall()
        
        # Données pour le graphe (tous les noeuds et arêtes)
        cursor.execute("""
            SELECT id, title, author
            FROM books
            ORDER BY id
        """)
        all_books = cursor.fetchall()
        
        cursor.execute("""
            SELECT book_id1, book_id2, similarity
            FROM jaccard_edges
            ORDER BY similarity DESC
        """)
        all_edges = cursor.fetchall()
    
    context = {
        'nb_books': nb_books,
        'nb_edges': nb_edges,
        'max_edges': nb_books * (nb_books - 1) // 2,
        'edge_percentage': (100 * nb_edges / (nb_books * (nb_books - 1) // 2)) if nb_books > 1 else 0,
        'min_sim': sim_stats[0] if sim_stats[0] else 0,
        'avg_sim': sim_stats[1] if sim_stats[1] else 0,
        'max_sim': sim_stats[2] if sim_stats[2] else 0,
        'top_pairs': [
            {
                'id1': row[0],
                'title1': row[1],
                'author1': row[2],
                'id2': row[3],
                'title2': row[4],
                'author2': row[5],
                'similarity': row[6]
            }
            for row in top_pairs
        ],
        'top_connected': [
            {
                'id': row[0],
                'title': row[1],
                'author': row[2],
                'degree': row[3],
                'avg_similarity': row[4]
            }
            for row in top_connected
        ],
        'graph_data': {
            'nodes': [
                {'id': row[0], 'title': row[1], 'author': row[2]}
                for row in all_books
            ],
            'edges': [
                {'source': row[0], 'target': row[1], 'weight': row[2]}
                for row in all_edges
            ]
        }
    }
    
    return render(request, 'search/jaccard_graph.html', context)
