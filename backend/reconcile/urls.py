from django.urls import path
from .views import disagreements_list, orgs_list

urlpatterns = [
    path("disagreements/", disagreements_list, name="disagreements-list"),
    path("orgs/", orgs_list, name="orgs-list"),
]
