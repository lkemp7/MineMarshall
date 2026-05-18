from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('profile/', views.edit_profile, name='profile'),
    path('setup-account/<str:token>/', views.setup_account, name='setup_account'),

    path('licence-scan/<str:token>/', views.licence_scan, name='licence_scan'),

    path('licence-renewal/<str:token>/', views.licence_renewal_upload, name='licence_renewal_upload'),
    path('licence-renewal/<str:token>/confirm/', views.licence_renewal_confirm, name='licence_renewal_confirm'),
    path('licence-renewal/<str:token>/success/', views.licence_renewal_success, name='licence_renewal_success'),
]