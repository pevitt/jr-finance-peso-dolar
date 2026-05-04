from typing import List, Optional
from uuid import UUID

from django.contrib.auth.models import User

from utils.selectors.base_selector import BaseSelector

from .models import Account, MonthlyExpense, Transaction, UserProfile


class UserProfileSelector(BaseSelector):
    model = UserProfile

    @classmethod
    def get_by_user(cls, user: User) -> Optional[UserProfile]:
        return UserProfile.objects.filter(user=user).first()

    @classmethod
    def get_by_telegram_chat_id(cls, chat_id: str) -> Optional[UserProfile]:
        return UserProfile.objects.filter(telegram_chat_id=str(chat_id)).select_related("user").first()


class AccountSelector(BaseSelector):
    model = Account

    @classmethod
    def get_user_accounts(cls, user: User) -> List[Account]:
        return Account.objects.filter(user=user)

    @classmethod
    def get_user_account_by_id(cls, user: User, account_id: UUID) -> Optional[Account]:
        return Account.objects.filter(user=user, id=account_id).first()


class MonthlyExpenseSelector(BaseSelector):
    model = MonthlyExpense

    @classmethod
    def get_user_active_expenses(cls, user: User) -> List[MonthlyExpense]:
        return MonthlyExpense.objects.filter(user=user, is_active=True).select_related("account")


class TransactionSelector(BaseSelector):
    model = Transaction

    @classmethod
    def get_user_transactions(cls, user: User, **filters) -> List[Transaction]:
        return Transaction.objects.filter(user=user, **filters).select_related("account")

    @classmethod
    def get_monthly_transactions(cls, user: User, year: int, month: int) -> List[Transaction]:
        return Transaction.objects.filter(
            user=user, date__year=year, date__month=month
        ).select_related("account")
