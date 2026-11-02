from django.urls import path

from fundus.loans import views

urlpatterns = [
    path("scannen/", views.scanner, name="scanner"),
    path("s/", views.scan, name="scan_lookup"),
    path("s/<str:number>", views.scan, name="scan"),
    path("exemplar/<int:pk>/ausleihen/", views.lend, name="lend"),
    path("exemplar/<int:pk>/zurueckgeben/", views.give_back, name="give_back"),
    path("ausleihe/<int:pk>/verlaengern/", views.extend, name="extend"),
    path("ausleihen/", views.overview, name="loan_overview"),
    path("ausleihen/rueckgabekiste/", views.return_box, name="return_box"),
]
