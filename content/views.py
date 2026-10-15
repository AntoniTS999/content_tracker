from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from content.models import Content
from content.permissions import IsAuthorOrStaffOrReadOnly
from content.serializers import ContentSerializer


class ContentViewSet(viewsets.ModelViewSet):
    queryset = Content.objects.select_related("author")
    serializer_class = ContentSerializer
    permission_classes = [IsAuthenticated, IsAuthorOrStaffOrReadOnly]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
