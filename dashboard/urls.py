from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    # Forms
    path('forms/create/', views.create_form, name='create_form'),
    path('forms/mine/', views.my_forms, name='my_forms'),
    path('forms/<int:pk>/', views.view_form, name='view_form'),
    path('forms/<int:pk>/assign/', views.assign_form, name='assign_form'),
    path('forms/<int:pk>/analytics/', views.form_analytics, name='form_analytics'),
    path('forms/<int:pk>/delete/', views.delete_form, name='delete_form'),

    # Personnel
    path('personnel/', views.personnel, name='personnel'),
    path("personnel/<int:user_id>/", views.user_profile, name="user_profile"),
    path("metrics/", views.metrics, name="metrics")
]