"""
Benchmark visuel avec génération de graphiques pour le rapport
Basé sur les tests demandés dans daar_projet3.pdf
"""

import time
import psycopg2
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
import os

# Configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'daar',
    'user': 'postgres',
    'password': 'postgres'
}

# Créer le dossier pour les graphiques
os.makedirs('benchmark_graphs', exist_ok=True)

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def benchmark_query(cursor, query, params=None, iterations=10):
    """Exécute une requête plusieurs fois et retourne les temps"""
    times = []
    for _ in range(iterations):
        start = time.time()
        cursor.execute(query, params or ())
        cursor.fetchall()
        elapsed = time.time() - start
        times.append(elapsed * 1000)  # Convertir en ms
    return times

print("\n" + "="*80)
print("BENCHMARK VISUEL - MOTEUR DE RECHERCHE BIBLIOSEARCH")
print("="*80)

# ============================================================================
# 1. COMPARAISON DES TEMPS DE RECHERCHE
# ============================================================================
print("\n1. Comparaison des temps de recherche par type...")

conn = get_connection()
cursor = conn.cursor()

search_types = {
    'Titre (LIKE)': ("SELECT id, title FROM books WHERE LOWER(title) LIKE '%%love%%'", None),
    'Top Terms': ("SELECT b.id, b.title FROM top_terms tt JOIN books b ON b.id = tt.book_id WHERE LOWER(tt.w) = 'love'", None),
    'Postings': ("SELECT b.id, b.title FROM words w JOIN postings p ON p.word_id = w.id JOIN books b ON b.id = p.book_id WHERE LOWER(w.w) = 'love'", None),
    'RegEx': ("SELECT b.id, b.title FROM words w JOIN postings p ON p.word_id = w.id JOIN books b ON b.id = p.book_id WHERE w.w ~ '^love' GROUP BY b.id, b.title", None)
}

search_results = {}
for name, (query, params) in search_types.items():
    print(f"   Testing {name}...")
    times = benchmark_query(cursor, query, params, iterations=10)
    search_results[name] = np.mean(times)

# Graphique 1: Comparaison des temps de recherche
plt.figure(figsize=(10, 6))
names = list(search_results.keys())
values = list(search_results.values())
colors = ['#667eea', '#764ba2', '#f093fb', '#4facfe']
bars = plt.bar(names, values, color=colors, edgecolor='black', linewidth=1.5)
plt.ylabel('Temps moyen (ms)', fontsize=12, fontweight='bold')
plt.title('Comparaison des temps de recherche par méthode', fontsize=14, fontweight='bold')
plt.xticks(rotation=15, ha='right')
plt.grid(axis='y', alpha=0.3, linestyle='--')
for i, (bar, val) in enumerate(zip(bars, values)):
    plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(values)*0.02,
             f'{val:.1f}ms', ha='center', va='bottom', fontweight='bold')
plt.tight_layout()
plt.savefig('benchmark_graphs/1_comparaison_recherche.png', dpi=300, bbox_inches='tight')
print("   ✓ Graphique sauvegardé: 1_comparaison_recherche.png")

# ============================================================================
# 2. SCALABILITÉ: TEMPS DE RECHERCHE SELON LA TAILLE DU CORPUS
# ============================================================================
print("\n2. Scalabilité selon le nombre de livres...")

book_limits = [100, 250, 500, 750, 1000, 1250, 1500, 1726]
scalability_results = {}

for method_name in ['Top Terms', 'Postings']:
    scalability_results[method_name] = []
    
for limit in book_limits:
    print(f"   Testing avec {limit} livres...")
    
    # Test Top Terms
    query = f"""
        SELECT b.id, b.title 
        FROM top_terms tt 
        JOIN books b ON b.id = tt.book_id 
        WHERE LOWER(tt.w) = 'time' AND b.id <= (SELECT id FROM books ORDER BY id LIMIT 1 OFFSET {limit-1})
    """
    times = benchmark_query(cursor, query, iterations=5)
    scalability_results['Top Terms'].append(np.mean(times))
    
    # Test Postings
    query = f"""
        SELECT b.id, b.title 
        FROM words w 
        JOIN postings p ON p.word_id = w.id 
        JOIN books b ON b.id = p.book_id 
        WHERE LOWER(w.w) = 'time' AND b.id <= (SELECT id FROM books ORDER BY id LIMIT 1 OFFSET {limit-1})
    """
    times = benchmark_query(cursor, query, iterations=5)
    scalability_results['Postings'].append(np.mean(times))

# Graphique 2: Scalabilité
plt.figure(figsize=(12, 6))
for method, times in scalability_results.items():
    plt.plot(book_limits, times, marker='o', linewidth=2.5, markersize=8, label=method)
plt.xlabel('Nombre de livres dans le corpus', fontsize=12, fontweight='bold')
plt.ylabel('Temps de recherche (ms)', fontsize=12, fontweight='bold')
plt.title('Scalabilité: Temps de recherche vs Taille du corpus', fontsize=14, fontweight='bold')
plt.legend(fontsize=11)
plt.grid(True, alpha=0.3, linestyle='--')
plt.tight_layout()
plt.savefig('benchmark_graphs/2_scalabilite.png', dpi=300, bbox_inches='tight')
print("   ✓ Graphique sauvegardé: 2_scalabilite.png")

# ============================================================================
# 3. DISTRIBUTION DES TEMPS DE RÉPONSE
# ============================================================================
print("\n3. Distribution des temps de réponse...")

query = "SELECT b.id, b.title FROM top_terms tt JOIN books b ON b.id = tt.book_id WHERE LOWER(tt.w) = 'love'"
times_distribution = benchmark_query(cursor, query, iterations=100)

# Graphique 3: Distribution
plt.figure(figsize=(10, 6))
plt.hist(times_distribution, bins=30, color='#667eea', edgecolor='black', alpha=0.7)
plt.axvline(np.mean(times_distribution), color='red', linestyle='--', linewidth=2, label=f'Moyenne: {np.mean(times_distribution):.1f}ms')
plt.axvline(np.median(times_distribution), color='green', linestyle='--', linewidth=2, label=f'Médiane: {np.median(times_distribution):.1f}ms')
plt.xlabel('Temps de réponse (ms)', fontsize=12, fontweight='bold')
plt.ylabel('Fréquence', fontsize=12, fontweight='bold')
plt.title('Distribution des temps de réponse (recherche top_terms, 100 itérations)', fontsize=14, fontweight='bold')
plt.legend(fontsize=11)
plt.grid(axis='y', alpha=0.3, linestyle='--')
plt.tight_layout()
plt.savefig('benchmark_graphs/3_distribution_temps.png', dpi=300, bbox_inches='tight')
print("   ✓ Graphique sauvegardé: 3_distribution_temps.png")

# ============================================================================
# 4. PERFORMANCE DES MÉTRIQUES DE CENTRALITÉ
# ============================================================================
print("\n4. Performance des métriques de centralité...")

centrality_metrics = {
    'PageRank': "SELECT b.id, b.title, bc.pagerank FROM books b JOIN book_centrality bc ON bc.book_id = b.id ORDER BY bc.pagerank DESC LIMIT 100",
    'Closeness': "SELECT b.id, b.title, bc.closeness FROM books b JOIN book_centrality bc ON bc.book_id = b.id ORDER BY bc.closeness DESC LIMIT 100",
    'Betweenness': "SELECT b.id, b.title, bc.betweenness FROM books b JOIN book_centrality bc ON bc.book_id = b.id ORDER BY bc.betweenness DESC LIMIT 100"
}

centrality_results = {}
for metric, query in centrality_metrics.items():
    print(f"   Testing {metric}...")
    times = benchmark_query(cursor, query, iterations=10)
    centrality_results[metric] = np.mean(times)

# Graphique 4: Centralité
plt.figure(figsize=(10, 6))
names = list(centrality_results.keys())
values = list(centrality_results.values())
colors = ['#f093fb', '#667eea', '#4facfe']
bars = plt.bar(names, values, color=colors, edgecolor='black', linewidth=1.5)
plt.ylabel('Temps moyen (ms)', fontsize=12, fontweight='bold')
plt.title('Performance des métriques de centralité (Top 100)', fontsize=14, fontweight='bold')
plt.grid(axis='y', alpha=0.3, linestyle='--')
for bar, val in zip(bars, values):
    plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(values)*0.02,
             f'{val:.2f}ms', ha='center', va='bottom', fontweight='bold')
plt.tight_layout()
plt.savefig('benchmark_graphs/4_centralite.png', dpi=300, bbox_inches='tight')
print("   ✓ Graphique sauvegardé: 4_centralite.png")

# ============================================================================
# 5. PERFORMANCE DU GRAPHE JACCARD
# ============================================================================
print("\n5. Performance des requêtes Jaccard...")

jaccard_queries = {
    'Top 20 paires': ("SELECT b1.title, b2.title, je.similarity FROM jaccard_edges je JOIN books b1 ON b1.id = je.book_id1 JOIN books b2 ON b2.id = je.book_id2 ORDER BY je.similarity DESC LIMIT 20", None),
    'Stats similarité': ("SELECT MIN(similarity), AVG(similarity), MAX(similarity) FROM jaccard_edges", None),
    'Arêtes d\'un livre': ("SELECT book_id2, similarity FROM jaccard_edges WHERE book_id1 = 1 UNION ALL SELECT book_id1, similarity FROM jaccard_edges WHERE book_id2 = 1 ORDER BY similarity DESC LIMIT 50", None),
    'Livres connectés': ("WITH degrees AS (SELECT book_id1 as book_id, COUNT(*) as degree FROM jaccard_edges GROUP BY book_id1 UNION ALL SELECT book_id2, COUNT(*) FROM jaccard_edges GROUP BY book_id2) SELECT book_id, SUM(degree) FROM degrees GROUP BY book_id ORDER BY 2 DESC LIMIT 20", None)
}

jaccard_results = {}
for name, (query, params) in jaccard_queries.items():
    print(f"   Testing {name}...")
    times = benchmark_query(cursor, query, params, iterations=10)
    jaccard_results[name] = np.mean(times)

# Graphique 5: Jaccard
plt.figure(figsize=(10, 6))
names = list(jaccard_results.keys())
values = list(jaccard_results.values())
colors = ['#667eea', '#764ba2', '#f093fb', '#4facfe']
bars = plt.barh(names, values, color=colors, edgecolor='black', linewidth=1.5)
plt.xlabel('Temps moyen (ms)', fontsize=12, fontweight='bold')
plt.title('Performance des requêtes du graphe Jaccard', fontsize=14, fontweight='bold')
plt.grid(axis='x', alpha=0.3, linestyle='--')
for bar, val in zip(bars, values):
    plt.text(val + max(values)*0.02, bar.get_y() + bar.get_height()/2,
             f'{val:.1f}ms', va='center', fontweight='bold')
plt.tight_layout()
plt.savefig('benchmark_graphs/5_jaccard.png', dpi=300, bbox_inches='tight')
print("   ✓ Graphique sauvegardé: 5_jaccard.png")

# ============================================================================
# 6. COMPARAISON REGEX vs RECHERCHE SIMPLE
# ============================================================================
print("\n6. Comparaison RegEx complexité...")

regex_patterns = {
    'Simple (^love)': "^love",
    'Moyen (love.*)': "love.*",
    'Complexe ([a-z]*love[a-z]*)': "[a-z]*love[a-z]*"
}

regex_results = {}
for name, pattern in regex_patterns.items():
    print(f"   Testing {name}...")
    query = f"""
        SELECT b.id, b.title 
        FROM words w 
        JOIN postings p ON p.word_id = w.id 
        JOIN books b ON b.id = p.book_id 
        WHERE w.w ~ %s 
        GROUP BY b.id, b.title 
        LIMIT 100
    """
    times = benchmark_query(cursor, query, (pattern,), iterations=5)
    regex_results[name] = np.mean(times)

# Graphique 6: RegEx
plt.figure(figsize=(10, 6))
names = list(regex_results.keys())
values = list(regex_results.values())
colors = ['#4facfe', '#667eea', '#764ba2']
bars = plt.bar(names, values, color=colors, edgecolor='black', linewidth=1.5)
plt.ylabel('Temps moyen (ms)', fontsize=12, fontweight='bold')
plt.title('Impact de la complexité des expressions régulières', fontsize=14, fontweight='bold')
plt.xticks(rotation=15, ha='right')
plt.grid(axis='y', alpha=0.3, linestyle='--')
for bar, val in zip(bars, values):
    plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(values)*0.02,
             f'{val:.1f}ms', ha='center', va='bottom', fontweight='bold')
plt.tight_layout()
plt.savefig('benchmark_graphs/6_regex_complexity.png', dpi=300, bbox_inches='tight')
print("   ✓ Graphique sauvegardé: 6_regex_complexity.png")

# ============================================================================
# 7. RÉCAPITULATIF DES PERFORMANCES
# ============================================================================
print("\n7. Génération du tableau récapitulatif...")

cursor.execute("SELECT COUNT(*) FROM books")
nb_books = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM words")
nb_words = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(DISTINCT w) FROM top_terms")
nb_top_terms = cursor.fetchone()[0]
cursor.execute("SELECT reltuples::bigint FROM pg_class WHERE relname = 'jaccard_edges'")
nb_edges = cursor.fetchone()[0]

# Créer un tableau récapitulatif
fig, ax = plt.subplots(figsize=(12, 8))
ax.axis('tight')
ax.axis('off')

summary_data = [
    ['MÉTRIQUE', 'VALEUR', 'PERFORMANCE'],
    ['', '', ''],
    ['Base de données', '', ''],
    ['  Livres indexés', f'{nb_books:,}', ''],
    ['  Mots uniques', f'{nb_words:,}', ''],
    ['  Top terms', f'{nb_top_terms:,}', ''],
    ['  Arêtes Jaccard', f'{nb_edges:,}', ''],
    ['', '', ''],
    ['Recherche (temps moyen)', '', ''],
    ['  Titre (LIKE)', f'{search_results["Titre (LIKE)"]:.1f} ms', '⚡ Très rapide'],
    ['  Top Terms', f'{search_results["Top Terms"]:.1f} ms', '✓ Rapide'],
    ['  Postings', f'{search_results["Postings"]:.1f} ms', '⚠ Moyen'],
    ['  RegEx', f'{search_results["RegEx"]:.1f} ms', '⚠ Moyen'],
    ['', '', ''],
    ['Centralité (top 100)', '', ''],
    ['  PageRank', f'{centrality_results["PageRank"]:.2f} ms', '⚡ Très rapide'],
    ['  Closeness', f'{centrality_results["Closeness"]:.2f} ms', '⚡ Très rapide'],
    ['  Betweenness', f'{centrality_results["Betweenness"]:.2f} ms', '⚡ Très rapide'],
]

table = ax.table(cellText=summary_data, cellLoc='left', loc='center',
                colWidths=[0.4, 0.3, 0.3])
table.auto_set_font_size(False)
table.set_fontsize(10)
table.scale(1, 2)

# Style du tableau
for i in range(len(summary_data)):
    for j in range(3):
        cell = table[(i, j)]
        if i == 0:  # En-tête
            cell.set_facecolor('#667eea')
            cell.set_text_props(weight='bold', color='white')
        elif i in [1, 7, 13]:  # Lignes vides
            cell.set_facecolor('#f5f5f5')
        elif summary_data[i][0] and not summary_data[i][0].startswith('  '):  # Catégories
            cell.set_facecolor('#e0e7ff')
            cell.set_text_props(weight='bold')
        else:
            cell.set_facecolor('white' if i % 2 == 0 else '#f9fafb')

plt.title(f'Récapitulatif des performances - {datetime.now().strftime("%Y-%m-%d %H:%M")}',
          fontsize=14, fontweight='bold', pad=20)
plt.savefig('benchmark_graphs/7_recapitulatif.png', dpi=300, bbox_inches='tight')
print("   ✓ Graphique sauvegardé: 7_recapitulatif.png")

conn.close()

print("\n" + "="*80)
print("✓ BENCHMARK VISUEL TERMINÉ")
print("="*80)
print(f"\nTous les graphiques ont été sauvegardés dans: benchmark_graphs/")
print("\nFichiers générés:")
print("  1. 1_comparaison_recherche.png    - Comparaison des méthodes de recherche")
print("  2. 2_scalabilite.png              - Scalabilité selon la taille du corpus")
print("  3. 3_distribution_temps.png       - Distribution des temps de réponse")
print("  4. 4_centralite.png               - Performance des métriques de centralité")
print("  5. 5_jaccard.png                  - Performance des requêtes Jaccard")
print("  6. 6_regex_complexity.png         - Impact de la complexité RegEx")
print("  7. 7_recapitulatif.png            - Tableau récapitulatif complet")
print("\nUtilisez ces graphiques pour votre rapport!\n")
