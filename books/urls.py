# books/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views

router = DefaultRouter()
router.register('profile', views.UserProfileViewSet, basename='userprofile')
router.register('books', views.BookViewSet)
router.register('user-books', views.UserBookViewSet, basename='userbook')

urlpatterns = [
    path('', views.index, name='index'),
    path('api/', include(router.urls)),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # Distributed authentication (returns JWT tokens)
    path('api/auth/login/', views.distributed_login, name='distributed_login'),
    path('api/auth/google-login/', views.google_sso_login, name='google_sso_login'),
    # Cross-site navigation  
    path('api/auth/generate-code/', views.generate_auth_code, name='generate_auth_code'),
    path('api/auth/exchange-code/', views.exchange_auth_code, name='exchange_auth_code'),
    path('api/sites/cross-promo/', views.get_cross_promo_sites, name='cross_promo_sites'),
]
