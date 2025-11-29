#!/usr/bin/env python3
"""
Crée la table jaccard_edges pour stocker les similarités entre livres.
"""
import os
import psycopg2

PGURL = os.environ.get("PGURL")
if not PGURL:
    raise SystemExit("Erreur: définis la variable d'environnement PGURL")


def create_jaccard_table(conn):
    """Crée la table jaccard_edges si elle n'existe pas."""
    with conn.cursor() as cur:
        # Création de la table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jaccard_edges (
                id SERIAL PRIMARY KEY,
                book_id1 INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                book_id2 INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                dist REAL NOT NULL,
                similarity REAL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(book_id1, book_id2),
                CHECK (book_id1 < book_id2),
                CHECK (dist >= 0.0 AND dist <= 1.0)
            );
        """)
        
        # Index pour accélérer les requêtes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_jaccard_book1 
            ON jaccard_edges(book_id1);
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_jaccard_book2 
            ON jaccard_edges(book_id2);
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_jaccard_dist 
            ON jaccard_edges(dist ASC);
        """)
        
        conn.commit()
        print("✅ Table jaccard_edges créée avec succès!")
        
        # Afficher les statistiques
        cur.execute("SELECT COUNT(*) FROM jaccard_edges;")
        count = cur.fetchone()[0]
        print(f"📊 Nombre d'arêtes actuelles: {count}")


def main():
    with psycopg2.connect(PGURL) as conn:
        create_jaccard_table(conn)


if __name__ == "__main__":
    main()
