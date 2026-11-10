from django.urls import path

from apps.checkin.views import CheckinJobDetailView, CheckinJobView, CheckinRecordView, CheckinSummaryView

urlpatterns = [
    path("checkin/records", CheckinRecordView.as_view()),
    path("checkin/records/", CheckinRecordView.as_view()),
    path("checkins", CheckinRecordView.as_view()),
    path("checkin/jobs", CheckinJobView.as_view()),
    path("checkin/jobs/", CheckinJobView.as_view()),
    path("checkin/jobs/<str:job_id>", CheckinJobDetailView.as_view()),
    path("checkin/jobs/<str:job_id>/", CheckinJobDetailView.as_view()),
    path("checkin/summary", CheckinSummaryView.as_view()),
    path("checkin/summary/", CheckinSummaryView.as_view()),
]
