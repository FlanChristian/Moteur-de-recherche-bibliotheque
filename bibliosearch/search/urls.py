# search/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('book/<int:book_id>/', views.book_detail, name='book_detail'),
    path('search/', views.search, name='search'),
    path('search/word/', views.search_by_word, name='search_by_word'),
]



