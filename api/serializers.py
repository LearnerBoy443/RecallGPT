# api/serializers.py

from rest_framework import serializers
from .models import ChatSession, ChatMessage

class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ['id', 'role', 'content', 'timestamp']


class ChatSessionSerializer(serializers.ModelSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)
    message_count = serializers.SerializerMethodField()
    formatted_created_at = serializers.SerializerMethodField()

    class Meta:
        model = ChatSession
        fields = ['id', 'title', 'chat_type', 'created_at', 'formatted_created_at', 'message_count', 'messages']

    def get_message_count(self, obj):
        return obj.messages.count()

    def get_formatted_created_at(self, obj):
        return obj.created_at.strftime('%b %d, %H:%M')


class TaskSerializer(serializers.Serializer):
    task = serializers.CharField(max_length=500)
    status = serializers.CharField(max_length=20)
    date = serializers.CharField(max_length=50, allow_null=True, required=False)


class ExpenseSerializer(serializers.Serializer):
    category = serializers.CharField(max_length=255)
    amount = serializers.FloatField()
    date = serializers.CharField(max_length=50, allow_null=True, required=False)
