from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
# Create your views here.

@api_view(['POST'])
def login(request):
    return Response({})


@api_view(['POST'])
def signup(request):
    return Response({})


@api_view(['GET'])
def test_token(request):
    return Response({})

