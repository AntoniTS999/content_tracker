from rest_framework import generics, viewsets, mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django.db.models import F
from rest_framework.response import Response
from content.models import Content, UserContentState
from content import services
from content.permissions import IsAuthorOrStaffOrReadOnly
from content.serializers import ChangedContentSerializer, ContentSerializer


class ContentViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Content.objects.select_related("author")
    serializer_class = ContentSerializer
    permission_classes = [IsAuthenticated, IsAuthorOrStaffOrReadOnly]

    def retrieve(self, request, *args, **kwargs):
        content = self.get_object()
        data = self.get_serializer(content).data
        services.mark_seen(request.user, content)  # otwarcie szczegółów = przeczytane
        return Response(data)

    @action(
        detail=True, methods=["post", "delete"], permission_classes=[IsAuthenticated]
    )
    def watch(self, request, pk=None):
        content = self.get_object()
        if request.method == "POST":
            started = services.start_watching(request.user, content)
            return Response({"watching": True}, status=201 if started else 200)
        services.stop_watching(request.user, content)
        return Response(status=204)


class MyChangesView(generics.ListAPIView):
    serializer_class = ChangedContentSerializer

    def get_queryset(self):
        return (
            UserContentState.objects.filter(
                user=self.request.user,
                is_watching=True,
                content__version__gt=F("last_seen_version"),
            )
            .select_related("content")
            .order_by("-content__last_changed_at")
        )
