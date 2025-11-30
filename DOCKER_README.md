# 🐳 Guide Docker Compose - BiblioSearch

Ce guide explique comment déployer BiblioSearch avec Docker Compose.

---

## 🚀 Démarrage Rapide

```bash
# Cloner le projet
git clone https://github.com/FlanChristian/Moteur-de-recherche-bibliotheque.git
cd Moteur-de-recherche-bibliotheque

# Lancer les conteneurs
docker compose up
```

Le site sera accessible sur : **http://localhost:8000**

---

## ⚠️ Important : Premier Lancement

### Problème connu au premier démarrage

Au **premier lancement**, il est **normal** que le site ne réponde pas pendant environ **5 minutes**, même si les logs indiquent que les services sont prêts.

**Pourquoi ?**

Lorsque PostgreSQL démarre pour la première fois, il doit :
1. **Initialiser la structure** de la base de données (tables, index)
2. **Charger toutes les données** depuis l'image Docker (1726 livres, 13M postings, 47K arêtes)
3. **Construire les index B-tree** pour optimiser les recherches

Ce processus prend du temps car :
- **738 502 mots uniques** doivent être indexés
- **13 046 418 postings** doivent être insérés
- **47 143 arêtes Jaccard** doivent être chargées
- Les **index PostgreSQL** doivent être construits (peut prendre 3-5 minutes)

Le `healthcheck` dans `docker-compose.yml` vérifie uniquement que PostgreSQL **accepte les connexions**, mais **pas que les données sont entièrement chargées**.

### Solution

Si après **5 minutes** le site ne répond toujours pas :

```bash
# 1. Arrêter les conteneurs avec Ctrl+C
^C

# 2. Relancer
docker compose up
```

Au **second lancement**, les données sont déjà présentes dans le volume Docker, donc le démarrage sera **instantané** (< 10 secondes).

---

## 🔧 Commandes Utiles

```bash
# Démarrer en arrière-plan
docker compose up -d

# Voir les logs
docker compose logs -f

# Arrêter les services
docker compose down

# Supprimer tout (volumes inclus)
docker compose down -v
```

---

## 🌐 Compatibilité Mac M1/M2

Le `docker-compose.yml` inclut `platform: linux/amd64` pour assurer la compatibilité.

Sur Mac M1/M2, le premier démarrage peut prendre **7-8 minutes** au lieu de 5 (émulation Rosetta 2).

---

## 📚 Ressources

- **Images Docker** :
  - Application : `hamidzch/bibliosearch:latest`
  - Base de données : `hamidzch/bibliosearch-db:latest`

- **Repository GitHub** : https://github.com/FlanChristian/Moteur-de-recherche-bibliotheque

- **Site démo** : https://bibliosearch.hamid-zibouche.fr

---

**Auteurs** : Hamid ZIBOUCHE & Bih FLAN & Awwal FAGBEHOURO  
M2 STL - Sorbonne Université - 2024-2025
