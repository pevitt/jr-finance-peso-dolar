from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.finance"

    def ready(self):
        from django.contrib.admin.sites import AdminSite
        from apps.finance.admin import _get_all_users_balance_summary

        _original_index = AdminSite.index

        def _patched_index(self, request, extra_context=None):
            extra_context = extra_context or {}
            extra_context["balance_summary"] = _get_all_users_balance_summary()
            return _original_index(self, request, extra_context)

        AdminSite.index = _patched_index
        AdminSite.index_template = "admin/finance_index.html"
        AdminSite.site_header = "💰 Control de Finanzas"
        AdminSite.site_title = "Finanzas"
        AdminSite.index_title = "Panel de Control"
