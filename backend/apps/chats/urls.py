"""URL-ы чатов. Все ручки требуют авторизации и проверяют членство."""

from django.urls import path

from . import views

app_name = "chats"

urlpatterns = [
    path("chats", views.ChatListCreateView.as_view(), name="list-create"),
    path("chats/<int:chat_id>", views.ChatDetailView.as_view(), name="detail"),
    path("chats/<int:chat_id>/members", views.ChatMembersView.as_view(), name="members"),
    path("chats/<int:chat_id>/read", views.MarkReadView.as_view(), name="mark-read"),
]
