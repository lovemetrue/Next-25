# handlers/delete_user.py
from telebot import TeleBot, types
from app.database.models import User, UserRole
from loguru import logger

def register_delete_user_handlers(bot: TeleBot):
    """
    Регистрирует хендлеры удаления (деактивации) пользователей:
      - /delete_me — деактивировать собственную учётку (любой пользователь).
      - /delete_user @username — деактивировать по нику (только руководитель).
    """

    # ===== ВСПОМОГАТЕЛЬНЫЕ =====

    def _get_user_by_tg(tg_id: int) -> User | None:
        """Вернуть пользователя по Telegram ID (или None)."""
        try:
            return User.get_or_none(User.tg_id == tg_id)
        except Exception:
            logger.exception("User lookup failed")
            return None
    # ===== /delete_me =====

    @bot.message_handler(commands=["delete_me"])
    def cmd_delete_me(message: types.Message):
        """
        Запрос подтверждения на деактивацию собственной учётки.
        После деактивации пользователь может заново пройти /start и выбрать роль.
        """
        user = _get_user_by_tg(message.from_user.id)
        if not user or not user.is_active:
            bot.reply_to(message, "❔ Активная учётная запись не найдена.")
            return

        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ Да, удалить меня", callback_data="delme:yes"),
            types.InlineKeyboardButton("❌ Отмена", callback_data="delme:no"),
        )
        bot.reply_to(
            message,
            "Вы уверены, что хотите удалить (деактивировать) свою учётную запись?\n"
            "После этого вы сможете снова запуститься через /start и выбрать правильную роль.",
            reply_markup=kb
        )

    @bot.callback_query_handler(func=lambda c: c.data in ("delme:yes", "delme:no"))
    def cb_delete_me(call: types.CallbackQuery):
        """
        Подтверждение/отмена деактивации собственной учётной записи.
        """
        user = _get_user_by_tg(call.from_user.id)
        if not user:
            bot.answer_callback_query(call.id, "Учётка не найдена.")
            return

        if call.data == "delme:no":
            bot.answer_callback_query(call.id, "Отменено.")
            try:
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            except Exception:
                pass
            return

        # delme:yes
        try:
            user.is_active = False
            # опционально можно "анонимизировать" чувствительные поля:
            # user.phone = None
            # user.employee_id = None
            user.save()
        except Exception:
            logger.exception("Deactivate self failed")
            bot.answer_callback_query(call.id, "Ошибка удаления. Попробуйте позже.")
            return

        bot.answer_callback_query(call.id, "✅ Учётная запись деактивирована.")
        try:
            bot.edit_message_text(
                "✅ Ваша учётная запись деактивирована.\n"
                "Теперь вы можете заново пройти регистрацию: /start",
                call.message.chat.id,
                call.message.message_id
            )
        except Exception:
            bot.send_message(
                call.message.chat.id,
                "✅ Ваша учётная запись деактивирована.\nТеперь вы можете заново пройти регистрацию: /start"
            )
