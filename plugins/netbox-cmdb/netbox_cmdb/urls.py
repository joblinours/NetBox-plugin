from django.urls import path

from . import views

urlpatterns = [
    path("sources/", views.SourceStatusListView.as_view(), name="sourcestatus_list"),
    path("sources/run-syncs/", views.RunSyncsView.as_view(), name="run_syncs"),
    path("sources/<int:pk>/forget/", views.ForgetSourceView.as_view(), name="forget_source"),
]
