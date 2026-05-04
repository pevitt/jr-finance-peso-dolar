"""Funciones síncronas de acceso a DB, envueltas con sync_to_async en los handlers."""
import datetime
from uuid import UUID

from django.contrib.auth.models import User

from apps.finance.models import Account, UserProfile
from apps.finance.services import FinanceSummaryService, TransactionService


def get_profile_by_chat_id(chat_id: str) -> UserProfile | None:
    return (
        UserProfile.objects.filter(telegram_chat_id=str(chat_id))
        .select_related("user")
        .first()
    )


def get_user_accounts(user: User) -> list[Account]:
    return list(Account.objects.filter(user=user))


def create_transaction(
    user: User,
    account_id: UUID,
    transaction_type: str,
    amount,
    category: str,
    description: str,
):
    return TransactionService.create(
        user=user,
        account_id=account_id,
        type=transaction_type,
        amount=amount,
        category=category,
        description=description,
        date=datetime.date.today(),
        created_via="telegram",
    )


def get_monthly_summary(user: User) -> dict:
    today = datetime.date.today()
    return FinanceSummaryService.get_monthly_summary(user, today.year, today.month)


def update_exchange_rate(profile, rate) -> None:
    profile.usd_to_cop_rate = rate
    profile.save(update_fields=["usd_to_cop_rate"])
