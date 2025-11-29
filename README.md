# 📚 BiblioSearch - Moteur de Recherche pour Bibliothèque

**Projet DAAR - M2 STL - Sorbonne Université - 2025**

Moteur de recherche intelligent pour explorer la bibliothèque du Projet Gutenberg avec indexation inversée, graphe de similarité de Jaccard et métriques de centralité.

---

## 🎯 Fonctionnalités

### ✅ Recherche Avancée
- **Mot-clé** : recherche simple avec 3 niveaux de priorité (titre → top-50 → index complet)
- **RegEx** : patterns complexes pour recherches avancées (`^love`, `[a-z]{4}$`, etc.)
- **Filtres** : par langue (English, French, Italian)
- **Tri dynamique** : 6 options (pertinence, PageRank, occurrences, closeness, betweenness, titre)

### ✅ Graphe de Jaccard (OBLIGATOIRE)
- **Similarité textuelle** : `J(A,B) = |A ∩ B| / |A ∪ B|` sur les top-50 mots
- **Seuil 0.5** : minimum 50% de mots communs
- **82 arêtes** reliant 35 livres (similarité moyenne : 0.5509)
- **Visualisation interactive** : graphe Vis.js avec slider de seuil ajustable
- **Recommandations** : livres similaires dans chaque page de détail

### ✅ Centralité de Graphe (OBLIGATOIRE)
Trois métriques calculées sur le graphe de Jaccard :

- **PageRank** : importance dans le réseau (convergence en 45 itérations, damping 0.85)
- **Closeness** : proximité moyenne aux autres livres (algorithme BFS)
- **Betweenness** : rôle de "pont" entre clusters (algorithme de Brandes)

### ✅ Interface Moderne
- Design responsive avec sidebar navigation
- Cartes de livres avec couvertures
- Graphe interactif (zoom, drag, filtrage)
- Autocomplétion de recherche
- Statistiques temps réel

---

## 🏗️ Architecture

### Stack Technique
- **Backend** : Django 5.2.8 (Python 3.13)
- **Base de données** : PostgreSQL 16
- **Frontend** : Templates Django + Vanilla JS
- **Visualisation** : Vis.js 9.1.2 (graphe), Chart.js 4.4.0 (stats)

### Structure PostgreSQL
```sql
books          -- Métadonnées des livres
words          -- Vocabulaire global (15K mots uniques)
postings       -- Index inversé (290K entrées)
top_terms      -- Top-50 mots par livre (1750 entrées)
jaccard_edges  -- Graphe de similarité (82 arêtes)
book_centrality -- PageRank, Closeness, Betweenness (35 entrées)
```

---

## 🚀 Installation et Démarrage

### 1. Prérequis
- Python 3.13+
- PostgreSQL 16+
- Git

### 2. Cloner et installer
```powershell
git clone <repository_url>
cd Moteur-de-recherche-bibliotheque
pip install -r requirements.txt
```

### 3. Configurer PostgreSQL
```powershell
# Créer la base de données
psql -U postgres
CREATE DATABASE daar;
\q

# Définir la variable d'environnement
$env:PGURL="postgresql://postgres:postgres@localhost:5432/daar"
```

### 4. Indexer les données
```powershell
# Indexer les livres dans PostgreSQL
python fetcher/ingest.py

# Construire le graphe de Jaccard
python fetcher/build_jaccard.py

# Calculer les métriques de centralité
python fetcher/centrality.py
```

### 5. Lancer l'application
```powershell
cd bibliosearch
python manage.py migrate
python manage.py runserver
```

### 6. Accéder
Ouvrir : **http://127.0.0.1:8000/**

---

## 📊 Algorithmes Implémentés

### 1. Construction du Graphe de Jaccard
```python
# Pour chaque paire de livres (i, j)
words_i = set(top_50_mots[livre_i])
words_j = set(top_50_mots[livre_j])

similarity = len(words_i & words_j) / len(words_i | words_j)

if similarity >= 0.5:
    create_edge(i, j, similarity)
```

**Résultats** :
- 595 paires comparées
- 82 arêtes créées (13.78% de densité)
- Range de similarité : [0.5013, 0.7701]

### 2. PageRank
```python
# Initialisation
PR[i] = 1/N pour tous les livres

# Itération jusqu'à convergence
for iteration in range(max_iter):
    for livre_i:
        PR_new[i] = (1-d)/N + d * Σ(PR[voisin] × poids / total_poids_sortant)
    
    if |PR_new - PR| < tolerance:
        break  # Convergence atteinte
```

**Paramètres** : damping=0.85, max_iter=100, tolerance=1e-6  
**Résultat** : Top livre = "This Side of Paradise" (0.050525)

### 3. Closeness Centrality
```python
# Pour chaque livre source
distances = BFS(source)  # Plus courts chemins
avg_distance = mean(distances)
closeness = 1 / avg_distance
```

**Résultat** : Top livre = "Nicholas Nickleby" (1.0)

### 4. Betweenness Centrality (Brandes)
```python
betweenness = {livre: 0 for livre in livres}

for source in livres:
    # Phase 1: BFS pour compter les chemins
    sigma = count_shortest_paths(source)
    
    # Phase 2: Accumulation en remontant
    for livre in reversed(BFS_order):
        betweenness[livre] += contribution(livre, sigma)

# Normalisation pour graphe non-orienté
betweenness = {k: v × 2/((N-1)(N-2)) for k, v in betweenness.items()}
```

**Résultat** : Top livre = "The Adventures of Pinocchio" (0.552585)

---

## 📁 Structure du Projet

```
Moteur-de-recherche-bibliotheque/
├── README.md                    # Ce fichier
├── requirements.txt             # Dépendances Python
├── daar_projet3.pdf             # Énoncé du projet
│
├── fetcher/                     # Scripts d'indexation
│   ├── ingest.py               # Indexe les livres dans PostgreSQL
│   ├── build_jaccard.py        # Construit le graphe de similarité
│   ├── centrality.py           # Calcule PageRank, Closeness, Betweenness
│   ├── utils_text.py           # Tokenization et stopwords (179 mots)
│   └── data/raw/               # Livres téléchargés (.txt + .json)
│
└── bibliosearch/               # Application Django
    ├── manage.py               # CLI Django
    ├── bibliosearch/
    │   ├── settings.py         # Configuration
    │   └── urls.py             # Routes principales
    └── search/
        ├── models.py           # Modèles ORM (Book, Word, Posting)
        ├── views.py            # Logique métier (recherche, tri, graphe)
        ├── urls.py             # Routes de l'app
        └── templates/search/
            ├── home.html           # Page d'accueil + recherche
            ├── book_detail.html    # Détail + recommandations Jaccard
            └── jaccard_graph.html  # Visualisation interactive
```

---

## 🎨 Captures d'écran et Démonstration

### Page d'accueil
- Barre de recherche avec autocomplétion
- Filtres par langue et tri
- Livres populaires (par PageRank)
- Statistiques globales (35 livres, 3 langues, ~290K postings)

### Résultats de recherche
- Badges de source : 📖 Titre / ⭐ Top-50 / 🔍 Index
- 6 options de tri : Pertinence, PageRank, Occurrences, Closeness, Betweenness, Titre
- Statistiques : nombre de résultats par source

### Page de détail
- Informations complètes (titre, auteur, langue, nombre de mots)
- Top-10 mots les plus fréquents avec compteurs
- **Livres similaires via Jaccard** (avec scores de similarité)
- Livres du même auteur
- Navigation précédent/suivant

### Graphe de Jaccard (/jaccard/)
- Visualisation interactive Vis.js (zoom, drag, sélection)
- Slider de seuil dynamique (0.5 → 1.0)
- Statistiques : nœuds, arêtes, similarité moyenne
- Top 20 paires les plus similaires
- Top 15 livres les plus connectés

---

## 📈 Statistiques Actuelles

**Données indexées (35 livres)** :
- Livres : 35
- Langues : 3 (English, French, Italian)
- Mots uniques : ~15,000
- Postings : ~290,000
- Top terms : 1,750 (50 par livre)
- Arêtes Jaccard : 82 (seuil 0.5)
- Centralité : 35 entrées calculées

**Performance** :
- Recherche par mot : < 50ms
- Recherche RegEx : < 200ms
- Construction Jaccard : ~5s (35 livres)
- Calcul centralité : ~10s (35 livres)
- **Scalabilité** : prêt pour 1664+ livres (~190K arêtes Jaccard estimées)

---

## 🔧 Commandes Utiles

### Réindexation complète
```powershell
$env:PGURL="postgresql://postgres:postgres@localhost:5432/daar"
$env:INIT_SCHEMA="1"  # Force la recréation des tables
python fetcher/ingest.py
python fetcher/build_jaccard.py
python fetcher/centrality.py
```

### Vérification rapide
```powershell
# Nombre de livres
python -c "import psycopg2; conn = psycopg2.connect('postgresql://postgres:postgres@localhost:5432/daar'); cur = conn.cursor(); cur.execute('SELECT COUNT(*) FROM books'); print(f'Livres: {cur.fetchone()[0]}')"

# Arêtes Jaccard
python -c "import psycopg2; conn = psycopg2.connect('postgresql://postgres:postgres@localhost:5432/daar'); cur = conn.cursor(); cur.execute('SELECT COUNT(*) FROM jaccard_edges'); print(f'Arêtes: {cur.fetchone()[0]}')"
```

### Requêtes SQL utiles
```sql
-- Top 10 PageRank
SELECT b.title, bc.pagerank
FROM book_centrality bc
JOIN books b ON b.id = bc.book_id
ORDER BY bc.pagerank DESC
LIMIT 10;

-- Top 10 paires Jaccard
SELECT b1.title, b2.title, je.similarity
FROM jaccard_edges je
JOIN books b1 ON b1.id = je.book_id1
JOIN books b2 ON b2.id = je.book_id2
ORDER BY je.similarity DESC
LIMIT 10;

-- Rechercher un mot
SELECT b.title, p.cnt
FROM words w
JOIN postings p ON p.word_id = w.id
JOIN books b ON b.id = p.book_id
WHERE w.w = 'love'
ORDER BY p.cnt DESC
LIMIT 10;
```

---

## 🎯 Choix Techniques Clés

### Indexation
- **Top-50 seulement** pour Jaccard : performance 100x + capture l'essence thématique
- **Stopwords filtrés** (179 mots) : améliore la qualité des résultats
- **Index B-tree** sur `words.w` : recherche rapide

### Graphe de Jaccard
- **Seuil 0.5** : équilibre entre bruit et couverture
- **Graphe non-orienté** : similarité symétrique
- **Poids stockés** : permet ajustement dynamique du seuil

### Centralité
- **3 métriques complémentaires** : vues différentes de l'importance
- **PageRank standard** : damping 0.85 (Google)
- **Algorithmes optimaux** : BFS pour closeness, Brandes pour betweenness

### Interface
- **Sans framework CSS** : contrôle total, performance
- **Vanilla JS** : simplicité, pas de build step
- **Vis.js** : graphe professionnel clé en main

---

## 📚 Références

### Algorithmes
- **PageRank** : Page, L., Brin, S. (1998). "The PageRank Citation Ranking"
- **Betweenness** : Brandes, U. (2001). "A faster algorithm for betweenness centrality"
- **Jaccard** : Jaccard, P. (1912). "The distribution of the flora in the alpine zone"

### Technologies
- Django : https://docs.djangoproject.com/
- PostgreSQL : https://www.postgresql.org/docs/
- Vis.js : https://visjs.github.io/vis-network/

---

## 🚨 Dépannage

### Erreur : "relation does not exist"
```powershell
# Recréer les tables
$env:INIT_SCHEMA="1"
python fetcher/ingest.py
```

### Erreur : "could not connect to server"
```powershell
# Démarrer PostgreSQL
pg_ctl start
```

### Cache navigateur
```
Forcer le rechargement : Ctrl + Shift + R (ou Ctrl + F5)
Ou navigation privée : Ctrl + Shift + N
```

### Graphe Jaccard vide
```powershell
# Reconstruire
python fetcher/build_jaccard.py
python fetcher/centrality.py
```

---

## ✅ Conformité Projet DAAR

### Fonctionnalités OBLIGATOIRES Implémentées

✅ **Graphe de Jaccard**
- Construction complète avec seuil 0.5
- 82 arêtes sur 35 livres
- Visualisation interactive avec Vis.js
- Recommandations dans les pages de détail

✅ **Centralité de Graphe**
- PageRank (convergence 45 itérations)
- Closeness (BFS)
- Betweenness (Brandes)
- Intégration dans le tri des résultats

✅ **Système de Recherche**
- Mot-clé avec 3 niveaux de priorité
- RegEx pour patterns complexes
- Filtrage par langue
- Tri multi-critères (6 options)

### Points Forts du Projet

🎨 **Interface moderne** : design professionnel, responsive  
⚡ **Performance** : recherche < 50ms, SQL optimisé  
📈 **Scalabilité** : prêt pour 1664+ livres  
📖 **Documentation** : code commenté, README complet  
🔬 **Algorithmes standards** : PageRank, Brandes reconnus

---

## 👥 Auteurs

**Projet DAAR - M2 STL**  
Sorbonne Université - 2024-2025

---

## 📝 Licence

Projet académique - M2 STL DAAR

