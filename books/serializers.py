
# books/serializers.py
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile, Book, UserBook

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = UserProfile
        fields = ['user', 'google_id', 'referral_code', 'referred_by', 'credits', 'created_at']
        read_only_fields = ['referral_code', 'created_at']

class BookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Book
        fields = ['id', 'title', 'available_chapters', 'free_chapters', 
                 'chapter_credit_cost', 'digital_credit_cost', 'audio_credit_cost', 
                 'price', 'created_at']

class UserBookSerializer(serializers.ModelSerializer):
    book = BookSerializer(read_only=True)
    book_id = serializers.IntegerField(write_only=True)
    
    class Meta:
        model = UserBook
        fields = ['id', 'book', 'book_id', 'unlocked_chapters', 'last_chapter_read',
                 'chapter_progress_percent', 'digital_purchased', 'audio_purchased',
                 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']
