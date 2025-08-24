import os
from loguru import logger
from utils.loader import bot
from telebot import TeleBot
from handlers.start import register_handlers
from database.models import create_all_tables
from telebot.storage import StateMemoryStorage
from handlers.manager import register_manager_handlers
from handlers.profile import register_profile_handlers
from handlers.driver import register_driver_handlers
from handlers.dispatcher import register_dispatcher_handlers
from handlers.chat import register_chat_handlers
from config.settings import settings


# db
create_all_tables()
#### delete row in the DB


# handlers
register_handlers(bot) ### хендлер для первичной регистраци юзеров
register_profile_handlers(bot) ### хендлер для вывода профиля /profile
register_driver_handlers(bot)
register_dispatcher_handlers(bot)
register_manager_handlers(bot)

logger.info("Bot is up")

bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    bot.set_my_commands(settings.BOT_COMMANDS)
    main()
