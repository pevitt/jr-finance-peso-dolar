from django.contrib.auth.models import User
from django.db import models

from utils.models.base_model import BaseModelUUID


class Currency(models.TextChoices):
    COP = "COP", "Peso Colombiano"
    USD = "USD", "Dólar"


class TransactionType(models.TextChoices):
    INCOME = "income", "Ingreso"
    EXPENSE = "expense", "Egreso"
    TRANSFER = "transfer", "Transferencia"


class CreatedVia(models.TextChoices):
    ADMIN = "admin", "Admin"
    TELEGRAM = "telegram", "Telegram"
    CLAUDE = "claude", "Claude"


class UserProfile(BaseModelUUID):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    phone_number = models.CharField(max_length=20, blank=True)
    telegram_chat_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    usd_to_cop_rate = models.DecimalField(max_digits=10, decimal_places=2, default=4200)

    class Meta:
        verbose_name = "Perfil"
        verbose_name_plural = "Perfiles"

    def __str__(self):
        return f"Perfil de {self.user.get_full_name() or self.user.email}"


class Account(BaseModelUUID):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="accounts")
    name = models.CharField(max_length=100)
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.COP)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "Cuenta"
        verbose_name_plural = "Cuentas"

    def __str__(self):
        return f"{self.name} ({self.currency})"


class MonthlyExpense(BaseModelUUID):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="monthly_expenses")
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="monthly_expenses")
    category = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Gasto Mensual Fijo"
        verbose_name_plural = "Gastos Mensuales Fijos"

    def __str__(self):
        return f"{self.category}: {self.amount} {self.account.currency} → {self.account.name}"


class Transaction(BaseModelUUID):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="transactions")
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="transactions")
    type = models.CharField(max_length=20, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.COP)
    category = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    date = models.DateField()
    created_via = models.CharField(max_length=20, choices=CreatedVia.choices, default=CreatedVia.ADMIN)

    class Meta:
        verbose_name = "Transacción"
        verbose_name_plural = "Transacciones"
        ordering = ["-date", "-created_at"]

    def __str__(self):
        symbol = "+" if self.type == TransactionType.INCOME else "-"
        return f"{symbol}{self.amount} {self.currency} — {self.category or self.type} ({self.date})"
