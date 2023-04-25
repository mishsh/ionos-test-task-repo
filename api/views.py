from django.forms.models import model_to_dict

from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveAPIView, CreateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import FormParser, MultiPartParser

from api.models import TestRunRequest
from api.serializers import TestFilePathUploadSerializer, TestRunRequestSerializer, TestRunRequestItemSerializer
from api.tasks import execute_test_run_request
from api.usecases import get_assets


class TestRunRequestAPIView(ListCreateAPIView):
    serializer_class = TestRunRequestSerializer
    queryset = TestRunRequest.objects.all().order_by('-created_at')

    def perform_create(self, serializer):
        instance = serializer.save()
        execute_test_run_request.delay(instance.id)


class TestRunRequestItemAPIView(RetrieveAPIView):
    serializer_class = TestRunRequestItemSerializer
    queryset = TestRunRequest.objects.all()
    lookup_field = 'pk'


class AssetsAPIView(APIView):

    def get(self, request):
        return Response(status=status.HTTP_200_OK, data=get_assets())


class CreateTestFilePathAPIView(APIView):
    parser_classes = [FormParser, MultiPartParser]

    def post(self, request, format=None):
        serializer = TestFilePathUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        test_file_path = serializer.save()
        return Response(model_to_dict(test_file_path), status=status.HTTP_201_CREATED)