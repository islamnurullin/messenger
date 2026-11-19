from django.contrib import admin

from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "chat", "seq", "sender", "short_body", "created_at")
    list_filter = ("created_at",)
    search_fields = ("body", "sender__username")
    raw_id_fields = ("chat", "sender")
    ordering = ("-id",)

    @admin.display(description="текст")
    def short_body(self, obj: Message) -> str:
        return obj.body[:60]
