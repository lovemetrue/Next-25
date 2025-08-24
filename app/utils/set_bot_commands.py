# utils/set_bot_commands.py
import logging
from app.utils.loader import bot
from app.config.settings import settings

logger = logging.getLogger(__name__)

def set_bot_commands(bot):
    """Установка команд меню для бота"""
    try:
        bot.set_my_commands(settings.BOT_COMMANDS)
        logger.info("Команды бота успешно установлены")
        return True
    except Exception as e:
        logger.error(f"Ошибка при установке команд бота: {e}")
        return False