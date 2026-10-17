from rest_framework.routers import DefaultRouter
from django.urls import path, include
from content.views import ContentViewSet, MyChangesView

router = DefaultRouter()

router.register("contents", ContentViewSet, basename="content")

app_name = "content"

urlpatterns = [
    path("", include(router.urls)),
    path("me/changes/", MyChangesView.as_view(), name="my-changes"),
]
