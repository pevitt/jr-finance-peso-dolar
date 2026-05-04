from typing import List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 Agregar ingreso", callback_data="add_income"),
            InlineKeyboardButton("💸 Agregar egreso", callback_data="add_expense"),
        ],
        [
            InlineKeyboardButton("📊 Ver balance", callback_data="balance"),
            InlineKeyboardButton("📅 Resumen del mes", callback_data="summary"),
        ],
        [
            InlineKeyboardButton("💱 Actualizar tasa USD/COP", callback_data="update_rate"),
        ],
    ])


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]])


def accounts_keyboard(accounts) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"🏦 {acc.name} ({acc.currency})", callback_data=f"account:{acc.id}")]
        for acc in accounts
    ]
    buttons.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)


def categories_keyboard(categories: List[str]) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for cat in categories:
        row.append(InlineKeyboardButton(cat, callback_data=f"cat:{cat}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton("✏️ Otra", callback_data="cat:custom"),
        InlineKeyboardButton("❌ Cancelar", callback_data="cancel"),
    ])
    return InlineKeyboardMarkup(buttons)


def skip_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⏭ Omitir", callback_data="skip"),
        InlineKeyboardButton("❌ Cancelar", callback_data="cancel"),
    ]])
