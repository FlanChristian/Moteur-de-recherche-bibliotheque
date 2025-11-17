from django.shortcuts import render
from .models import Book

def home(request):
    # Top : les plus consultés (pour l’instant on met juste les premiers)
    most_viewed = Book.objects.all()[:5]

    # Catégories basées sur un champ fictif "category" (à adapter à ton modèle)
    categories = ["Tout", "Sci-Fi", "Drame", "Education"]
    current_category = request.GET.get("category")

    if current_category and current_category != "Tout":
        category_books = Book.objects.filter(category=current_category)[:10]
    else:
        category_books = Book.objects.all()[:10]

    return render(request, "search/home.html", {
        "most_viewed": most_viewed,
        "categories": categories,
        "current_category": current_category,
        "category_books": category_books,
    })

