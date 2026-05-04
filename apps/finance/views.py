import datetime

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .selectors import AccountSelector, MonthlyExpenseSelector, TransactionSelector
from .serializers import (
    AccountSerializer,
    MonthlyExpenseSerializer,
    TransactionCreateSerializer,
    TransactionSerializer,
)
from .services import AccountService, FinanceSummaryService, TransactionService, UserProfileService


class UserSummaryView(APIView):
    def get(self, request, profile_id):
        profile = UserProfileService.get_by_id(profile_id)
        user = profile.user
        today = datetime.date.today()
        return Response({
            "user": {"name": user.get_full_name(), "email": user.email},
            "accounts": AccountSerializer(AccountSelector.get_user_accounts(user), many=True).data,
            "monthly_expenses": MonthlyExpenseSerializer(
                MonthlyExpenseSelector.get_user_active_expenses(user), many=True
            ).data,
            "monthly_summary": FinanceSummaryService.get_monthly_summary(user, today.year, today.month),
        })


class UserAccountListView(APIView):
    def get(self, request, profile_id):
        profile = UserProfileService.get_by_id(profile_id)
        accounts = AccountSelector.get_user_accounts(profile.user)
        return Response(AccountSerializer(accounts, many=True).data)


class UserTransactionListView(APIView):
    def get(self, request, profile_id):
        profile = UserProfileService.get_by_id(profile_id)
        transactions = TransactionSelector.get_user_transactions(profile.user)
        return Response(TransactionSerializer(transactions, many=True).data)

    def post(self, request, profile_id):
        profile = UserProfileService.get_by_id(profile_id)
        serializer = TransactionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        transaction = TransactionService.create(
            user=profile.user,
            account_id=data["account_id"],
            type=data["type"],
            amount=data["amount"],
            category=data.get("category", ""),
            description=data.get("description", ""),
            date=data["date"],
            created_via=data.get("created_via", "admin"),
        )
        return Response(TransactionSerializer(transaction).data, status=status.HTTP_201_CREATED)
