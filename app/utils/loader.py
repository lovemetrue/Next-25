from telebot import TeleBot
from telebot.storage import StateMemoryStorage
from config.settings import settings

# Упрощенная инициализация storage
state_storage = StateMemoryStorage()
bot = TeleBot(settings.BOT_TOKEN, state_storage=state_storage)