from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    path('forms/mine/', views.my_forms, name='my_forms'),
    path('forms/<int:pk>/', views.view_form, name='view_form'),

    path('personnel/', views.personnel, name='personnel'),
    path('personnel/add/', views.add_user, name='add_user'),
    path('personnel/<int:user_id>/', views.user_profile, name='user_profile'),
    path('metrics/', views.metrics, name='metrics'),
    path('metrics/invite/<int:invite_id>/review/', views.update_project_invite_review_status, name='update_project_invite_review_status'),
    path('projects/<int:pk>/submissions/', views.project_submissions, name='project_submissions'),
    path('submissions/<int:submission_id>/', views.view_submission, name='view_submission'),
    path('forms/submit/', views.submit_authorization_form, name='submit_authorization_form'),
    path('personnel/<int:pk>/edit/', views.edit_user_profile, name='edit_user_profile'),
    path('personnel/<int:pk>/delete/', views.delete_user, name='delete_user'),
    path('personnel/<int:pk>/credential/', views.save_credential, name='save_credential'),
    path('forms/create/', views.create_form, name='create_form'),
    path('forms/add-question/', views.add_question_field, name='add_question_field'),
    path('forms/<int:pk>/delete/', views.delete_form, name='delete_form'),
    path('forms/<int:pk>/edit-data/', views.edit_form_data, name='edit_form_data'),
    path('forms/<int:pk>/update/', views.update_form, name='update_form'),

    path('projects/home/', views.projects_home, name='projects_home'),
    path('projects/', views.projects, name='projects'),
    path('projects/mine/', views.my_projects, name='my_projects'),
    path('projects/<int:pk>/', views.project_detail, name='project_detail'),
    path('projects/<int:pk>/roles/add/', views.add_project_role, name='add_project_role'),
    path('projects/<int:project_pk>/roles/<int:role_pk>/update-form/', views.update_project_role_form, name='update_project_role_form'),
    path('projects/<int:project_pk>/roles/<int:role_pk>/invite/', views.invite_users_to_project_role, name='invite_users_to_project_role'),
    path('project-invites/<int:invite_id>/form/', views.project_invite_form, name='project_invite_form'),
    path("personnel/induction/", views.start_induction, name="start_induction"),
    path("forms/onboarding-default/<str:token>/", views.onboarding_default_form, name="onboarding_default_form"),
  ]