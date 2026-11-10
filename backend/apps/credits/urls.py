from django.urls import path

from apps.credits.views import CreditExportView, CreditListView, CreditSummaryView

urlpatterns = [
    path("credits", CreditListView.as_view()),
    path("credits/", CreditListView.as_view()),
    path("credits/transactions", CreditListView.as_view()),
    path("credits/transactions/", CreditListView.as_view()),
    path("credits/summary", CreditSummaryView.as_view()),
    path("credits/summary/", CreditSummaryView.as_view()),
    path("credits/export", CreditExportView.as_view()),
    path("credits/export/", CreditExportView.as_view()),
]
