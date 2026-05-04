import asyncio
import logging

from django.conf import settings
from telegram import Bot
from telegram.ext import Application

from utils.channels.base import BaseChannel
from utils.channels.telegram.handlers.conversation import build_conversation_handler

logger = logging.getLogger(__name__)


class TelegramChannel(BaseChannel):

    def run(self):
        asyncio.run(self._clear_conflict())
        app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
        app.add_handler(build_conversation_handler())
        logger.info("Bot de Telegram iniciado con polling...")
        app.run_polling(drop_pending_updates=True)

    async def _clear_conflict(self):
        """Cierra cualquier sesión de polling activa antes de arrancar."""
        async with Bot(token=settings.TELEGRAM_BOT_TOKEN) as bot:
            await bot.delete_webhook(drop_pending_updates=True)
