from django.contrib import admin

from .models import Chat, ChatMember


class ChatMemberInline(admin.TabularInline):
    model = ChatMember
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "title", "last_seq", "created_at")
    list_filter = ("type",)
    search_fields = ("title", "direct_key")
    inlines = (ChatMemberInline,)
    readonly_fields = ("last_seq", "created_at", "updated_at")


@admin.register(ChatMember)
class ChatMemberAdmin(admin.ModelAdmin):
    list_display = ("chat", "user", "role", "last_read_seq", "joined_at")
    list_filter = ("role",)
    search_fields = ("user__username",)
    autocomplete_fields = ("chat", "user")
