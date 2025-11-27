from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Count
from .models import Book, BookText, Word, Posting


def home(request):
    """Page d'accueil avec les livres les plus consultés"""
    
    # Récupère tous les livres
    all_books = Book.objects.all().order_by('-word_count')[:50]
    
    # Pour les livres populaires, on prend ceux avec le plus de mots
    popular_books = all_books[:5]
    
    # Pour la section catégorie, on affiche les 10 premiers
    category_books = all_books[:10]
    
    # Si une recherche est effectuée
    search_query = request.GET.get('q', '').strip()
    if search_query:
        # Recherche dans le titre ou l'auteur
        category_books = Book.objects.filter(
            Q(title__icontains=search_query) | 
            Q(author__icontains=search_query)
        ).order_by('-word_count')[:20]
    
    context = {
        'popular_books': popular_books,
        'category_books': category_books,
        'search_query': search_query,
    }
    return render(request, 'search/home.html', context)


def book_detail(request, book_id):
    """Page de détail d'un livre"""
    book = get_object_or_404(Book, id=book_id)
    
    # Récupère le contenu du livre si disponible
    try:
        book_text = BookText.objects.get(book=book)
        content_preview = book_text.content[:500] + "..." if len(book_text.content) > 500 else book_text.content
    except BookText.DoesNotExist:
        content_preview = "Contenu non disponible"
    
    # Récupère les mots les plus fréquents du livre
    top_words = Posting.objects.filter(book=book).select_related('word').order_by('-cnt')[:10]
    
    # Livres similaires (même auteur)
    related_books = Book.objects.filter(author=book.author).exclude(id=book.id)[:5]
    
    context = {
        'book': book,
        'content_preview': content_preview,
        'top_words': top_words,
        'related_books': related_books,
    }
    return render(request, 'search/book_detail.html', context)


def search(request):
    """Recherche avancée de livres"""
    query = request.GET.get('q', '').strip()
    results = []
    
    if query:
        # Recherche dans les titres et auteurs
        results = Book.objects.filter(
            Q(title__icontains=query) | 
            Q(author__icontains=query)
        ).order_by('-word_count')
    
    context = {
        'query': query,
        'results': results,
        'count': results.count() if results else 0
    }
    return render(request, 'search/search_results.html', context)


def search_by_word(request):
    """Recherche de livres contenant un mot spécifique"""
    word_query = request.GET.get('word', '').strip().lower()
    results = []
    
    if word_query:
        # Trouve le mot dans la table words
        try:
            word_obj = Word.objects.get(w=word_query)
            # Récupère tous les livres contenant ce mot, triés par nombre d'occurrences
            postings = Posting.objects.filter(word=word_obj).select_related('book').order_by('-cnt')[:50]
            results = [{'book': p.book, 'count': p.cnt} for p in postings]
        except Word.DoesNotExist:
            results = []
    
    context = {
        'word': word_query,
        'results': results,
    }
    return render(request, 'search/word_search.html', context)