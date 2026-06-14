from django.urls import path
from . import views

urlpatterns = [
    # HTML Views
    path('', views.dashboard_view, name='home'),
    path('chat/', views.chat_view, name='chat'),
    path('tasks/', views.tasks_view, name='tasks'),
    path('expenses/', views.expenses_view, name='expenses'),
    path('general-chat/', views.general_chat_view, name='general_chat'),
    path('image-studio/', views.image_gen_view, name='image_gen'),
    path('gallery/', views.gallery_view, name='gallery'),
    path('accounts/register/', views.register_view, name='register'),
    path('about/', views.about_view, name='about'),

    # Chat API Endpoints
    path('api/upload/', views.UploadNotesView.as_view(), name='api_upload'),
    path('api/retrain/', views.RetrainDBView.as_view(), name='api_retrain'),
    path('api/chat/', views.ChatView.as_view(), name='api_chat'),
    path('api/notes/', views.NotesListView.as_view(), name='api_notes'),
    path('api/general_chat/', views.GeneralChatAPIView.as_view(), name='api_general_chat'),
    path('api/generate_image/', views.ImageGenerationAPIView.as_view(), name='api_generate_image'),
    path('api/tasks/', views.TasksView.as_view(), name='api_tasks'),
    path('api/expenses/', views.ExpensesView.as_view(), name='api_expenses'),
    path('api/gallery/', views.GalleryAPIView.as_view(), name='api_gallery'),

    # Session Management Endpoints
    path('api/sessions/', views.ChatSessionsView.as_view(), name='api_sessions'),
    path('api/sessions/<int:session_id>/messages/', views.ChatSessionMessagesView.as_view(), name='api_session_messages'),

    # Utility
    path('api/ollama_status/', views.OllamaStatusView.as_view(), name='api_ollama_status'),
    path('api/media/serve/<path:filename>', views.serve_media_view, name='serve_media'),
]
