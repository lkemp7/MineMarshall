from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    path('forms/mine/', views.my_forms, name='my_forms'),
    path('forms/<int:pk>/', views.view_form, name='view_form'),

    path('personnel/', views.personnel, name='personnel'),
    path("personnel/<int:user_id>/", views.user_profile, name="user_profile"),
    path("metrics/", views.metrics, name="metrics"),
    path('forms/submit/', views.submit_authorization_form, name='submit_authorization_form'),
        path('personnel/<int:pk>/edit/', views.edit_user_profile, name='edit_user_profile'),
]