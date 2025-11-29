#!/usr/bin/env python3
"""
Supprime et recrée la table jaccard_edges avec le bon schéma.
"""
import os
import psycopg2

PGURL = os.environ.get("PGURL")
if not PGURL:
    raise SystemExit("Erreur: définis la variable d'environnement PGURL")


def recreate_jaccard_table(conn):
    """Supprime et recrée la table jaccard_edges."""
    with conn.cursor() as cur:
        # Suppression de la table
        cur.execute("DROP TABLE IF EXISTS jaccard_edges CASCADE;")
        print("🗑️ Ancienne table supprimée.")
        
        # Création de la table
        cur.execute("""
            CREATE TABLE jaccard_edges (
                id SERIAL PRIMARY KEY,
                book_id1 INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                book_id2 INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                dist REAL NOT NULL,
                similarity REAL NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(book_id1, book_id2),
                CHECK (book_id1 < book_id2),
                CHECK (dist >= 0.0 AND dist <= 1.0),
                CHECK (similarity >= 0.0 AND similarity <= 1.0)
            );
        """)
        
        # Index pour accélérer les requêtes
        cur.execute("""
            CREATE INDEX idx_jaccard_book1 ON jaccard_edges(book_id1);
        """)
        
        cur.execute("""
            CREATE INDEX idx_jaccard_book2 ON jaccard_edges(book_id2);
        """)
        
        cur.execute("""
            CREATE INDEX idx_jaccard_dist ON jaccard_edges(dist ASC);
        """)
        
        cur.execute("""
            CREATE INDEX idx_jaccard_similarity ON jaccard_edges(similarity DESC);
        """)
        
        conn.commit()
        print("✅ Table jaccard_edges recréée avec succès!")


def main():
    with psycopg2.connect(PGURL) as conn:
        recreate_jaccard_table(conn)


if __name__ == "__main__":
    main()
