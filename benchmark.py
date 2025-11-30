"""
Benchmark de performance du moteur de recherche BiblioSearch
Ce script teste les performances des différentes fonctionnalités sans modifier la base de données.
"""

import time
import psycopg2
import statistics
from contextlib import contextmanager
import sys

# Configuration de la connexion
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'daar',
    'user': 'postgres',
    'password': 'postgres'
}

@contextmanager
def get_db_connection():
    """Gestionnaire de contexte pour les connexions DB"""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()

def format_time(seconds):
    """Formate le temps en ms si < 1s, sinon en secondes"""
    if seconds < 1:
        return f"{seconds * 1000:.2f} ms"
    return f"{seconds:.3f} s"

def benchmark_query(cursor, query, params=None, iterations=5):
    """Exécute une requête plusieurs fois et retourne les statistiques de temps"""
    times = []
    for _ in range(iterations):
        start = time.time()
        cursor.execute(query, params or ())
        cursor.fetchall()  # Force l'exécution complète
        elapsed = time.time() - start
        times.append(elapsed)
    
    return {
        'min': min(times),
        'max': max(times),
        'avg': statistics.mean(times),
        'median': statistics.median(times),
        'iterations': iterations
    }

def print_results(name, stats):
    """Affiche les résultats d'un benchmark"""
    print(f"\n  {name}:")
    print(f"    Min:     {format_time(stats['min'])}")
    print(f"    Avg:     {format_time(stats['avg'])}")
    print(f"    Median:  {format_time(stats['median'])}")
    print(f"    Max:     {format_time(stats['max'])}")
    print(f"    ({stats['iterations']} itérations)")

def benchmark_search_queries():
    """Benchmark des différentes recherches"""
    print("\n" + "="*70)
    print("BENCHMARK: RECHERCHE DE LIVRES")
    print("="*70)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Recherche simple par titre
        print("\n1. Recherche par titre (LIKE '%%love%%'):")
        query = """
            SELECT id, title, author FROM books 
            WHERE LOWER(title) LIKE '%%love%%'
        """
        stats = benchmark_query(cursor, query)
        print_results("Résultat", stats)
        cursor.execute(query)
        print(f"    Résultats trouvés: {len(cursor.fetchall())}")
        
        # 2. Recherche dans top_terms
        print("\n2. Recherche dans top_terms (mot: 'love'):")
        query = """
            SELECT b.id, b.title, b.author, tt.cnt
            FROM top_terms tt
            JOIN books b ON b.id = tt.book_id
            WHERE LOWER(tt.w) = 'love'
            ORDER BY tt.cnt DESC
        """
        stats = benchmark_query(cursor, query)
        print_results("Résultat", stats)
        cursor.execute(query)
        print(f"    Résultats trouvés: {len(cursor.fetchall())}")
        
        # 3. Recherche dans postings (index complet)
        print("\n3. Recherche dans postings (mot: 'adventure'):")
        query = """
            SELECT b.id, b.title, b.author, p.cnt
            FROM words w
            JOIN postings p ON p.word_id = w.id
            JOIN books b ON b.id = p.book_id
            WHERE LOWER(w.w) = 'adventure'
            ORDER BY p.cnt DESC
        """
        stats = benchmark_query(cursor, query)
        print_results("Résultat", stats)
        cursor.execute(query)
        print(f"    Résultats trouvés: {len(cursor.fetchall())}")
        
        # 4. Recherche avec priorités (3 niveaux)
        print("\n4. Recherche multi-niveaux (titre + top_terms + postings):")
        query = """
            WITH all_matches AS (
                SELECT b.id, b.title, b.author, 'title' as source, 0 as priority
                FROM books b
                WHERE LOWER(b.title) LIKE '%%time%%'
                
                UNION ALL
                
                SELECT b.id, b.title, b.author, 'top_terms' as source, 1 as priority
                FROM top_terms tt
                JOIN books b ON b.id = tt.book_id
                WHERE LOWER(tt.w) = 'time'
                
                UNION ALL
                
                SELECT b.id, b.title, b.author, 'postings' as source, 2 as priority
                FROM words w
                JOIN postings p ON p.word_id = w.id
                JOIN books b ON b.id = p.book_id
                WHERE LOWER(w.w) = 'time'
            )
            SELECT DISTINCT ON (id) *
            FROM all_matches
            ORDER BY id, priority ASC
        """
        stats = benchmark_query(cursor, query, iterations=3)
        print_results("Résultat", stats)
        cursor.execute(query)
        print(f"    Résultats trouvés: {len(cursor.fetchall())}")
        
        # 5. Recherche RegEx
        print("\n5. Recherche RegEx (motif: '^love'):")
        query = """
            SELECT b.id, b.title, b.author, COUNT(DISTINCT w.id) as word_count
            FROM words w
            JOIN postings p ON p.word_id = w.id
            JOIN books b ON b.id = p.book_id
            WHERE w.w ~ '^love'
            GROUP BY b.id, b.title, b.author
            ORDER BY word_count DESC
        """
        stats = benchmark_query(cursor, query, iterations=3)
        print_results("Résultat", stats)
        cursor.execute(query)
        print(f"    Résultats trouvés: {len(cursor.fetchall())}")

def benchmark_statistics():
    """Benchmark des pages de statistiques"""
    print("\n" + "="*70)
    print("BENCHMARK: STATISTIQUES")
    print("="*70)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Stats de base (comptages simples)
        print("\n1. Statistiques de base (COUNT):")
        queries = [
            ("Nombre de livres", "SELECT COUNT(*) FROM books"),
            ("Nombre d'auteurs", "SELECT COUNT(DISTINCT author) FROM books WHERE author IS NOT NULL"),
            ("Nombre de langues", "SELECT COUNT(DISTINCT language) FROM books WHERE language IS NOT NULL"),
            ("Total de mots", "SELECT SUM(word_count) FROM books WHERE word_count IS NOT NULL"),
        ]
        
        for name, query in queries:
            stats = benchmark_query(cursor, query, iterations=10)
            print_results(name, stats)
        
        # 2. Top mots globaux (optimisé avec top_terms)
        print("\n2. Top 20 mots globaux (via top_terms):")
        query = """
            SELECT tt.w, SUM(tt.cnt) as total_count, COUNT(DISTINCT tt.book_id) as book_count
            FROM top_terms tt
            GROUP BY tt.w
            ORDER BY total_count DESC
            LIMIT 20
        """
        stats = benchmark_query(cursor, query, iterations=5)
        print_results("Résultat", stats)
        
        # 3. Top auteurs
        print("\n3. Top 10 auteurs:")
        query = """
            SELECT author, COUNT(*) as count
            FROM books
            WHERE author IS NOT NULL
            GROUP BY author
            ORDER BY count DESC
            LIMIT 10
        """
        stats = benchmark_query(cursor, query, iterations=5)
        print_results("Résultat", stats)
        
        # 4. Estimation rapide postings (pg_class)
        print("\n4. Estimation nombre de postings (pg_class):")
        query = """
            SELECT reltuples::bigint AS estimate 
            FROM pg_class 
            WHERE relname = 'postings'
        """
        stats = benchmark_query(cursor, query, iterations=10)
        print_results("Résultat", stats)

def benchmark_jaccard():
    """Benchmark du graphe de Jaccard"""
    print("\n" + "="*70)
    print("BENCHMARK: GRAPHE DE JACCARD")
    print("="*70)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Stats de similarité
        print("\n1. Statistiques de similarité:")
        query = """
            SELECT MIN(similarity), AVG(similarity), MAX(similarity)
            FROM jaccard_edges
        """
        stats = benchmark_query(cursor, query, iterations=5)
        print_results("Résultat", stats)
        
        # 2. Top 20 paires similaires
        print("\n2. Top 20 paires les plus similaires:")
        query = """
            SELECT b1.id, b1.title, b2.id, b2.title, je.similarity
            FROM jaccard_edges je
            JOIN books b1 ON b1.id = je.book_id1
            JOIN books b2 ON b2.id = je.book_id2
            ORDER BY je.similarity DESC
            LIMIT 20
        """
        stats = benchmark_query(cursor, query, iterations=5)
        print_results("Résultat", stats)
        
        # 3. Livres les plus connectés (optimisé)
        print("\n3. Top 15 livres les plus connectés:")
        query = """
            WITH degrees AS (
                SELECT book_id1 as book_id, COUNT(*) as degree
                FROM jaccard_edges
                GROUP BY book_id1
                UNION ALL
                SELECT book_id2 as book_id, COUNT(*) as degree
                FROM jaccard_edges
                GROUP BY book_id2
            ),
            book_degrees AS (
                SELECT book_id, SUM(degree) as total_degree
                FROM degrees
                GROUP BY book_id
                ORDER BY total_degree DESC
                LIMIT 15
            )
            SELECT b.id, b.title, b.author, bd.total_degree
            FROM book_degrees bd
            JOIN books b ON b.id = bd.book_id
            ORDER BY bd.total_degree DESC
        """
        stats = benchmark_query(cursor, query, iterations=3)
        print_results("Résultat", stats)
        
        # 4. Récupération arêtes pour un livre spécifique
        print("\n4. Arêtes d'un livre spécifique (book_id=1):")
        query = """
            SELECT book_id2, similarity
            FROM jaccard_edges
            WHERE book_id1 = 1
            UNION ALL
            SELECT book_id1, similarity
            FROM jaccard_edges
            WHERE book_id2 = 1
            ORDER BY similarity DESC
            LIMIT 10
        """
        stats = benchmark_query(cursor, query, iterations=5)
        print_results("Résultat", stats)
        
        # 5. Estimation du nombre d'arêtes (pg_class)
        print("\n5. Estimation nombre d'arêtes (pg_class):")
        query = """
            SELECT reltuples::bigint AS estimate 
            FROM pg_class 
            WHERE relname = 'jaccard_edges'
        """
        stats = benchmark_query(cursor, query, iterations=10)
        print_results("Résultat", stats)

def benchmark_centrality():
    """Benchmark des métriques de centralité"""
    print("\n" + "="*70)
    print("BENCHMARK: MÉTRIQUES DE CENTRALITÉ")
    print("="*70)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Top 10 par PageRank
        print("\n1. Top 10 livres par PageRank:")
        query = """
            SELECT b.id, b.title, bc.pagerank
            FROM books b
            JOIN book_centrality bc ON bc.book_id = b.id
            ORDER BY bc.pagerank DESC
            LIMIT 10
        """
        stats = benchmark_query(cursor, query, iterations=5)
        print_results("Résultat", stats)
        
        # 2. Top 10 par Closeness
        print("\n2. Top 10 livres par Closeness:")
        query = """
            SELECT b.id, b.title, bc.closeness
            FROM books b
            JOIN book_centrality bc ON bc.book_id = b.id
            ORDER BY bc.closeness DESC
            LIMIT 10
        """
        stats = benchmark_query(cursor, query, iterations=5)
        print_results("Résultat", stats)
        
        # 3. Top 10 par Betweenness
        print("\n3. Top 10 livres par Betweenness:")
        query = """
            SELECT b.id, b.title, bc.betweenness
            FROM books b
            JOIN book_centrality bc ON bc.book_id = b.id
            ORDER BY bc.betweenness DESC
            LIMIT 10
        """
        stats = benchmark_query(cursor, query, iterations=5)
        print_results("Résultat", stats)
        
        # 4. Recherche avec tri par PageRank
        print("\n4. Recherche avec tri PageRank (mot: 'life'):")
        query = """
            SELECT b.id, b.title, b.author, p.cnt, bc.pagerank
            FROM words w
            JOIN postings p ON p.word_id = w.id
            JOIN books b ON b.id = p.book_id
            LEFT JOIN book_centrality bc ON bc.book_id = b.id
            WHERE LOWER(w.w) = 'life'
            ORDER BY bc.pagerank DESC NULLS LAST
            LIMIT 20
        """
        stats = benchmark_query(cursor, query, iterations=5)
        print_results("Résultat", stats)

def benchmark_database_info():
    """Affiche les informations sur la base de données"""
    print("\n" + "="*70)
    print("INFORMATIONS BASE DE DONNÉES")
    print("="*70)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Nombre de livres
        cursor.execute("SELECT COUNT(*) FROM books")
        nb_books = cursor.fetchone()[0]
        
        # Nombre de mots indexés
        cursor.execute("SELECT COUNT(*) FROM words")
        nb_words = cursor.fetchone()[0]
        
        # Nombre de mots dans top_terms
        cursor.execute("SELECT COUNT(DISTINCT w) FROM top_terms")
        nb_top_terms = cursor.fetchone()[0]
        
        # Estimation postings
        cursor.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = 'postings'")
        nb_postings = cursor.fetchone()[0]
        
        # Nombre d'arêtes Jaccard
        cursor.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = 'jaccard_edges'")
        nb_edges = cursor.fetchone()[0]
        
        # Total mots
        cursor.execute("SELECT SUM(word_count) FROM books")
        total_words = cursor.fetchone()[0]
        
        print(f"\n  Livres indexés:        {nb_books:,}")
        print(f"  Mots uniques (words):  {nb_words:,}")
        print(f"  Top terms:             {nb_top_terms:,}")
        print(f"  Postings (estimé):     {nb_postings:,}")
        print(f"  Arêtes Jaccard:        {nb_edges:,}")
        print(f"  Total mots:            {total_words:,}")
        print(f"\n  Densité du graphe:     {(100 * nb_edges / (nb_books * (nb_books - 1) // 2)):.2f}%")

def main():
    """Fonction principale du benchmark"""
    print("\n" + "="*70)
    print("   BENCHMARK MOTEUR DE RECHERCHE BIBLIOSEARCH")
    print("="*70)
    print("\nCe benchmark teste les performances sans modifier la base de données.")
    print("Les requêtes sont exécutées en lecture seule (SELECT uniquement).")
    
    try:
        # Affiche les infos de la BDD
        benchmark_database_info()
        
        # Lance les benchmarks
        benchmark_search_queries()
        benchmark_statistics()
        benchmark_jaccard()
        benchmark_centrality()
        
        print("\n" + "="*70)
        print("BENCHMARK TERMINÉ AVEC SUCCÈS")
        print("="*70)
        print("\nAucune modification n'a été apportée à la base de données.")
        print("Tous les tests ont été effectués en lecture seule.\n")
        
    except psycopg2.Error as e:
        print(f"\n❌ Erreur de connexion à la base de données: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erreur lors du benchmark: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
