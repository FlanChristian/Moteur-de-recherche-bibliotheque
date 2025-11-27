from django.contrib import admin
from .models import Book, BookText, Word, Posting


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'author', 'word_count', 'language', 'created_at']
    list_filter = ['language', 'created_at']
    search_fields = ['title', 'author', 'gutenberg_id']
    readonly_fields = ['gutenberg_id', 'word_count', 'created_at']
    
    fieldsets = (
        ('Informations principales', {
            'fields': ('gutenberg_id', 'title', 'author', 'language')
        }),
        ('Statistiques', {
            'fields': ('word_count', 'path_txt', 'created_at')
        }),
    )


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ['id', 'w']
    search_fields = ['w']
    ordering = ['w']


@admin.register(Posting)
class PostingAdmin(admin.ModelAdmin):
    list_display = ['word', 'book', 'cnt']
    list_filter = ['book']
    search_fields = ['word__w', 'book__title']
    raw_id_fields = ['word', 'book']


@admin.register(BookText)
class BookTextAdmin(admin.ModelAdmin):
    list_display = ['book', 'content_preview']
    search_fields = ['book__title']
    raw_id_fields = ['book']
    
    def content_preview(self, obj):
        return obj.content[:100] + "..." if len(obj.content) > 100 else obj.content
    
    content_preview.short_description = 'Aperçu du contenu'