# books/models.py
from django.db import models
from django.contrib.auth.models import User
import uuid

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    google_id = models.CharField(max_length=100, unique=True)
    referral_code = models.CharField(max_length=20, unique=True, default=uuid.uuid4)
    referred_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True)
    credits = models.IntegerField(default=0)
    total_credits_earned = models.IntegerField(default=0)
    total_credits_spent = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    last_active = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - Credits: {self.credits}"

class BookSite(models.Model):
    """Track different book websites in the network"""
    name = models.CharField(max_length=100)
    domain = models.CharField(max_length=200, unique=True)
    api_key = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.domain})"

class UserSiteActivity(models.Model):
    """Track which sites users have visited"""
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    site = models.ForeignKey(BookSite, on_delete=models.CASCADE)
    first_visit = models.DateTimeField(auto_now_add=True)
    last_visit = models.DateTimeField(auto_now=True)
    total_visits = models.IntegerField(default=1)

    class Meta:
        unique_together = ('user', 'site')

class AuthCode(models.Model):
    """Track auth codes for security auditing"""
    code = models.CharField(max_length=50, unique=True)
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    target_site = models.ForeignKey(BookSite, on_delete=models.CASCADE)
    referral_code = models.CharField(max_length=20, null=True, blank=True)
    used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Auth code for {self.user.user.username} → {self.target_site.name}"

class CreditTransaction(models.Model):
    """Track all credit transactions across the network"""
    TRANSACTION_TYPES = [
        ('earned', 'Earned'),
        ('spent', 'Spent'),
        ('referral_bonus', 'Referral Bonus'),
        ('welcome_bonus', 'Welcome Bonus'),
    ]
    
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    site = models.ForeignKey(BookSite, on_delete=models.CASCADE, null=True, blank=True)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.IntegerField()
    description = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.user.username} {self.transaction_type} {self.amount} credits"

class Book(models.Model):
    title = models.CharField(max_length=200)
    available_chapters = models.IntegerField(default=0)
    free_chapters = models.IntegerField(default=0)
    chapter_credit_cost = models.IntegerField(default=1)
    digital_credit_cost = models.IntegerField(default=0)
    audio_credit_cost = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class UserBook(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    book = models.ForeignKey(Book, on_delete=models.CASCADE)
    unlocked_chapters = models.IntegerField(default=0)
    last_chapter_read = models.IntegerField(default=0)
    chapter_progress_percent = models.FloatField(default=0.0)
    digital_purchased = models.BooleanField(default=False)
    audio_purchased = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'book')

    def __str__(self):
        return f"{self.user.user.username} - {self.book.title}"

