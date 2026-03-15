# accounts/urls.py
from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('profile/', views.edit_profile, name='profile'),
    path('setup-account/<str:token>/', views.setup_account, name='setup_account'),
]
