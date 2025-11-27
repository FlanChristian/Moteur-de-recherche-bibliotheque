from django.db import models

class Book(models.Model):
    gutenberg_id = models.BigIntegerField(unique=True, null=True)
    title = models.TextField()
    author = models.TextField(null=True, blank=True)
    language = models.TextField(null=True, blank=True)
    word_count = models.IntegerField()
    path_txt = models.TextField(null=True, blank=True)
    cover_url = models.TextField(null=True, blank=True)  # 🆕 Cette ligne
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'books'
        managed = False

    def __str__(self):
        return self.title

    @property
    def cover_color(self):
        """Génère une couleur basée sur l'ID du livre"""
        colors = ['#94a3b8', '#64748b', '#475569', '#334155', '#1e293b']
        return colors[self.id % len(colors)]


class BookText(models.Model):
    """
    Modèle correspondant à la table 'book_texts'
    """
    book = models.OneToOneField(Book, primary_key=True, on_delete=models.CASCADE, db_column='book_id')
    content = models.TextField()

    class Meta:
        db_table = 'book_texts'
        managed = False

    def __str__(self):
        return f"Texte de {self.book.title}"


class Word(models.Model):
    """
    Modèle correspondant à la table 'words'
    """
    w = models.TextField(unique=True)

    class Meta:
        db_table = 'words'
        managed = False

    def __str__(self):
        return self.w


class Posting(models.Model):
    """
    Modèle correspondant à la table 'postings'
    """
    word = models.ForeignKey(Word, on_delete=models.CASCADE, db_column='word_id')
    book = models.ForeignKey(Book, on_delete=models.CASCADE, db_column='book_id')
    cnt = models.IntegerField()

    class Meta:
        db_table = 'postings'
        managed = False
        unique_together = ('word', 'book')

    def __str__(self):
        return f"{self.word.w} dans {self.book.title} ({self.cnt}x)"