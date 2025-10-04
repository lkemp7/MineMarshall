from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name = 'dashboard'),
    path('forms/create/', views.create_form, name='create_form'),
    path('forms/mine/', views.my_forms, name='my_forms'),
    path('forms/<int:pk>/', views.view_form, name='view_form')
]