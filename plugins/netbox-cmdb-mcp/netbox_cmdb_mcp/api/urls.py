from django.urls import path

from . import views

urlpatterns = [path("", views.MCPView.as_view(), name="mcp")]
