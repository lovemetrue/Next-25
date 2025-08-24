# utils/decorators.py
import logging
from functools import wraps

logger = logging.getLogger(__name__)


def debug_handler(func):
    """Декоратор для отладки обработчиков"""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            message = args[0]
            logger.debug(f"Обработчик {func.__name__} вызван с сообщением: {message.text}")
            logger.debug(f"User ID: {message.from_user.id}, Chat ID: {message.chat.id}")

            # Логируем текущее состояние
            from ..utils.loader import bot
            current_state = bot.get_state(message.from_user.id, message.chat.id)
            logger.debug(f"Текущее состояние: {current_state}")

            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Ошибка в обработчике {func.__name__}: {e}")
            raise

    return wrapper