# handlers/profile.py
from telebot import TeleBot, types
from loguru import logger

from app.database.models import User, UserRole
from keyboards.main_menu import get_main_menu


def register_profile_handlers(bot: TeleBot):
    """Регистрация хэндлеров профиля"""

    @bot.message_handler(commands=["profile"])
    def cmd_profile(message: types.Message):
        user = User.get_or_none(User.tg_id == message.from_user.id)
        if not user:
            bot.send_message(message.chat.id, "❌ Ты ещё не зарегистрирован. Используй команду /start.")
            return

        role = UserRole(user.role)
        text = (
            f"<b>👤 Профиль</b>\n"
            f"Имя: {user.first_name or '-'} {user.last_name or ''}\n"
            f"Логин: @{user.username if user.username else '—'}\n"
            f"Телефон: {user.phone or '—'}\n"
            f"ID сотрудника: {user.employee_id or '—'}\n"
            f"Роль: <b>{role.label}</b>\n"
        )

        bot.send_message(message.chat.id, text, parse_mode="HTML",
                         reply_markup=get_main_menu(role.name.lower()))