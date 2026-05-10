from rest_framework import serializers

from .models import Account, MonthlyExpense, Transaction, UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)
    full_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = UserProfile
        fields = ["id", "email", "full_name", "phone_number", "telegram_chat_id", "created_at"]
        read_only_fields = ["id", "created_at"]


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ["id", "name", "balance", "currency", "description", "created_at"]
        read_only_fields = ["id", "balance", "created_at"]


class MonthlyExpenseSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)
    currency = serializers.CharField(source="account.currency", read_only=True)

    class Meta:
        model = MonthlyExpense
        fields = ["id", "account", "account_name", "category", "amount", "currency", "description", "is_active", "created_at"]
        read_only_fields = ["id", "created_at", "account_name", "currency"]


class TransactionSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id", "account", "account_name", "type", "amount", "currency",
            "category", "description", "date", "created_via", "created_at",
        ]
        read_only_fields = ["id", "created_at", "account_name"]


class TransactionCreateSerializer(serializers.Serializer):
    account_id = serializers.UUIDField()
    type = serializers.ChoiceField(choices=["income", "expense"])
    amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    category = serializers.CharField(max_length=100, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    date = serializers.DateField()
    created_via = serializers.ChoiceField(choices=["admin", "telegram", "claude"], required=False, default="admin")
