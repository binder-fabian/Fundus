from django.urls import path

from fundus.loans import views

urlpatterns = [
    path("scannen/", views.scanner, name="scanner"),
    path("s/", views.scan, name="scan_lookup"),
    path("s/<str:number>", views.scan, name="scan"),
    path("exemplar/<int:pk>/ausleihen/", views.lend, name="lend"),
    path("exemplar/<int:pk>/zurueckgeben/", views.give_back, name="give_back"),
    path("ausleihe/<int:pk>/verlaengern/", views.extend, name="extend"),
    path("katalog/<int:pk>/anfragen/", views.request_create, name="request_create"),
    path("anfrage/<int:pk>/genehmigen/", views.request_approve, name="request_approve"),
    path("anfrage/<int:pk>/ablehnen/", views.request_reject, name="request_reject"),
    path("anfrage/<int:pk>/zurueckziehen/", views.request_withdraw, name="request_withdraw"),
    path("anfrage/<int:pk>/uebergeben/<int:copy_pk>/", views.hand_over, name="request_hand_over"),
    path("ausleihen/", views.overview, name="loan_overview"),
    path("ausleihen/rueckgabekiste/", views.return_box, name="return_box"),
]
