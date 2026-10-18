from rest_framework import serializers

from content import services
from content.models import Content, UserContentState
from users.serializers import UserSerializer


class ContentSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    is_watching = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    versions_behind = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = [
            "id",
            "title",
            "body",
            "content_type",
            "author",
            "version",
            "last_changed_at",
            "created_at",
            "is_watching",
            "status",
            "versions_behind",
        ]
        read_only_fields = ["version", "last_changed_at", "created_at"]

    def get_is_watching(self, obj):
        states = self.context.get("states")
        if states is None:
            return None
        state = states.get(obj.pk)
        return bool(state and state.is_watching)

    def get_status(self, obj):
        states = self.context.get("states")
        if states is None:
            return None
        state = states.get(obj.pk)
        if state is None:
            return "unseen"
        return "updated" if obj.version > state.last_seen_version else "up_to_date"

    def get_versions_behind(self, obj):
        states = self.context.get("states")
        if states is None:
            return None
        state = states.get(obj.pk)
        if state is None:
            return None
        return max(obj.version - state.last_seen_version, 0)

    def create(self, validated_data):
        user = self.context["request"].user
        return services.create_content(user, **validated_data)

    def update(self, instance, validated_data):
        user = self.context["request"].user
        services.update_content(instance, user, validated_data)
        return instance


class ChangedContentSerializer(serializers.ModelSerializer):
    content_id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(source="content.title")
    content_type = serializers.CharField(source="content.content_type")
    current_version = serializers.IntegerField(source="content.version")
    last_changed_at = serializers.DateTimeField(source="content.last_changed_at")
    versions_behind = serializers.SerializerMethodField()

    class Meta:
        model = UserContentState
        fields = [
            "content_id",
            "title",
            "content_type",
            "last_seen_version",
            "current_version",
            "versions_behind",
            "last_changed_at",
        ]

    def get_versions_behind(self, obj):
        return obj.content.version - obj.last_seen_version
