from rest_framework import serializers

from content import services
from content.models import Content, UserContentState
from users.serializers import UserSerializer


class ContentSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

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
        ]
        read_only_fields = ["version", "last_changed_at", "created_at"]

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
