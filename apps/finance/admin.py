from decimal import Decimal

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import Account, MonthlyExpense, Transaction, UserProfile


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_all_users_balance_summary():
    rows = []
    for profile in UserProfile.objects.select_related("user").all():
        try:
            rate = profile.usd_to_cop_rate
            total_cop = Decimal("0")
            total_usd = Decimal("0")
            for acc in Account.objects.filter(user=profile.user):
                if acc.currency == "COP":
                    total_cop += acc.balance
                    total_usd += acc.balance / rate
                else:
                    total_usd += acc.balance
                    total_cop += acc.balance * rate
            rows.append({
                "user_id": profile.user.pk,
                "display_name": profile.user.get_full_name() or profile.user.username,
                "total_cop": f"{total_cop:,.0f}",
                "total_usd": f"{total_usd:,.2f}",
                "rate": f"{rate:,.0f}",
            })
        except Exception:
            continue
    return rows or None


# ── Model Admins ──────────────────────────────────────────────────────────────

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Perfil"
    fields = ["phone_number", "telegram_chat_id", "usd_to_cop_rate"]


class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "balance", "currency", "created_at"]
    list_filter = ["currency", "user"]
    search_fields = ["name", "user__email", "user__first_name", "user__last_name"]

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        try:
            user_id = request.GET.get("user__id__exact")
            target_user = User.objects.get(pk=user_id) if user_id else request.user
            profile = target_user.profile
            rate = profile.usd_to_cop_rate
            total_cop = Decimal("0")
            total_usd = Decimal("0")
            for acc in Account.objects.filter(user=target_user):
                if acc.currency == "COP":
                    total_cop += acc.balance
                    total_usd += acc.balance / rate
                else:
                    total_usd += acc.balance
                    total_cop += acc.balance * rate
            extra_context["account_totals"] = {
                "display_name": target_user.get_full_name() or target_user.username,
                "total_cop": f"{total_cop:,.0f}",
                "total_usd": f"{total_usd:,.2f}",
                "rate": f"{rate:,.0f}",
            }
        except Exception:
            pass
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(MonthlyExpense)
class MonthlyExpenseAdmin(admin.ModelAdmin):
    list_display = ["category", "account", "amount", "account_currency", "is_active"]
    list_filter = ["is_active", "account__currency", "user"]
    search_fields = ["category", "description"]

    @admin.display(description="Moneda")
    def account_currency(self, obj):
        return obj.account.currency


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["date", "account", "type", "amount", "currency", "category", "created_via"]
    list_filter = ["type", "currency", "created_via", "account"]
    search_fields = ["category", "description"]
    date_hierarchy = "date"
