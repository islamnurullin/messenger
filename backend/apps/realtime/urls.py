from django.urls import path

from .views import ConnectionTokenView, SubscriptionTokenView

app_name = "realtime"

urlpatterns = [
    path("realtime/token", ConnectionTokenView.as_view(), name="token"),
    path("realtime/subscribe", SubscriptionTokenView.as_view(), name="subscribe"),
]
