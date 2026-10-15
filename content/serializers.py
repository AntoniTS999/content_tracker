from rest_framework import serializers

from content import services
from content.models import Content
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
