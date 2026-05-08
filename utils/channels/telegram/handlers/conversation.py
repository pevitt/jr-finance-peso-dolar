import asyncio
import datetime
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
    create_transfer,
    get_monthly_summary,
    get_profile_by_chat_id,
    get_user_accounts,
    update_exchange_rate,
)
from utils.channels.telegram.keyboards import (
    accounts_keyboard,
    cancel_keyboard,
    categories_keyboard,
    confirm_transfer_keyboard,
    main_menu_keyboard,
    skip_cancel_keyboard,
)

logger = logging.getLogger(__name__)

MAIN_MENU, AMOUNT, ACCOUNT, CATEGORY, CATEGORY_CUSTOM, DESCRIPTION, UPDATE_RATE, TRANSFER_AMOUNT, TRANSFER_FROM, TRANSFER_TO, TRANSFER_CONFIRM = range(11)

INCOME_CATEGORIES = ["Salario", "Freelance", "Inversión", "Dividendos", "Bono", "Transferencia", "Cobro préstamo"]
EXPENSE_CATEGORIES = ["Arriendo", "Mercado", "Transporte", "Servicios", "Salud", "Entretenimiento", "Suscripciones", "Transferencia", "Familia", "Préstamo"]

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


def _detailed_summary_lines(summary: dict, month_name: str, rate: Decimal) -> list[str]:
    lines = [f"\n*── {month_name} {summary['year']} ──*\n"]
    has_data = False
    for currency in ("COP", "USD"):
        income = summary["income"][currency]
        fixed = summary["fixed_expenses"][currency]
        expenses = summary["expenses"][currency]
        target = summary["savings_target"][currency]
        savings = summary["actual_savings"][currency]
        if income == 0 and fixed == 0:
            continue
        has_data = True
        icon = "✅" if savings >= target else "⚠️"
        pct = f"{(savings / income * 100):.0f}%" if income else "—"
        lines.append(f"*{currency}*")
        diff = fixed - expenses
        diff_icon = "✅" if diff >= 0 else "⚠️"
        diff_label = f"Restante: {_fmt(diff, currency)}" if diff >= 0 else f"Excedido: {_fmt(abs(diff), currency)}"
        lines.append(f"📥 Ingresos: {_fmt(income, currency)}")
        lines.append(f"📌 Gastos fijos: {_fmt(fixed, currency)}")
        lines.append(f"📤 Egresos totales: {_fmt(expenses, currency)}")
        lines.append(f"{diff_icon} {diff_label}")
        lines.append(f"{icon} Ahorro: {_fmt(savings, currency)} ({pct}) — mínimo {_fmt(target, currency)}\n")

    if not has_data:
        lines.append("Sin datos registrados.")
        return lines

    total_savings_cop = summary["actual_savings"]["COP"] + summary["actual_savings"]["USD"] * rate
    total_income_cop = summary["income"]["COP"] + summary["income"]["USD"] * rate
    if total_income_cop > 0:
        total_pct = f"{(total_savings_cop / total_income_cop * 100):.0f}%"
        icon = "✅" if total_savings_cop >= total_income_cop * Decimal("0.35") else "⚠️"
        lines.append(f"*Total consolidado*")
        lines.append(f"{icon} Ahorro: ~{_fmt_cop(total_savings_cop)} ({total_pct})")
    return lines


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
    rate = profile.usd_to_cop_rate

    accounts = await sync_to_async(get_user_accounts)(profile.user)

    if not accounts:
        await query.edit_message_text("📊 No tenés cuentas registradas.", reply_markup=main_menu_keyboard())
        return MAIN_MENU

    total_cop = Decimal("0")
    total_usd = Decimal("0")
    lines = [f"📊 *Balance actual*\n_(1 USD = {_fmt_cop(rate)})_\n"]

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
    rate = profile.usd_to_cop_rate

    today = datetime.date.today()
    prev_year, prev_month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)

    summary_cur, summary_prev = await asyncio.gather(
        sync_to_async(get_monthly_summary)(profile.user),
        sync_to_async(get_monthly_summary)(profile.user, prev_year, prev_month),
    )

    cur_month_name = MONTH_NAMES[summary_cur["month"]]
    prev_month_name = MONTH_NAMES[summary_prev["month"]]

    lines = [f"📅 *Resumen mensual*\n_(1 USD = {_fmt_cop(rate)})_"]
    lines.extend(_detailed_summary_lines(summary_cur, cur_month_name, rate))
    lines.extend(_detailed_summary_lines(summary_prev, prev_month_name, rate))

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


# ── Transfer flow ─────────────────────────────────────────────────────────────

@require_auth
async def handle_transfer_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    profile = context.user_data["profile"]
    accounts = await sync_to_async(get_user_accounts)(profile.user)
    if len(accounts) < 2:
        await query.edit_message_text(
            "⚠️ Necesitás al menos 2 cuentas para mover dinero.",
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU
    await query.edit_message_text(
        "🔄 *Mover dinero*\n\n¿Cuánto querés mover? Escribí el monto:",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return TRANSFER_AMOUNT


@require_auth
async def handle_transfer_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().replace(",", ".").replace(" ", "")
    try:
        amount = Decimal(text)
        if amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        await update.message.reply_text(
            "❌ Monto inválido. Ingresá un número positivo:",
            reply_markup=cancel_keyboard(),
        )
        return TRANSFER_AMOUNT

    context.user_data["transfer_amount"] = amount
    profile = context.user_data["profile"]
    accounts = await sync_to_async(get_user_accounts)(profile.user)
    await update.message.reply_text(
        "🏦 ¿De qué cuenta sale el dinero?",
        reply_markup=accounts_keyboard(accounts, prefix="tfrom"),
    )
    return TRANSFER_FROM


async def handle_transfer_from(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    account_id = query.data.split(":")[1]
    accounts = await sync_to_async(get_user_accounts)(context.user_data["profile"].user)
    from_account = next((a for a in accounts if str(a.id) == account_id), None)
    if not from_account:
        await query.edit_message_text("❌ Cuenta no encontrada.", reply_markup=main_menu_keyboard())
        return MAIN_MENU
    context.user_data["transfer_from"] = from_account
    other_accounts = [a for a in accounts if str(a.id) != account_id]
    await query.edit_message_text(
        "🏦 ¿A qué cuenta va el dinero?",
        reply_markup=accounts_keyboard(other_accounts, prefix="tto"),
    )
    return TRANSFER_TO


async def handle_transfer_to(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    account_id = query.data.split(":")[1]
    accounts = await sync_to_async(get_user_accounts)(context.user_data["profile"].user)
    to_account = next((a for a in accounts if str(a.id) == account_id), None)
    if not to_account:
        await query.edit_message_text("❌ Cuenta no encontrada.", reply_markup=main_menu_keyboard())
        return MAIN_MENU

    context.user_data["transfer_to"] = to_account
    from_account = context.user_data["transfer_from"]
    amount = context.user_data["transfer_amount"]
    rate = context.user_data["profile"].usd_to_cop_rate

    if from_account.currency == to_account.currency:
        converted = amount
        conversion_line = ""
    elif from_account.currency == "COP" and to_account.currency == "USD":
        converted = (amount / rate).quantize(Decimal("0.01"))
        conversion_line = f"\n💱 Equivale a: *{_fmt_usd(converted)}*\n_(tasa: {_fmt_cop(rate)})_"
    else:
        converted = (amount * rate).quantize(Decimal("0.01"))
        conversion_line = f"\n💱 Equivale a: *{_fmt_cop(converted)}*\n_(tasa: {_fmt_cop(rate)})_"

    context.user_data["transfer_converted"] = converted

    text = (
        f"🔄 *Confirmar transferencia*\n\n"
        f"De: *{from_account.name}* ({from_account.currency})\n"
        f"A:  *{to_account.name}* ({to_account.currency})\n"
        f"Monto: *{_fmt(amount, from_account.currency)}*"
        f"{conversion_line}\n\n"
        f"¿Confirmás?"
    )
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=confirm_transfer_keyboard())
    return TRANSFER_CONFIRM


async def handle_transfer_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    data = context.user_data
    profile = data["profile"]
    from_account = data["transfer_from"]
    to_account = data["transfer_to"]
    amount = data["transfer_amount"]
    converted = data["transfer_converted"]

    try:
        await sync_to_async(create_transfer)(
            user=profile.user,
            from_account_id=from_account.id,
            to_account_id=to_account.id,
            amount=amount,
            rate=profile.usd_to_cop_rate,
        )
        text = (
            f"✅ *Transferencia realizada*\n\n"
            f"📤 {from_account.name}: -{_fmt(amount, from_account.currency)}\n"
            f"📥 {to_account.name}: +{_fmt(converted, to_account.currency)}\n\n"
            f"¿Qué más querés hacer?"
        )
    except Exception:
        logger.exception("Error al crear transferencia")
        text = "❌ Error inesperado. Intentá de nuevo."

    context.user_data.clear()
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=main_menu_keyboard())
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
                CallbackQueryHandler(handle_transfer_start, pattern="^transfer$"),
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
            TRANSFER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_transfer_amount),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            TRANSFER_FROM: [
                CallbackQueryHandler(handle_transfer_from, pattern="^tfrom:"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            TRANSFER_TO: [
                CallbackQueryHandler(handle_transfer_to, pattern="^tto:"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
            TRANSFER_CONFIRM: [
                CallbackQueryHandler(handle_transfer_execute, pattern="^transfer_confirm$"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("menu", start),
        ],
        per_message=False,
    )
