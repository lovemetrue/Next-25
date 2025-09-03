import os
from loguru import logger
from telebot import TeleBot
from telebot.storage import StateMemoryStorage
from app.utils.loader import bot
from app.handlers.start import register_handlers
from app.database.models import create_all_tables
from app.handlers.manager import register_manager_handlers
from app.handlers.profile import register_profile_handlers
from app.handlers.driver import register_driver_handlers
from app.handlers.dispatcher import register_dispatcher_handlers
from app.handlers.chat import register_chat_handlers
from app.handlers.delete_user import register_delete_user_handlers
from app.config.settings import settings


# db
create_all_tables()
#### delete row in the DB


# handlers
register_handlers(bot) ### хендлер для первичной регистраци юзеров
register_profile_handlers(bot) ### хендлер для вывода профиля /profile
register_driver_handlers(bot)
register_dispatcher_handlers(bot)
register_manager_handlers(bot)
register_delete_user_handlers(bot)
logger.info("Bot is up")

bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    main()
