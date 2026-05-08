"""Funciones síncronas de acceso a DB, envueltas con sync_to_async en los handlers."""
import datetime
from uuid import UUID

from django.contrib.auth.models import User

from apps.finance.models import Account, UserProfile
from apps.finance.services import FinanceSummaryService, TransactionService
from decimal import Decimal
from uuid import UUID


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


def get_monthly_summary(user: User, year: int = None, month: int = None) -> dict:
    today = datetime.date.today()
    return FinanceSummaryService.get_monthly_summary(user, year or today.year, month or today.month)


def update_exchange_rate(profile, rate) -> None:
    profile.usd_to_cop_rate = rate
    profile.save(update_fields=["usd_to_cop_rate"])


def create_transfer(user, from_account_id: UUID, to_account_id: UUID, amount: Decimal, rate: Decimal) -> Decimal:
    return TransactionService.create_transfer(
        user=user,
        from_account_id=from_account_id,
        to_account_id=to_account_id,
        amount=amount,
        rate=rate,
    )
