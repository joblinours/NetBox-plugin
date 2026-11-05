from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("sources/", views.SourceReportView.as_view(), name="sources"),
]
