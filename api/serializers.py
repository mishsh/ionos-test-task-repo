import os
from django.conf import settings
from rest_framework import serializers

from api.models import (
    TestRunRequest, 
    TestFilePath, 
    TestEnvironment,
    upload_dirs,
)


class TestRunRequestSerializer(serializers.ModelSerializer):
    env_name = serializers.ReadOnlyField(source='env.name')

    class Meta:
        model = TestRunRequest
        fields = (
            'id',
            'requested_by',
            'env',
            'path',
            'status',
            'created_at',
            'env_name'
        )
        read_only_fields = (
            'id',
            'created_at',
            'status',
            'logs',
            'env_name'
        )


class TestRunRequestItemSerializer(serializers.ModelSerializer):
    env_name = serializers.ReadOnlyField(source='env.name')

    class Meta:
        model = TestRunRequest
        fields = (
            'id',
            'requested_by',
            'env',
            'path',
            'status',
            'created_at',
            'env_name',
            'logs'
        )


class TestFilePathSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestFilePath
        fields = ('id', 'path')


class TestFilePathUploadSerializer(serializers.Serializer):
    test_file = serializers.FileField(max_length=1024, allow_empty_file=True)
    upload_dir = serializers.ChoiceField(upload_dirs)

    class Meta:
        fields = ('test_file', 'upload_dir')

    def save(self):
        directory = self.validated_data['upload_dir']
        file = self.validated_data['test_file']

        path = os.path.join(directory, file.name)

        with open(os.path.join(settings.BASE_DIR, path), 'wb+') as f:
            for chunk in file.chunks():
                f.write(chunk)

        (obj, _) = TestFilePath.objects.get_or_create(path=path)
        return obj


class TestEnvironmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestEnvironment
        fields = ('id', 'name')
