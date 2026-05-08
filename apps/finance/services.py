import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from django.contrib.auth.models import User
from django.db import models

from utils.services.base_service import BaseService

from .exceptions import FinanceErrorCode, FinanceException
from .models import Account, MonthlyExpense, Transaction, TransactionType, UserProfile
from .selectors import AccountSelector, MonthlyExpenseSelector, TransactionSelector, UserProfileSelector

_ZERO = Decimal("0")


class UserProfileService(BaseService):

    @classmethod
    def create(cls, **kwargs) -> UserProfile:
        return UserProfileSelector.create(**kwargs)

    @classmethod
    def update(cls, instance: UserProfile, **kwargs) -> UserProfile:
        return UserProfileSelector.update(instance, **kwargs)

    @classmethod
    def delete(cls, instance: UserProfile) -> bool:
        return UserProfileSelector.delete(instance)

    @classmethod
    def get_by_id(cls, id: Any) -> UserProfile:
        profile = UserProfileSelector.get_by_id(id)
        if not profile:
            raise FinanceException(FinanceErrorCode.F01)
        return profile

    @classmethod
    def get_all(cls) -> List[UserProfile]:
        return UserProfileSelector.get_all()

    @classmethod
    def get_by_filters(cls, **filters) -> List[UserProfile]:
        return UserProfileSelector.filter(**filters)

    @classmethod
    def get_by_telegram_chat_id(cls, chat_id: str) -> UserProfile:
        profile = UserProfileSelector.get_by_telegram_chat_id(chat_id)
        if not profile:
            raise FinanceException(FinanceErrorCode.F01)
        return profile


class AccountService(BaseService):

    @classmethod
    def create(cls, user: User, **kwargs) -> Account:
        return AccountSelector.create(user=user, **kwargs)

    @classmethod
    def update(cls, instance: Account, **kwargs) -> Account:
        return AccountSelector.update(instance, **kwargs)

    @classmethod
    def delete(cls, instance: Account) -> bool:
        return AccountSelector.delete(instance)

    @classmethod
    def get_by_id(cls, id: Any) -> Account:
        account = AccountSelector.get_by_id(id)
        if not account:
            raise FinanceException(FinanceErrorCode.F02)
        return account

    @classmethod
    def get_all(cls) -> List[Account]:
        return AccountSelector.get_all()

    @classmethod
    def get_by_filters(cls, **filters) -> List[Account]:
        return AccountSelector.filter(**filters)

    @classmethod
    def get_user_account(cls, user: User, account_id: UUID) -> Account:
        account = AccountSelector.get_user_account_by_id(user, account_id)
        if not account:
            raise FinanceException(FinanceErrorCode.F05)
        return account


class TransactionService(BaseService):

    @classmethod
    def create(cls, user: User, account_id: UUID, **kwargs) -> Transaction:
        account = AccountService.get_user_account(user, account_id)
        kwargs.setdefault("currency", account.currency)
        transaction = TransactionSelector.create(user=user, account=account, **kwargs)
        if transaction.type == "income":
            account.balance += transaction.amount
        else:
            account.balance -= transaction.amount
        account.save()
        return transaction

    @classmethod
    def update(cls, instance: Transaction, **kwargs) -> Transaction:
        return TransactionSelector.update(instance, **kwargs)

    @classmethod
    def delete(cls, instance: Transaction) -> bool:
        return TransactionSelector.delete(instance)

    @classmethod
    def get_by_id(cls, id: Any) -> Transaction:
        transaction = TransactionSelector.get_by_id(id)
        if not transaction:
            raise FinanceException(FinanceErrorCode.F03)
        return transaction

    @classmethod
    def get_all(cls) -> List[Transaction]:
        return TransactionSelector.get_all()

    @classmethod
    def get_by_filters(cls, **filters) -> List[Transaction]:
        return TransactionSelector.filter(**filters)

    @classmethod
    def create_transfer(cls, user: User, from_account_id: UUID, to_account_id: UUID, amount: Decimal, rate: Decimal) -> Decimal:
        from_account = AccountService.get_user_account(user, from_account_id)
        to_account = AccountService.get_user_account(user, to_account_id)

        if from_account.currency == to_account.currency:
            converted_amount = amount
        elif from_account.currency == "COP" and to_account.currency == "USD":
            converted_amount = (amount / rate).quantize(Decimal("0.01"))
        else:
            converted_amount = (amount * rate).quantize(Decimal("0.01"))

        today = datetime.date.today()

        TransactionSelector.create(
            user=user, account=from_account,
            type=TransactionType.TRANSFER, amount=amount,
            currency=from_account.currency, category="Transferencia",
            description=f"→ {to_account.name}", date=today, created_via="telegram",
        )
        from_account.balance -= amount
        from_account.save()

        TransactionSelector.create(
            user=user, account=to_account,
            type=TransactionType.TRANSFER, amount=converted_amount,
            currency=to_account.currency, category="Transferencia",
            description=f"← {from_account.name}", date=today, created_via="telegram",
        )
        to_account.balance += converted_amount
        to_account.save()

        return converted_amount


class MonthlyExpenseService(BaseService):

    @classmethod
    def create(cls, user: User, **kwargs) -> MonthlyExpense:
        return MonthlyExpenseSelector.create(user=user, **kwargs)

    @classmethod
    def update(cls, instance: MonthlyExpense, **kwargs) -> MonthlyExpense:
        return MonthlyExpenseSelector.update(instance, **kwargs)

    @classmethod
    def delete(cls, instance: MonthlyExpense) -> bool:
        return MonthlyExpenseSelector.delete(instance)

    @classmethod
    def get_by_id(cls, id: Any) -> MonthlyExpense:
        expense = MonthlyExpenseSelector.get_by_id(id)
        if not expense:
            raise FinanceException(FinanceErrorCode.F04)
        return expense

    @classmethod
    def get_all(cls) -> List[MonthlyExpense]:
        return MonthlyExpenseSelector.get_all()

    @classmethod
    def get_by_filters(cls, **filters) -> List[MonthlyExpense]:
        return MonthlyExpenseSelector.filter(**filters)


class FinanceSummaryService:
    SAVINGS_TARGET = Decimal("0.35")

    @classmethod
    def get_monthly_summary(cls, user: User, year: int, month: int) -> Dict:
        transactions = [
            t for t in TransactionSelector.get_monthly_transactions(user, year, month)
            if t.type != TransactionType.TRANSFER
        ]
        fixed_expenses = list(MonthlyExpenseSelector.get_user_active_expenses(user))

        income_cop = sum((t.amount for t in transactions if t.type == "income" and t.currency == "COP"), _ZERO)
        income_usd = sum((t.amount for t in transactions if t.type == "income" and t.currency == "USD"), _ZERO)
        expense_cop = sum((t.amount for t in transactions if t.type == "expense" and t.currency == "COP"), _ZERO)
        expense_usd = sum((t.amount for t in transactions if t.type == "expense" and t.currency == "USD"), _ZERO)

        fixed_cop = sum((e.amount for e in fixed_expenses if e.account.currency == "COP"), _ZERO)
        fixed_usd = sum((e.amount for e in fixed_expenses if e.account.currency == "USD"), _ZERO)

        return {
            "year": year,
            "month": month,
            "income": {"COP": income_cop, "USD": income_usd},
            "expenses": {"COP": expense_cop, "USD": expense_usd},
            "fixed_expenses": {"COP": fixed_cop, "USD": fixed_usd},
            "savings_target": {
                "COP": income_cop * cls.SAVINGS_TARGET,
                "USD": income_usd * cls.SAVINGS_TARGET,
            },
            "actual_savings": {
                "COP": income_cop - expense_cop,
                "USD": income_usd - expense_usd,
            },
        }
