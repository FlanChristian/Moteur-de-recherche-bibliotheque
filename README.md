# 📚 BiblioSearch - Moteur de Recherche Intelligent

**Projet DAAR - M2 STL - Sorbonne Université 2024-2025**

Moteur de recherche pour la bibliothèque du Projet Gutenberg avec graphe de similarité Jaccard et métriques de centralité.

---

## 🌐 Site en Ligne

# **[bibliosearch.hamid-zibouche.fr](https://bibliosearch.hamid-zibouche.fr)**

> [!IMPORTANT]  
> **⚠️ Instance AWS Gratuite** : Le site est hébergé sur une instance EC2 gratuite avec des ressources limitées. Les recherches coûteuses (RegEx complexes, tri par centralité) peuvent entraîner des ralentissements ou un crash temporaire du serveur. Pour une expérience optimale, privilégiez l'installation locale via Docker.

---

## 🎯 Fonctionnalités

- **Recherche avancée** : mot-clé ou RegEx avec filtres et tri multi-critères
- **Graphe de Jaccard** : 82 arêtes de similarité textuelle (seuil 0.5) entre 35 livres
- **Métriques de centralité** : PageRank, Closeness, Betweenness pour le tri des résultats
- **Interface responsive** : design moderne avec menu burger et graphe interactif

---

## 🏗️ Stack Technique

- **Backend** : Django 5.2.8 (Python 3.13)
- **Base de données** : PostgreSQL 16
- **Frontend** : Templates Django + Vanilla JS
- **Visualisation** : Vis.js (graphe), Chart.js (stats)
- **Déploiement** : Docker + AWS EC2 (instance gratuite)

---

## 🚀 Démarrage Local

### 1. Avec Docker (recommandé)
```bash
git clone https://github.com/FlanChristian/Moteur-de-recherche-bibliotheque.git
cd Moteur-de-recherche-bibliotheque
docker compose up
```
Accès : http://localhost:8000

### 2. Installation manuelle
```bash
# Installer les dépendances
pip install -r requirements.txt

# Configurer PostgreSQL
psql -U postgres -c "CREATE DATABASE daar;"
export PGURL="postgresql://postgres:postgres@localhost:5432/daar"

# Indexer les données
python fetcher/ingest.py
python fetcher/build_jaccard.py

# Lancer Django
cd bibliosearch
python manage.py migrate
python manage.py runserver
```

---

## 📊 Algorithmes Implémentés

### Graphe de Jaccard
```python
J(A,B) = |A ∩ B| / |A ∪ B|  # Sur les top-50 mots de chaque livre
```
**Résultat** : 82 arêtes (similarité 0.50-0.77)

### PageRank
```python
PR[i] = (1-d)/N + d × Σ(PR[voisin] × poids)
```
**Paramètres** : damping=0.85, convergence en 45 itérations

### Closeness & Betweenness
- **Closeness** : BFS pour calculer les distances moyennes
- **Betweenness** : Algorithme de Brandes pour identifier les "ponts"

---

## 📁 Structure du Projet

```
├── fetcher/              # Indexation et construction du graphe
│   ├── ingest.py         # Index inversé PostgreSQL
│   ├── build_jaccard.py  # Calcul similarités Jaccard
│   └── data/raw/         # 35 livres Gutenberg (.txt + .json)
│
├── bibliosearch/         # Application Django
│   └── search/
│       ├── views.py      # Logique recherche et tri
│       └── templates/    # UI responsive (5 pages)
│
├── docker-compose.yml    # PostgreSQL + Django (multi-plateforme)
└── Dockerfile            # Image hamidzch/bibliosearch:latest
```

---

## 🌐 Déploiement AWS

Le site est hébergé sur une instance EC2 gratuite AWS :
- **URL** : [bibliosearch.hamid-zibouche.fr](http://bibliosearch.hamid-zibouche.fr)
- **Config** : t2.micro + Docker Compose
- **Base de données** : PostgreSQL avec 35 livres pré-indexés

---

## 📈 Performance

- Recherche : < 50ms (mot-clé) / < 200ms (RegEx)
- 35 livres indexés, ~15K mots uniques, ~290K postings
- Graphe : 82 arêtes Jaccard, 3 métriques de centralité
- Interface : responsive mobile/tablette/desktop

---

## 👥 Auteurs

**Hamid ZIBOUCHE & Bih FLAN & Awwal FAGBEHOURO**  
M2 STL - Sorbonne Université - 2024-2025

