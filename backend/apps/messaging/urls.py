from django.urls import path

from .views import MessageListCreateView

app_name = "messaging"

urlpatterns = [
    path("chats/<int:chat_id>/messages", MessageListCreateView.as_view(), name="messages"),
]
