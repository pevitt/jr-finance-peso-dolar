from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Inicia el bot de Telegram con polling"

    def handle(self, *args, **options):
        from utils.channels.telegram.channel import TelegramChannel
        self.stdout.write("Iniciando bot de Telegram...")
        TelegramChannel().run()
