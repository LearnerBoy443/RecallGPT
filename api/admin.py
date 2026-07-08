from django.contrib import admin
from .models import UserProfile, ChatSession, ChatMessage, ImageMemory, DatabaseFile

admin.site.register(UserProfile)
admin.site.register(ChatSession)
admin.site.register(ChatMessage)
admin.site.register(ImageMemory)
admin.site.register(DatabaseFile)
