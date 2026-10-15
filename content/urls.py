from rest_framework.routers import DefaultRouter
from django.urls import path, include
from content.views import ContentViewSet

router = DefaultRouter()

router.register("contents", ContentViewSet, basename="content")

app_name = "content"

urlpatterns = [
    path("", include(router.urls)),
]
