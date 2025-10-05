# books/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
import uuid
import secrets
from .models import (UserProfile, Book, UserBook, BookSite, UserSiteActivity, 
                    CreditTransaction, AuthCode)

@admin.register(BookSite)
class BookSiteAdmin(admin.ModelAdmin):
    list_display = ('name', 'domain', 'api_key_display', 'is_active', 'total_users', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'domain')
    readonly_fields = ('api_key', 'created_at', 'total_users_display')
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'domain', 'is_active')
        }),
        ('API Configuration', {
            'fields': ('api_key',),
            'description': 'Use this API key in your book site headers as X-API-Key'
        }),
        ('Statistics', {
            'fields': ('total_users_display',),
        }),
        ('Timestamps', {
            'fields': ('created_at',),
        }),
    )

    def api_key_display(self, obj):
        """Display masked API key in list view"""
        if obj.api_key:
            masked = obj.api_key[:8] + '...' + obj.api_key[-4:]
            return format_html(
                '<code style="background: #f0f0f0; padding: 2px 4px;">{}</code>',
                masked
            )
        return 'No API key'
    api_key_display.short_description = 'API Key'

    def total_users(self, obj):
        """Count of users who have visited this site"""
        return UserSiteActivity.objects.filter(site=obj).count()
    total_users.short_description = 'Total Users'

    def total_users_display(self, obj):
        """Detailed user stats for the detail view"""
        if obj.pk:
            total = UserSiteActivity.objects.filter(site=obj).count()
            active = UserSiteActivity.objects.filter(site=obj, last_visit__gte=timezone.now() - timedelta(days=30)).count()
            return format_html(
                '<strong>Total:</strong> {} users<br>'
                '<strong>Active (30 days):</strong> {} users',
                total, active
            )
        return 'Save first to see stats'
    total_users_display.short_description = 'User Statistics'

    def change_view(self, request, object_id, form_url='', extra_context=None):
        """Add API key actions to the change view"""
        extra_context = extra_context or {}
        if object_id:
            obj = self.get_object(request, object_id)
            if obj and obj.api_key:
                extra_context['api_key_actions'] = format_html(
                    '<div style="margin: 15px 0; padding: 15px; background: #f8f9fa; border-radius: 5px;">'
                    '<h3>API Key Management</h3>'
                    '<p><strong>Current API Key:</strong></p>'
                    '<code style="background: #e9ecef; padding: 8px; border-radius: 3px; display: block; margin: 10px 0; word-break: break-all;">{}</code>'
                    '<button type="button" onclick="copyApiKey()" class="button" style="margin-right: 10px;">'
                    '📋 Copy API Key</button>'
                    '<button type="button" onclick="regenerateApiKey()" class="button" style="background: #dc3545; color: white;">'
                    '🔄 Regenerate API Key</button>'
                    '<script>'
                    'function copyApiKey() {{'
                    '  navigator.clipboard.writeText("{}").then(() => {{'
                    '    alert("API Key copied to clipboard!");'
                    '  }});'
                    '}}'
                    'function regenerateApiKey() {{'
                    '  if(confirm("This will invalidate the current API key and may break existing integrations. Continue?")) {{'
                    '    fetch("/admin/books/booksite/{}/regenerate-api-key/", {{'
                    '      method: "POST",'
                    '      headers: {{"X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]").value}}'
                    '    }}).then(response => response.json()).then(data => {{'
                    '      if(data.success) {{'
                    '        alert("API key regenerated successfully!");'
                    '        location.reload();'
                    '      }} else {{'
                    '        alert("Error: " + data.error);'
                    '      }}'
                    '    }});'
                    '  }}'
                    '}}'
                    '</script>'
                    '</div>',
                    obj.api_key, obj.api_key, object_id
                )
        return super().change_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        """Auto-generate API key for new sites"""
        if not change or not obj.api_key:  # New object or missing API key
            obj.api_key = f"bk_{secrets.token_urlsafe(32)}"
            messages.success(request, f'New API key generated: {obj.api_key}')
        super().save_model(request, obj, form, change)

    def get_urls(self):
        """Add custom URL for API key regeneration"""
        urls = super().get_urls()
        custom_urls = [
            path('<int:site_id>/regenerate-api-key/', 
                 self.admin_site.admin_view(self.regenerate_api_key), 
                 name='regenerate_api_key'),
        ]
        return custom_urls + urls

    def regenerate_api_key(self, request, site_id):
        """Regenerate API key for a site"""
        if request.method == 'POST':
            try:
                site = BookSite.objects.get(pk=site_id)
                old_key = site.api_key
                site.api_key = f"bk_{secrets.token_urlsafe(32)}"
                site.save()
                
                messages.success(request, f'API key regenerated successfully!')
                return JsonResponse({'success': True, 'new_key': site.api_key})
            except BookSite.DoesNotExist:
                return JsonResponse({'error': 'Site not found'}, status=404)
        
        return JsonResponse({'error': 'Invalid request'}, status=400)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'credits', 'total_credits_earned', 'referral_code', 'referred_by', 'created_at')
    list_filter = ('created_at', 'referred_by')
    search_fields = ('user__username', 'user__email', 'referral_code')
    readonly_fields = ('referral_code', 'created_at', 'google_id')
    
    fieldsets = (
        ('User Info', {
            'fields': ('user', 'google_id')
        }),
        ('Credits', {
            'fields': ('credits', 'total_credits_earned', 'total_credits_spent')
        }),
        ('Referrals', {
            'fields': ('referral_code', 'referred_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'last_active')
        }),
    )

@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'available_chapters', 'free_chapters', 'chapter_credit_cost', 'price', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('title',)

@admin.register(UserBook)
class UserBookAdmin(admin.ModelAdmin):
    list_display = ('user', 'book', 'unlocked_chapters', 'last_chapter_read', 'chapter_progress_percent', 'digital_purchased', 'audio_purchased')
    list_filter = ('digital_purchased', 'audio_purchased', 'created_at')
    search_fields = ('user__user__username', 'book__title')

@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'site', 'transaction_type', 'amount', 'description', 'created_at')
    list_filter = ('transaction_type', 'site', 'created_at')
    search_fields = ('user__user__username', 'description')
    readonly_fields = ('created_at',)

@admin.register(UserSiteActivity)
class UserSiteActivityAdmin(admin.ModelAdmin):
    list_display = ('user', 'site', 'total_visits', 'first_visit', 'last_visit')
    list_filter = ('site', 'first_visit', 'last_visit')
    search_fields = ('user__user__username', 'site__name')

@admin.register(AuthCode)
class AuthCodeAdmin(admin.ModelAdmin):
    list_display = ('code_display', 'user', 'target_site', 'used', 'expires_at', 'created_at')
    list_filter = ('used', 'target_site', 'created_at', 'expires_at')
    search_fields = ('user__user__username', 'target_site__name')
    readonly_fields = ('code', 'created_at', 'used_at')

    def code_display(self, obj):
        """Display masked auth code"""
        if obj.code:
            return f"{obj.code[:5]}...{obj.code[-5:]}"
        return 'No code'
    code_display.short_description = 'Auth Code'

# Custom admin site header
admin.site.site_header = "ValkyrieX Truck API Administration"
admin.site.site_title = "ValkyrieX Admin"
admin.site.index_title = "Book Network Management"

# Add some custom CSS for better API key display
class BookSiteAdminMedia:
    css = {
        'all': ('admin/css/custom_admin.css',)
    }

# books/static/admin/css/custom_admin.css (create this file)
"""
.api-key-section {
    background: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 4px;
    padding: 15px;
    margin: 10px 0;
}

.api-key-code {
    font-family: 'Monaco', 'Consolas', monospace;
    background: #f4f4f4;
    padding: 8px 12px;
    border-radius: 4px;
    border: 1px solid #ddd;
    display: inline-block;
    margin: 5px 0;
    word-break: break-all;
}

.api-key-actions button {
    margin-right: 10px;
    padding: 8px 15px;
    border-radius: 4px;
    border: none;
    cursor: pointer;
}

.copy-btn {
    background: #007cba;
    color: white;
}

.regenerate-btn {
    background: #dc3545;
    color: white;
}
"""
