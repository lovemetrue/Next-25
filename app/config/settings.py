import os
from dotenv import load_dotenv
from telebot.types import BotCommand

load_dotenv()

class Settings:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS", "").split(",") if id]

    # Список команд для меню бота (используем кортежи)
    BOT_COMMANDS = (
        BotCommand('start', 'Запуск бота и регистрация'),
        BotCommand('profile', 'Показать профиль пользователя'),
        BotCommand('cancel', 'Отменить текущее действие')
    )
    DATE_FORMAT = "%d.%m.%Y"

    # Список команд для обработчиков (используем кортежи)
    COMMAND_HANDLERS = {
        'common': ('start', 'profile', 'cancel'),
        'dispatcher': ('create_request', 'my_requests', 'drivers', 'stats'),
        'driver': ('active_requests', 'accept_request', 'in_transit', 'delivered', 'my_stats'),
        'manager': ('general_stats', 'personnel', 'all_requests', 'analytics', 'export_reports')
    }


settings = Settings()