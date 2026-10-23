from django.urls import path

from .health import health

app_name = "common"

urlpatterns = [
    path("health", health, name="health"),
]
