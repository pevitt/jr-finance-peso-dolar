import functools
import logging
from decimal import Decimal, InvalidOperation

from asgiref.sync import sync_to_async
from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from apps.finance.exceptions import FinanceException
from utils.channels.telegram.db import (
    create_transaction,
    get_monthly_summary,
    get_profile_by_chat_id,
    get_user_accounts,
    update_exchange_rate,
)
from utils.channels.telegram.keyboards import (
    accounts_keyboard,
    cancel_keyboard,
    categories_keyboard,
    main_menu_keyboard,
    skip_cancel_keyboard,
)

logger = logging.getLogger(__name__)

MAIN_MENU, AMOUNT, ACCOUNT, CATEGORY, CATEGORY_CUSTOM, DESCRIPTION, UPDATE_RATE = range(7)

INCOME_CATEGORIES = ["Salario", "Freelance", "Inversión", "Dividendos", "Bono"]
EXPENSE_CATEGORIES = ["Arriendo", "Mercado", "Transporte", "Servicios", "Salud", "Entretenimiento", "Suscripciones"]

MONTH_NAMES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


# ── Auth ──────────────────────────────────────────────────────────────────────

def require_auth(handler):
    """Verifica que el chat_id esté registrado en un UserProfile antes de ejecutar el handler."""
    @functools.wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        profile = await sync_to_async(get_profile_by_chat_id)(str(update.effective_user.id))
        if not profile:
            msg = "⛔ No estás autorizado para usar este bot."
            if update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.edit_message_text(msg)
            else:
                await update.effective_message.reply_text(msg)
            return ConversationHandler.END
        context.user_data["profile"] = profile
        return await handler(update, context)
    return wrapper


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_cop(val: Decimal) -> str:
    return f"${val:,.0f} COP"

def _fmt_usd(val: Decimal) -> str:
    return f"${val:,.2f} USD"

def _fmt(val: Decimal, currency: str) -> str:
    return _fmt_cop(val) if currency == "COP" else _fmt_usd(val)


# ── Entry point ───────────────────────────────────────────────────────────────

@require_auth
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    profile = context.user_data["profile"]
    name = profile.user.first_name or profile.user.email
    await update.effective_message.reply_text(
        f"¡Hola, {name}! 💰 ¿Qué querés hacer?",
        reply_markup=main_menu_keyboard(),
    )
    return MAIN_MENU


# ── Main menu handlers ────────────────────────────────────────────────────────

async def handle_add_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["type"] = "income"
    await query.edit_message_text(
        "💰 *Agregar ingreso*\n\n¿Cuánto ingresó? Escribí el monto:",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AMOUNT


async def handle_add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["type"] = "expense"
    await query.edit_message_text(
        "💸 *Agregar egreso*\n\n¿Cuánto salió? Escribí el monto:",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return AMOUNT


@require_auth
async def handle_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    profile = context.user_data["profile"]
    accounts = await sync_to_async(get_user_accounts)(profile.user)
    rate = profile.usd_to_cop_rate

    if not accounts:
        await query.edit_message_text("📊 No tenés cuentas registradas.", reply_markup=main_menu_keyboard())
        return MAIN_MENU

    total_cop = Decimal("0")
    total_usd = Decimal("0")
    lines = [f"📊 *Tu balance actual:*\n_(1 USD = {_fmt_cop(rate)})_\n"]

    for acc in accounts:
        if acc.currency == "COP":
            equiv = acc.balance / rate
            lines.append(f"• *{acc.name}*: {_fmt_cop(acc.balance)} _(~{_fmt_usd(equiv)})_")
            total_cop += acc.balance
            total_usd += equiv
        else:
            equiv = acc.balance * rate
            lines.append(f"• *{acc.name}*: {_fmt_usd(acc.balance)} _(~{_fmt_cop(equiv)})_")
            total_usd += acc.balance
            total_cop += equiv

    lines.append(f"\n*Total: ~{_fmt_cop(total_cop)} | ~{_fmt_usd(total_usd)}*")

    await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=main_menu_keyboard())
    return MAIN_MENU


@require_auth
async def handle_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    profile = context.user_data["profile"]
    summary = await sync_to_async(get_monthly_summary)(profile.user)
    rate = profile.usd_to_cop_rate

    month_name = MONTH_NAMES[summary["month"]]
    lines = [f"📅 *Resumen {month_name} {summary['year']}:*\n_(1 USD = {_fmt_cop(rate)})_\n"]

    for currency in ("COP", "USD"):
        income = summary["income"][currency]
        fixed = summary["fixed_expenses"][currency]
        expenses = summary["expenses"][currency]
        target = summary["savings_target"][currency]
        savings = summary["actual_savings"][currency]

        if income == 0 and fixed == 0:
            continue

        icon = "✅" if savings >= target else "⚠️"
        pct = f"{(savings / income * 100):.0f}%" if income else "—"
        lines.append(f"*── {currency} ──*")
        lines.append(f"📥 Ingresos: {_fmt(income, currency)}")
        lines.append(f"📌 Gastos fijos: {_fmt(fixed, currency)}")
        lines.append(f"📤 Egresos totales: {_fmt(expenses, currency)}")
        lines.append(f"{icon} Ahorro: {_fmt(savings, currency)} ({pct}) — mínimo {_fmt(target, currency)}\n")

    # Totales consolidados
    total_savings_cop = summary["actual_savings"]["COP"] + summary["actual_savings"]["USD"] * rate
    total_income_cop = summary["income"]["COP"] + summary["income"]["USD"] * rate
    if total_income_cop > 0:
        total_pct = f"{(total_savings_cop / total_income_cop * 100):.0f}%"
        icon = "✅" if total_savings_cop >= total_income_cop * Decimal("0.35") else "⚠️"
        lines.append(f"*── Total consolidado ──*")
        lines.append(f"{icon} Ahorro total: ~{_fmt_cop(total_savings_cop)} ({total_pct})")

    await query.edit_message_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=main_menu_keyboard()
    )
    return MAIN_MENU


# ── Update rate flow ──────────────────────────────────────────────────────────

@require_auth
async def handle_update_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    profile = context.user_data["profile"]
    await query.edit_message_text(
        f"💱 *Actualizar tasa USD/COP*\n\nTasa actual: *{_fmt_cop(profile.usd_to_cop_rate)}*\n\nEscribí la nueva tasa (ej: 4250):",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return UPDATE_RATE


async def handle_rate_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().replace(",", ".").replace(" ", "")
    try:
        rate = Decimal(text)
        if rate <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await update.message.reply_text(
            "❌ Tasa inválida. Ingresá un número positivo (ej: 4250):",
            reply_markup=cancel_keyboard(),
        )
        return UPDATE_RATE

    profile = context.user_data["profile"]
    try:
        await sync_to_async(update_exchange_rate)(profile, rate)
        profile.usd_to_cop_rate = rate
        text = f"✅ Tasa actualizada: *1 USD = {_fmt_cop(rate)}*\n\n¿Qué más querés hacer?"
    except Exception:
        logger.exception("Error al actualizar tasa")
        text = "❌ Error al actualizar la tasa. Intentá de nuevo."

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())
    return MAIN_MENU


# ── Transaction flow ──────────────────────────────────────────────────────────

@require_auth
async def handle_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().replace(",", ".").replace(" ", "")
    try:
        amount = Decimal(text)
        if amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await update.message.reply_text(
            "❌ Monto inválido. Ingresá un número positivo (ej: 50000):",
            reply_markup=cancel_keyboard(),
        )
        return AMOUNT

    context.user_data["amount"] = amount
    profile = context.user_data["profile"]
    accounts = await sync_to_async(get_user_accounts)(profile.user)

    if not accounts:
        await update.message.reply_text(
            "⚠️ No tenés cuentas registradas. Creá una desde el admin.",
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU

    await update.message.reply_text("🏦 ¿En qué cuenta?", reply_markup=accounts_keyboard(accounts))
    return ACCOUNT


async def handle_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    account_id = query.data.split(":")[1]
    accounts = await sync_to_async(get_user_accounts)(context.user_data["profile"].user)
    account = next((a for a in accounts if str(a.id) == account_id), None)

    if not account:
        await query.edit_message_text("❌ Cuenta no encontrada.", reply_markup=main_menu_keyboard())
        return MAIN_MENU

    context.user_data["account"] = account
    cats = INCOME_CATEGORIES if context.user_data["type"] == "income" else EXPENSE_CATEGORIES
    await query.edit_message_text("🏷️ ¿Categoría?", reply_markup=categories_keyboard(cats))
    return CATEGORY


async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cat:custom":
        await query.edit_message_text("✏️ Escribí la categoría:")
        return CATEGORY_CUSTOM

    context.user_data["category"] = query.data.split(":", 1)[1]
    await query.edit_message_text("📝 ¿Descripción? (opcional)", reply_markup=skip_cancel_keyboard())
    return DESCRIPTION


async def handle_category_custom(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["category"] = update.message.text.strip()
    await update.message.reply_text("📝 ¿Descripción? (opcional)", reply_markup=skip_cancel_keyboard())
    return DESCRIPTION


async def handle_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["description"] = update.message.text.strip()
    return await _save_transaction(update, context, is_callback=False)


async def handle_skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["description"] = ""
    return await _save_transaction(update, context, is_callback=True)


async def _save_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE, is_callback: bool) -> int:
    data = context.user_data
    profile = data["profile"]
    account = data["account"]

    try:
        await sync_to_async(create_transaction)(
            user=profile.user,
            account_id=account.id,
            transaction_type=data["type"],
            amount=data["amount"],
            category=data["category"],
            description=data.get("description", ""),
        )
        currency = account.currency
        amount_str = f"{data['amount']:,.0f}" if currency == "COP" else f"{data['amount']:,.2f}"
        symbol = "+" if data["type"] == "income" else "-"
        text = (
            f"✅ *Registrado*\n\n"
            f"{symbol}${amount_str} {currency}\n"
            f"🏦 {account.name}  •  🏷️ {data['category']}\n\n"
            f"¿Qué más querés hacer?"
        )
    except FinanceException as e:
        text = f"❌ {e.detail['message']}"
    except Exception:
        logger.exception("Error inesperado al guardar transacción")
        text = "❌ Error inesperado. Intentá de nuevo."

    context.user_data.clear()

    if is_callback:
        await update.callback_query.edit_message_text(
            text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            text, parse_mode="Markdown", reply_markup=main_menu_keyboard()
        )
    return MAIN_MENU


# ── Cancel ────────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text("Cancelado. ¿Qué querés hacer?", reply_markup=main_menu_keyboard())
    return MAIN_MENU


# ── Build handler ─────────────────────────────────────────────────────────────

def build_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("menu", start),
        ],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(handle_add_income, pattern="^add_income$"),
                CallbackQueryHandler(handle_add_expense, pattern="^add_expense$"),
                CallbackQueryHandler(handle_balance, pattern="^balance$"),
                CallbackQueryHandler(handle_summary, pattern="^summary$"),
                CallbackQueryHandler(handle_update_rate, pattern="^update_rate$"),
            ],
            AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_amount),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            ACCOUNT: [
                CallbackQueryHandler(handle_account, pattern="^account:"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            CATEGORY: [
                CallbackQueryHandler(handle_category, pattern="^cat:"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            CATEGORY_CUSTOM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category_custom),
            ],
            DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_description),
                CallbackQueryHandler(handle_skip_description, pattern="^skip$"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            UPDATE_RATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rate_input),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("menu", start),
        ],
        per_message=False,
    )
