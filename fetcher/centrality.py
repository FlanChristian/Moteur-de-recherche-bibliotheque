#!/usr/bin/env python3
"""
Calcul des métriques de centralité sur le graphe de Jaccard.

Implémente :
- PageRank : mesure l'importance d'un livre dans le réseau
- Closeness : mesure la proximité moyenne aux autres livres
- Betweenness : mesure le rôle de "pont" d'un livre
"""
import os
import psycopg2
from collections import defaultdict
import math

PGURL = os.environ.get("PGURL")
if not PGURL:
    raise SystemExit("Erreur: définis la variable d'environnement PGURL")


def load_graph(conn):
    """
    Charge le graphe de Jaccard depuis la base.
    Retourne : adjacency_list, book_ids
    """
    adjacency = defaultdict(dict)
    book_ids = set()
    
    with conn.cursor() as cur:
        # Charger toutes les arêtes
        cur.execute("""
            SELECT book_id1, book_id2, similarity
            FROM jaccard_edges
        """)
        
        for b1, b2, sim in cur.fetchall():
            # Graphe non-orienté
            adjacency[b1][b2] = sim
            adjacency[b2][b1] = sim
            book_ids.add(b1)
            book_ids.add(b2)
        
        # Ajouter les livres isolés (sans arêtes)
        cur.execute("SELECT id FROM books")
        all_books = {row[0] for row in cur.fetchall()}
        book_ids.update(all_books)
    
    return adjacency, sorted(book_ids)


def compute_pagerank(adjacency, book_ids, damping=0.85, max_iter=100, tolerance=1e-6):
    """
    Calcule le PageRank pour chaque livre.
    
    Args:
        adjacency: dict[book_id] -> dict[neighbor_id] -> weight
        book_ids: liste des IDs de livres
        damping: facteur d'amortissement (0.85 par défaut)
        max_iter: nombre maximum d'itérations
        tolerance: seuil de convergence
    
    Returns:
        dict[book_id] -> pagerank_score
    """
    n = len(book_ids)
    if n == 0:
        return {}
    
    # Initialisation : tous les livres ont le même score
    pagerank = {book_id: 1.0 / n for book_id in book_ids}
    
    # Normaliser les poids des arêtes sortantes
    out_weights = {}
    for book_id in book_ids:
        neighbors = adjacency.get(book_id, {})
        total_weight = sum(neighbors.values()) if neighbors else 0
        out_weights[book_id] = total_weight
    
    print(f"🔄 Calcul de PageRank...")
    print(f"   Livres: {n}")
    print(f"   Damping: {damping}")
    print(f"   Max itérations: {max_iter}")
    
    # Itérations PageRank
    for iteration in range(max_iter):
        new_pagerank = {}
        diff = 0.0
        
        for book_id in book_ids:
            # Contribution des voisins
            rank_sum = 0.0
            for neighbor_id in book_ids:
                if book_id in adjacency.get(neighbor_id, {}):
                    # Le voisin pointe vers ce livre
                    weight = adjacency[neighbor_id][book_id]
                    out_weight = out_weights[neighbor_id]
                    if out_weight > 0:
                        rank_sum += pagerank[neighbor_id] * (weight / out_weight)
            
            # Formule PageRank : (1-d)/N + d * sum(PR(neighbor)/out_degree(neighbor))
            new_rank = (1 - damping) / n + damping * rank_sum
            new_pagerank[book_id] = new_rank
            
            # Calculer la différence pour convergence
            diff += abs(new_rank - pagerank[book_id])
        
        pagerank = new_pagerank
        
        if (iteration + 1) % 10 == 0:
            print(f"   Itération {iteration + 1}: diff = {diff:.6f}")
        
        # Convergence
        if diff < tolerance:
            print(f"   ✅ Convergence atteinte à l'itération {iteration + 1}")
            break
    else:
        print(f"   ⚠️ Nombre maximum d'itérations atteint")
    
    # Normaliser pour que la somme soit 1
    total = sum(pagerank.values())
    if total > 0:
        pagerank = {k: v / total for k, v in pagerank.items()}
    
    return pagerank


def compute_closeness(adjacency, book_ids):
    """
    Calcule la closeness centrality pour chaque livre.
    
    Closeness = 1 / (moyenne des distances aux autres noeuds)
    
    Utilise l'algorithme de Dijkstra pour calculer les plus courts chemins.
    """
    print(f"\n🔄 Calcul de Closeness Centrality...")
    
    closeness = {}
    n = len(book_ids)
    
    for i, book_id in enumerate(book_ids):
        if (i + 1) % 10 == 0:
            print(f"   Progression: {i+1}/{n} livres...")
        
        # BFS pour calculer les distances
        distances = {book_id: 0}
        queue = [book_id]
        visited = {book_id}
        
        while queue:
            current = queue.pop(0)
            current_dist = distances[current]
            
            for neighbor in adjacency.get(current, {}):
                if neighbor not in visited:
                    visited.add(neighbor)
                    distances[neighbor] = current_dist + 1
                    queue.append(neighbor)
        
        # Calculer la closeness
        if len(distances) > 1:
            avg_distance = sum(distances.values()) / (len(distances) - 1)
            closeness[book_id] = 1.0 / avg_distance if avg_distance > 0 else 0
        else:
            closeness[book_id] = 0
    
    print(f"   ✅ Closeness calculée pour {n} livres")
    
    return closeness


def compute_betweenness(adjacency, book_ids):
    """
    Calcule la betweenness centrality pour chaque livre.
    
    Betweenness = nombre de plus courts chemins passant par ce noeud
    
    Utilise l'algorithme de Brandes.
    """
    print(f"\n🔄 Calcul de Betweenness Centrality...")
    
    betweenness = {book_id: 0.0 for book_id in book_ids}
    n = len(book_ids)
    
    for i, source in enumerate(book_ids):
        if (i + 1) % 10 == 0:
            print(f"   Progression: {i+1}/{n} livres...")
        
        # BFS depuis source
        stack = []
        pred = {book_id: [] for book_id in book_ids}
        sigma = {book_id: 0 for book_id in book_ids}
        sigma[source] = 1
        dist = {book_id: -1 for book_id in book_ids}
        dist[source] = 0
        
        queue = [source]
        
        while queue:
            v = queue.pop(0)
            stack.append(v)
            
            for w in adjacency.get(v, {}):
                # Découverte
                if dist[w] < 0:
                    queue.append(w)
                    dist[w] = dist[v] + 1
                
                # Plus court chemin via v
                if dist[w] == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)
        
        # Accumulation
        delta = {book_id: 0.0 for book_id in book_ids}
        
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += (sigma[v] / sigma[w]) * (1 + delta[w])
            
            if w != source:
                betweenness[w] += delta[w]
    
    # Normalisation (pour graphe non-orienté)
    if n > 2:
        norm = 2.0 / ((n - 1) * (n - 2))
        betweenness = {k: v * norm for k, v in betweenness.items()}
    
    print(f"   ✅ Betweenness calculée pour {n} livres")
    
    return betweenness


def save_centrality_to_db(conn, pagerank, closeness, betweenness):
    """
    Sauvegarde les métriques de centralité dans la base de données.
    """
    print(f"\n💾 Sauvegarde dans la base de données...")
    
    with conn.cursor() as cur:
        # Créer la table si elle n'existe pas
        cur.execute("""
            CREATE TABLE IF NOT EXISTS book_centrality (
                book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,
                pagerank REAL NOT NULL,
                closeness REAL NOT NULL,
                betweenness REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            );
        """)
        
        # Nettoyer les anciennes données
        cur.execute("TRUNCATE book_centrality;")
        
        # Insérer les nouvelles valeurs
        count = 0
        for book_id in pagerank.keys():
            cur.execute("""
                INSERT INTO book_centrality (book_id, pagerank, closeness, betweenness)
                VALUES (%s, %s, %s, %s)
            """, (
                book_id,
                pagerank.get(book_id, 0),
                closeness.get(book_id, 0),
                betweenness.get(book_id, 0)
            ))
            count += 1
        
        conn.commit()
        print(f"   ✅ {count} entrées sauvegardées")


def show_top_books(conn, metric='pagerank', limit=10):
    """
    Affiche les livres les mieux classés selon une métrique.
    """
    print(f"\n🏆 TOP {limit} LIVRES PAR {metric.upper()}")
    print("=" * 70)
    
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT 
                b.id,
                b.title,
                b.author,
                bc.{metric}
            FROM book_centrality bc
            JOIN books b ON b.id = bc.book_id
            ORDER BY bc.{metric} DESC
            LIMIT %s
        """, (limit,))
        
        for i, (book_id, title, author, score) in enumerate(cur.fetchall(), 1):
            print(f"{i:2d}. {title[:50]:<50} - {author[:20]:<20}")
            print(f"    Score: {score:.6f}")


def main():
    with psycopg2.connect(PGURL) as conn:
        print("\n" + "="*70)
        print("📊 CALCUL DES MÉTRIQUES DE CENTRALITÉ")
        print("="*70)
        
        # 1. Charger le graphe
        print("\n📥 Chargement du graphe de Jaccard...")
        adjacency, book_ids = load_graph(conn)
        print(f"   ✅ {len(book_ids)} livres chargés")
        print(f"   ✅ {sum(len(neighbors) for neighbors in adjacency.values()) // 2} arêtes")
        
        # 2. Calculer PageRank
        pagerank = compute_pagerank(adjacency, book_ids)
        
        # 3. Calculer Closeness
        closeness = compute_closeness(adjacency, book_ids)
        
        # 4. Calculer Betweenness
        betweenness = compute_betweenness(adjacency, book_ids)
        
        # 5. Sauvegarder
        save_centrality_to_db(conn, pagerank, closeness, betweenness)
        
        # 6. Afficher les tops
        show_top_books(conn, 'pagerank', 10)
        show_top_books(conn, 'closeness', 10)
        show_top_books(conn, 'betweenness', 10)
        
        print("\n" + "="*70)
        print("✅ MÉTRIQUES DE CENTRALITÉ CALCULÉES AVEC SUCCÈS")
        print("="*70)
        print("\n💡 Vous pouvez maintenant utiliser ces métriques pour :")
        print("   - Classer les résultats de recherche")
        print("   - Identifier les livres influents")
        print("   - Détecter les clusters thématiques\n")


if __name__ == "__main__":
    main()
