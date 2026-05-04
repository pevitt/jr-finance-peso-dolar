from abc import ABC, abstractmethod


class BaseChannel(ABC):
    """Interfaz base para canales de comunicación (Telegram, WhatsApp, Twilio)."""

    @abstractmethod
    def run(self):
        """Inicia el canal."""
        pass
