from api.models import TestFilePath, TestEnvironment, upload_dirs
from api.serializers import TestFilePathSerializer, TestEnvironmentSerializer


def get_assets():
    return {
        'available_paths': TestFilePathSerializer(TestFilePath.objects.all().order_by('path'), many=True).data,
        'test_envs': TestEnvironmentSerializer(TestEnvironment.objects.all().order_by('name'), many=True).data,
        'upload_dirs': upload_dirs
    }
