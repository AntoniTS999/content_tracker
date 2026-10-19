from django.shortcuts import get_object_or_404
from rest_framework import generics, viewsets, mixins
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.decorators import action
from django.db.models import F
from rest_framework.response import Response
from content.models import Content, UserContentState
from content import services
from content.permissions import IsAuthorOrStaffOrReadOnly
from content.serializers import (
    ChangedContentSerializer,
    ContentSerializer,
    ContentRevisionSerializer,
)
from users.models import User


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

    def get_states(self, contents):
        states = UserContentState.objects.filter(
            user=self.request.user, content__in=contents
        )
        return {state.content_id: state for state in states}

    def list(self, request, *args, **kwargs):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        context = self.get_serializer_context()
        context["states"] = self.get_states(page)
        serializer = self.get_serializer(page, many=True, context=context)
        return self.get_paginated_response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        content = self.get_object()
        context = self.get_serializer_context()
        context["states"] = self.get_states([content])
        data = self.get_serializer(content, context=context).data
        services.mark_seen(request.user, content)
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

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        content = self.get_object()
        state = UserContentState.objects.filter(
            user=request.user, content=content
        ).first()
        context = self.get_serializer_context()
        context["seen_version"] = state.last_seen_version if state else None

        revisions = content.revisions.select_related("editor").order_by("-version")
        page = self.paginate_queryset(revisions)
        serializer = ContentRevisionSerializer(page, many=True, context=context)
        return self.get_paginated_response(serializer.data)


class MyChangesView(generics.ListAPIView):
    serializer_class = ChangedContentSerializer

    def get_target_user(self):
        return self.request.user

    def get_queryset(self):
        return (
            UserContentState.objects.filter(
                user=self.get_target_user(),
                is_watching=True,
                content__version__gt=F("last_seen_version"),
            )
            .select_related("content")
            .order_by("-content__last_changed_at")
        )


class UserChangesView(MyChangesView):
    permission_classes = [IsAdminUser]

    def get_target_user(self):
        return get_object_or_404(User, pk=self.kwargs["user_id"])
