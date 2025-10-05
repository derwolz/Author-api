# books/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
import secrets
import jwt
from django.conf import settings
from .models import (UserProfile, Book, UserBook, BookSite, UserSiteActivity, 
                    CreditTransaction, AuthCode)
from .serializers import UserProfileSerializer, BookSerializer, UserBookSerializer

class UserProfileViewSet(viewsets.ModelViewSet):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserProfile.objects.filter(user=self.request.user)

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user's profile"""
        try:
            profile = UserProfile.objects.get(user=request.user)
            serializer = self.get_serializer(profile)
            return Response(serializer.data)
        except UserProfile.DoesNotExist:
            return Response({'error': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['post'])
    def update_credits(self, request):
        """Update user credits (called by book sites)"""
        site_api_key = request.headers.get('X-API-Key')
        if not site_api_key:
            return Response({'error': 'API key required'}, status=status.HTTP_401_UNAUTHORIZED)
        
        try:
            site = BookSite.objects.get(api_key=site_api_key, is_active=True)
        except BookSite.DoesNotExist:
            return Response({'error': 'Invalid API key'}, status=status.HTTP_401_UNAUTHORIZED)

        profile = UserProfile.objects.get(user=request.user)
        amount = request.data.get('amount', 0)
        transaction_type = request.data.get('type', 'earned')
        description = request.data.get('description', '')

        # Update credits
        if transaction_type == 'spent':
            if profile.credits < abs(amount):
                return Response({'error': 'Insufficient credits'}, status=status.HTTP_400_BAD_REQUEST)
            profile.credits -= abs(amount)
            profile.total_credits_spent += abs(amount)
        else:
            profile.credits += abs(amount)
            profile.total_credits_earned += abs(amount)

        profile.save()

        # Record transaction
        CreditTransaction.objects.create(
            user=profile,
            site=site,
            transaction_type=transaction_type,
            amount=amount,
            description=description
        )

        return Response({
            'credits': profile.credits,
            'transaction_id': CreditTransaction.objects.last().id
        })

class BookViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Book.objects.all()
    serializer_class = BookSerializer
    permission_classes = [IsAuthenticated]

class UserBookViewSet(viewsets.ModelViewSet):
    serializer_class = UserBookSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user_profile = UserProfile.objects.get(user=self.request.user)
        return UserBook.objects.filter(user=user_profile)

    def perform_create(self, serializer):
        user_profile = UserProfile.objects.get(user=self.request.user)
        serializer.save(user=user_profile)

    @action(detail=True, methods=['post'])
    def unlock_chapter(self, request, pk=None):
        """Unlock a chapter using credits"""
        user_book = self.get_object()
        book = user_book.book
        user_profile = user_book.user

        if user_profile.credits >= book.chapter_credit_cost:
            user_profile.credits -= book.chapter_credit_cost
            user_book.unlocked_chapters += 1
            user_profile.save()
            user_book.save()
            
            return Response({
                'message': 'Chapter unlocked successfully',
                'unlocked_chapters': user_book.unlocked_chapters,
                'remaining_credits': user_profile.credits
            })
        else:
            return Response({
                'error': 'Insufficient credits'
            }, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def distributed_login(request):
    """Handle email/password login from any book site - returns JWT tokens"""
    site_api_key = request.headers.get('X-API-Key')
    email = request.data.get('email')
    password = request.data.get('password')
    referral_code = request.data.get('referral_code')
    
    if not site_api_key:
        return Response({'error': 'API key required'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        site = BookSite.objects.get(api_key=site_api_key, is_active=True)
    except BookSite.DoesNotExist:
        return Response({'error': 'Invalid API key'}, status=status.HTTP_401_UNAUTHORIZED)
    
    if not email or not password:
        return Response({'error': 'Email and password required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Try to authenticate existing user
    user = authenticate(username=email, password=password)
    
    if user:
        # Existing user login
        profile = UserProfile.objects.get(user=user)
        
        # Track site activity
        activity, created = UserSiteActivity.objects.get_or_create(
            user=profile,
            site=site,
            defaults={'total_visits': 1}
        )
        if not created:
            activity.total_visits += 1
            activity.save()
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'success': True,
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'credits': profile.credits,
                'referral_code': profile.referral_code,
                'is_new_user': False
            }
        })
    
    else:
        # User doesn't exist - create new account
        try:
            # Check if email already exists
            if User.objects.filter(email=email).exists():
                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
            
            # Create new user
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=request.data.get('first_name', ''),
                last_name=request.data.get('last_name', '')
            )
            
            # Create profile
            profile = UserProfile.objects.create(
                user=user,
                google_id='',
                credits=5  # Welcome bonus
            )
            
            # Process referral if provided
            if referral_code:
                try:
                    referrer = UserProfile.objects.get(referral_code=referral_code)
                    if referrer != profile:
                        profile.referred_by = referrer
                        profile.credits += 5  # Extra referral bonus (10 total)
                        profile.total_credits_earned = 10
                        profile.save()
                        
                        # Give referrer bonus
                        referrer.credits += 10
                        referrer.total_credits_earned += 10
                        referrer.save()
                        
                        # Record transactions
                        CreditTransaction.objects.create(
                            user=profile,
                            site=site,
                            transaction_type='welcome_bonus',
                            amount=10,
                            description='Welcome bonus + referral bonus'
                        )
                        CreditTransaction.objects.create(
                            user=referrer,
                            site=site,
                            transaction_type='referral_bonus',
                            amount=10,
                            description=f'Referral bonus for {user.email}'
                        )
                except UserProfile.DoesNotExist:
                    profile.total_credits_earned = 5
                    profile.save()
                    CreditTransaction.objects.create(
                        user=profile,
                        site=site,
                        transaction_type='welcome_bonus',
                        amount=5,
                        description='Welcome bonus'
                    )
            else:
                profile.total_credits_earned = 5
                profile.save()
                CreditTransaction.objects.create(
                    user=profile,
                    site=site,
                    transaction_type='welcome_bonus',
                    amount=5,
                    description='Welcome bonus'
                )
            
            # Track site activity
            UserSiteActivity.objects.create(
                user=profile,
                site=site,
                total_visits=1
            )
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'success': True,
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'credits': profile.credits,
                    'referral_code': profile.referral_code,
                    'is_new_user': True
                }
            })
            
        except Exception as e:
            return Response({'error': 'Failed to create account'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def google_sso_login(request):
    """Handle Google SSO login from any book site - returns JWT tokens"""
    site_api_key = request.headers.get('X-API-Key')
    google_token = request.data.get('google_token')
    referral_code = request.data.get('referral_code')
    
    if not site_api_key or not google_token:
        return Response({'error': 'API key and Google token required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        site = BookSite.objects.get(api_key=site_api_key, is_active=True)
    except BookSite.DoesNotExist:
        return Response({'error': 'Invalid API key'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        # Verify Google token
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token
        
        idinfo = id_token.verify_oauth2_token(
            google_token, 
            google_requests.Request(),
            audience=settings.GOOGLE_OAUTH_CLIENT_ID
        )
        
        google_id = idinfo['sub']
        email = idinfo['email']
        first_name = idinfo.get('given_name', '')
        last_name = idinfo.get('family_name', '')
        
        # Try to find existing user
        try:
            profile = UserProfile.objects.get(google_id=google_id)
            user = profile.user
            is_new_user = False
        except UserProfile.DoesNotExist:
            try:
                # Check if user exists with this email
                user = User.objects.get(email=email)
                profile = UserProfile.objects.get(user=user)
                # Link Google account
                profile.google_id = google_id
                profile.save()
                is_new_user = False
            except (User.DoesNotExist, UserProfile.DoesNotExist):
                # Create new user
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    first_name=first_name,
                    last_name=last_name
                )
                user.set_unusable_password()
                user.save()
                
                profile = UserProfile.objects.create(
                    user=user,
                    google_id=google_id,
                    credits=5
                )
                is_new_user = True
                
                # Process referral
                if referral_code:
                    try:
                        referrer = UserProfile.objects.get(referral_code=referral_code)
                        if referrer != profile:
                            profile.referred_by = referrer
                            profile.credits += 5
                            profile.total_credits_earned = 10
                            profile.save()
                            
                            referrer.credits += 10
                            referrer.total_credits_earned += 10
                            referrer.save()
                            
                            CreditTransaction.objects.create(
                                user=profile,
                                site=site,
                                transaction_type='welcome_bonus',
                                amount=10,
                                description='Welcome + referral bonus'
                            )
                            CreditTransaction.objects.create(
                                user=referrer,
                                site=site,
                                transaction_type='referral_bonus',
                                amount=10,
                                description=f'Referral bonus for {user.email}'
                            )
                    except UserProfile.DoesNotExist:
                        profile.total_credits_earned = 5
                        profile.save()
        
        # Track activity
        activity, created = UserSiteActivity.objects.get_or_create(
            user=profile,
            site=site,
            defaults={'total_visits': 1}
        )
        if not created:
            activity.total_visits += 1
            activity.save()
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'success': True,
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'credits': profile.credits,
                'referral_code': profile.referral_code,
                'is_new_user': is_new_user
            }
        })
        
    except ValueError:
        return Response({'error': 'Invalid Google token'}, status=status.HTTP_401_UNAUTHORIZED)
    except Exception:
        return Response({'error': 'Login failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_auth_code(request):
    """Generate auth code for cross-site navigation"""
    target_site_domain = request.data.get('target_site')
    
    if not target_site_domain:
        return Response({'error': 'target_site required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        target_site = BookSite.objects.get(domain=target_site_domain, is_active=True)
    except BookSite.DoesNotExist:
        return Response({'error': 'Invalid target site'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Generate auth code
    auth_code = f"AC_{secrets.token_urlsafe(16)}"
    expires_at = timezone.now() + timedelta(minutes=5)
    
    profile = UserProfile.objects.get(user=request.user)
    
    # Store in cache
    cache_data = {
        'user_id': request.user.id,
        'target_site_id': target_site.id,
        'expires_at': expires_at.isoformat()
    }
    cache.set(f"auth_code:{auth_code}", cache_data, timeout=300)
    
    return Response({
        'auth_code': auth_code,
        'auth_url': f"https://{target_site_domain}/auth/login?code={auth_code}",
        'expires_in': 300
    })

@api_view(['POST'])
@permission_classes([AllowAny])
def exchange_auth_code(request):
    """Exchange auth code for JWT tokens"""
    auth_code = request.data.get('code')
    site_api_key = request.headers.get('X-API-Key')
    
    if not site_api_key or not auth_code:
        return Response({'error': 'API key and auth code required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        site = BookSite.objects.get(api_key=site_api_key, is_active=True)
    except BookSite.DoesNotExist:
        return Response({'error': 'Invalid API key'}, status=status.HTTP_401_UNAUTHORIZED)
    
    # Get auth data from cache
    cache_key = f"auth_code:{auth_code}"
    auth_data = cache.get(cache_key)
    
    if not auth_data:
        return Response({'error': 'Invalid or expired auth code'}, status=status.HTTP_401_UNAUTHORIZED)
    
    # Verify target site
    if auth_data['target_site_id'] != site.id:
        return Response({'error': 'Auth code not valid for this site'}, status=status.HTTP_401_UNAUTHORIZED)
    
    # Delete code (single use)
    cache.delete(cache_key)
    
    try:
        user = User.objects.get(id=auth_data['user_id'])
        profile = UserProfile.objects.get(user=user)
    except (User.DoesNotExist, UserProfile.DoesNotExist):
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Track activity
    activity, created = UserSiteActivity.objects.get_or_create(
        user=profile,
        site=site,
        defaults={'total_visits': 1}
    )
    if not created:
        activity.total_visits += 1
        activity.save()
    
    # Generate JWT tokens
    refresh = RefreshToken.for_user(user)
    
    return Response({
        'success': True,
        'access_token': str(refresh.access_token),
        'refresh_token': str(refresh),
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'credits': profile.credits,
            'referral_code': profile.referral_code
        }
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_cross_promo_sites(request):
    """Get cross-promotion links with auth codes"""
    current_site_domain = request.GET.get('current_site')
    
    sites = BookSite.objects.filter(is_active=True)
    if current_site_domain:
        sites = sites.exclude(domain=current_site_domain)
    
    site_data = []
    for site in sites:
        # Generate auth code for each site
        auth_code = f"AC_{secrets.token_urlsafe(16)}"
        expires_at = timezone.now() + timedelta(minutes=5)
        
        cache_data = {
            'user_id': request.user.id,
            'target_site_id': site.id,
            'expires_at': expires_at.isoformat()
        }
        cache.set(f"auth_code:{auth_code}", cache_data, timeout=300)
        
        site_data.append({
            'name': site.name,
            'domain': site.domain,
            'auth_url': f"https://{site.domain}/auth/login?code={auth_code}"
        })
    
    return Response({'sites': site_data})
