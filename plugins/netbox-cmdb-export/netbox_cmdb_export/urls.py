from django.urls import path

from . import views

urlpatterns = [
    path("", views.ExportHomeView.as_view(), name="home"),
    path("cmdb.<str:fmt>", views.ExportFileView.as_view(), name="file"),
]
