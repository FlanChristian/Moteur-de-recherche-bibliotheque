#!/usr/bin/env python3
"""
Affiche les statistiques du graphe de Jaccard.
"""
import os
import psycopg2

PGURL = os.environ.get("PGURL")
if not PGURL:
    raise SystemExit("Erreur: définis la variable d'environnement PGURL")


def show_jaccard_stats(conn):
    """Affiche les statistiques du graphe."""
    with conn.cursor() as cur:
        # Statistiques générales
        print("\n" + "="*60)
        print("📊 STATISTIQUES DU GRAPHE DE JACCARD")
        print("="*60)
        
        cur.execute("SELECT COUNT(*) FROM books;")
        nb_books = cur.fetchone()[0]
        print(f"\n📚 Nombre de livres: {nb_books}")
        
        cur.execute("SELECT COUNT(*) FROM jaccard_edges;")
        nb_edges = cur.fetchone()[0]
        max_edges = nb_books * (nb_books - 1) // 2
        print(f"🔗 Nombre d'arêtes: {nb_edges} / {max_edges} ({100*nb_edges/max_edges:.2f}%)")
        
        # Statistiques sur les distances/similarités
        cur.execute("""
            SELECT 
                MIN(dist) as min_dist,
                AVG(dist) as avg_dist,
                MAX(dist) as max_dist,
                MIN(similarity) as min_sim,
                AVG(similarity) as avg_sim,
                MAX(similarity) as max_sim
            FROM jaccard_edges;
        """)
        row = cur.fetchone()
        if row and row[0] is not None:
            print(f"\n📏 Distance:")
            print(f"   Min: {row[0]:.4f}  |  Moyenne: {row[1]:.4f}  |  Max: {row[2]:.4f}")
            print(f"📈 Similarité:")
            print(f"   Min: {row[3]:.4f}  |  Moyenne: {row[4]:.4f}  |  Max: {row[5]:.4f}")
        
        # Top 10 paires les plus similaires
        print("\n" + "="*60)
        print("🏆 TOP 10 PAIRES LES PLUS SIMILAIRES")
        print("="*60)
        cur.execute("""
            SELECT 
                b1.title, b1.author,
                b2.title, b2.author,
                je.similarity
            FROM jaccard_edges je
            JOIN books b1 ON b1.id = je.book_id1
            JOIN books b2 ON b2.id = je.book_id2
            ORDER BY je.similarity DESC
            LIMIT 10;
        """)
        
        for i, (t1, a1, t2, a2, sim) in enumerate(cur.fetchall(), 1):
            print(f"\n{i}. Similarité: {sim:.4f}")
            print(f"   📖 {t1[:50]} - {a1}")
            print(f"   📖 {t2[:50]} - {a2}")
        
        # Livres les plus connectés (degree)
        print("\n" + "="*60)
        print("🌟 TOP 10 LIVRES LES PLUS CONNECTÉS (DEGREE)")
        print("="*60)
        cur.execute("""
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
            LIMIT 10;
        """)
        
        for i, (book_id, title, author, degree, avg_sim) in enumerate(cur.fetchall(), 1):
            print(f"{i}. {title[:50]} - {author}")
            print(f"   🔗 Voisins: {degree}  |  📊 Similarité moyenne: {avg_sim:.4f}")
        
        # Distribution des degrés
        print("\n" + "="*60)
        print("📊 DISTRIBUTION DES DEGRÉS")
        print("="*60)
        cur.execute("""
            WITH degrees AS (
                SELECT book_id1 as book_id FROM jaccard_edges
                UNION ALL
                SELECT book_id2 FROM jaccard_edges
            )
            SELECT 
                COUNT(*) as degree,
                COUNT(DISTINCT book_id) as nb_books
            FROM degrees
            GROUP BY book_id
            ORDER BY degree;
        """)
        
        degree_dist = cur.fetchall()
        if degree_dist:
            print("\nDegré | Nombre de livres")
            print("------+-----------------")
            for degree, nb in degree_dist:
                bar = "█" * (nb // 1)
                print(f"{degree:5d} | {nb:3d} {bar}")


def main():
    with psycopg2.connect(PGURL) as conn:
        show_jaccard_stats(conn)


if __name__ == "__main__":
    main()
