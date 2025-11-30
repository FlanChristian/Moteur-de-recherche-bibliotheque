# Utiliser l'image officielle Python 3.13
FROM python:3.13-slim

# Définir les variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Créer le répertoire de travail
WORKDIR /app

# Installer les dépendances système nécessaires pour psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copier le fichier requirements.txt
COPY requirements.txt /app/

# Installer les dépendances Python
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install django==5.2.8 gunicorn

# Copier tout le projet dans le conteneur
COPY . /app/

# Créer les répertoires nécessaires
RUN mkdir -p /app/bibliosearch/staticfiles && \
    mkdir -p /app/bibliosearch/media

# Se déplacer dans le répertoire bibliosearch
WORKDIR /app/bibliosearch

# Exposer le port 8000
EXPOSE 8000

# Script d'entrée pour initialiser la base de données
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
