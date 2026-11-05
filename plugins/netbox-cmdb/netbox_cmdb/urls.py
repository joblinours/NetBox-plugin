from django.urls import path

from . import views

urlpatterns = [
    path("sources/", views.SourceStatusListView.as_view(), name="sourcestatus_list"),
]
