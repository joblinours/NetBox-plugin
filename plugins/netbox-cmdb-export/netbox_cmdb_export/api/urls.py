from django.urls import path

from . import views

urlpatterns = [path("<str:fmt>/", views.ExportAPIView.as_view(), name="export")]
