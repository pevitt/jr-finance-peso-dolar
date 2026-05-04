from django.urls import path

from .views import UserAccountListView, UserSummaryView, UserTransactionListView

urlpatterns = [
    path("profiles/<uuid:profile_id>/summary/", UserSummaryView.as_view(), name="user-summary"),
    path("profiles/<uuid:profile_id>/accounts/", UserAccountListView.as_view(), name="user-accounts"),
    path("profiles/<uuid:profile_id>/transactions/", UserTransactionListView.as_view(), name="user-transactions"),
]
